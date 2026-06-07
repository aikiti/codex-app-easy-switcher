from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from codex_model_launcher.core import (
    DEFAULT_CODEX_OLLAMA_MODEL,
    AppSettings,
    build_pull_args,
    build_switch_args,
    is_cloud_model,
    is_valid_model,
    load_settings,
    model_kind,
    parse_codex_state,
    parse_ollama_models,
    parse_version,
    quit_codex_app,
    save_settings,
    settings_file,
    state_matches_target,
    switch_codex_connection,
)


class CoreTests(unittest.TestCase):
    def test_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            settings = AppSettings("qwen2.5-coder:7b", "900x720+10+20")
            save_settings(settings, path)
            self.assertEqual(load_settings(path), settings)

    def test_invalid_saved_model_is_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text(json.dumps({"install_model": "bad;name"}))
            self.assertEqual(load_settings(path).install_model, "")

    def test_platform_settings_locations(self) -> None:
        home = Path("example-home")
        self.assertIn("Library/Application Support", str(settings_file("Darwin", home)))
        self.assertTrue(
            str(settings_file("Windows", home)).endswith(
                "CodexModelLauncher/settings.json"
            )
        )

    def test_model_validation(self) -> None:
        self.assertTrue(is_valid_model(DEFAULT_CODEX_OLLAMA_MODEL))
        self.assertTrue(is_valid_model("namespace/model:tag"))
        for invalid in ("", "model name", "model;rm", "$(bad)", "bad'quote", "bad\nname"):
            self.assertFalse(is_valid_model(invalid), invalid)

    def test_model_kind(self) -> None:
        self.assertEqual(model_kind("gpt-oss:120b-cloud"), "Cloudモデル")
        self.assertTrue(is_cloud_model("qwen3-coder-next:cloud"))
        self.assertEqual(model_kind("qwen2.5-coder:7b"), "ローカルモデル")

    def test_parse_version(self) -> None:
        self.assertEqual(parse_version("ollama version is 0.24.0"), (0, 24, 0))
        self.assertIsNone(parse_version("unknown"))

    def test_parse_normal_codex_state(self) -> None:
        state = parse_codex_state('model = "gpt-5.5"\nmodel_provider = "openai"\n')
        self.assertEqual(state.mode, "normal")
        self.assertEqual(state.model, "gpt-5.5")

    def test_parse_ollama_codex_state(self) -> None:
        state = parse_codex_state(
            'model = "gpt-oss:120b-cloud"\n'
            'profile = "ollama-launch-codex-app"\n'
            'model_provider = "ollama-launch-codex-app"\n'
        )
        self.assertEqual(state.mode, "ollama")
        self.assertEqual(state.model, DEFAULT_CODEX_OLLAMA_MODEL)

    def test_parse_ignores_ollama_in_later_sections(self) -> None:
        state = parse_codex_state(
            'model = "gpt-5.5"\nmodel_provider = "openai"\n'
            '[profiles.ollama-launch-codex-app]\nmodel = "other"\n'
        )
        self.assertEqual(state.mode, "normal")

    def test_state_matches_target(self) -> None:
        normal = parse_codex_state('model = "gpt-5.5"\nmodel_provider = "openai"\n')
        ollama = parse_codex_state(
            'model = "gpt-oss:120b-cloud"\nmodel_provider = "ollama-launch-codex-app"\n'
        )
        other_ollama = parse_codex_state(
            'model = "qwen2.5-coder:7b"\nmodel_provider = "ollama-launch-codex-app"\n'
        )
        self.assertTrue(state_matches_target(normal, "normal"))
        self.assertTrue(state_matches_target(ollama, "ollama"))
        self.assertFalse(state_matches_target(other_ollama, "ollama"))

    def test_build_switch_args(self) -> None:
        self.assertEqual(
            build_switch_args("/usr/local/bin/ollama", "ollama"),
            [
                "/usr/local/bin/ollama",
                "launch",
                "codex-app",
                "--model",
                DEFAULT_CODEX_OLLAMA_MODEL,
                "--yes",
            ],
        )
        self.assertEqual(
            build_switch_args("/usr/local/bin/ollama", "normal"),
            [
                "/usr/local/bin/ollama",
                "launch",
                "codex-app",
                "--restore",
                "--yes",
            ],
        )

    def test_invalid_switch_mode_rejected(self) -> None:
        with self.assertRaises(ValueError):
            build_switch_args("/usr/local/bin/ollama", "bad")

    def test_build_pull_args_validates_model(self) -> None:
        self.assertEqual(
            build_pull_args("/usr/local/bin/ollama", "qwen2.5-coder:7b"),
            ["/usr/local/bin/ollama", "pull", "qwen2.5-coder:7b"],
        )
        with self.assertRaises(ValueError):
            build_pull_args("/usr/local/bin/ollama", "bad;name")

    def test_switch_uses_argument_list_without_shell(self) -> None:
        runner = Mock()
        runner.return_value = Mock(returncode=0, stdout="ok", stderr="")
        ok, _ = switch_codex_connection("/usr/local/bin/ollama", "ollama", runner=runner)
        self.assertTrue(ok)
        args, kwargs = runner.call_args
        self.assertIsInstance(args[0], list)
        self.assertFalse(kwargs["shell"])

    def test_quit_codex_app_uses_graceful_applescript(self) -> None:
        running = Mock(returncode=0, stdout="123", stderr="")
        quit_ok = Mock(returncode=0, stdout="", stderr="")
        stopped = Mock(returncode=1, stdout="", stderr="")
        runner = Mock(side_effect=[running, quit_ok, stopped])
        ok, _ = quit_codex_app(runner=runner, sleep=lambda _seconds: None)
        self.assertTrue(ok)
        self.assertEqual(
            runner.call_args_list[1].args[0],
            ["/usr/bin/osascript", "-e", 'tell application "Codex" to quit'],
        )
        self.assertFalse(runner.call_args_list[1].kwargs["shell"])

    def test_quit_codex_app_explains_permission_denial(self) -> None:
        running = Mock(returncode=0, stdout="123", stderr="")
        denied = Mock(returncode=1, stdout="", stderr="Not authorized to send Apple events. (-1743)")
        ok, message = quit_codex_app(runner=Mock(side_effect=[running, denied]))
        self.assertFalse(ok)
        self.assertIn("許可", message)

    def test_parse_ollama_models(self) -> None:
        output = (
            "NAME                        ID              SIZE      MODIFIED\n"
            "gpt-oss:120b-cloud          569662207105    -         6 months ago\n"
            "qwen2.5-coder:7b            dae161e27b0e    4.7 GB    11 days ago\n"
        )
        models = parse_ollama_models(output)
        self.assertEqual(len(models), 2)
        self.assertEqual(models[0].kind, "Cloud")
        self.assertEqual(models[1].kind, "ローカル")
        self.assertEqual(models[1].size, "4.7 GB")


if __name__ == "__main__":
    unittest.main()
