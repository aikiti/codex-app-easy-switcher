from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence


APP_NAME = "CodexModelLauncher"
DEFAULT_CODEX_OLLAMA_MODEL = "gpt-oss:120b-cloud"
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
MAC_CODEX_APP = Path("/Applications/Codex.app")
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"
MAC_OLLAMA_CANDIDATES = (
    Path("/usr/local/bin/ollama"),
    Path("/opt/homebrew/bin/ollama"),
)


@dataclass
class AppSettings:
    install_model: str = ""
    window_geometry: str = "900x720"
    codex_model: str = DEFAULT_CODEX_OLLAMA_MODEL


@dataclass
class CodexState:
    mode: str
    model: str = ""
    provider: str = ""
    detail: str = ""


@dataclass
class OllamaModel:
    name: str
    model_id: str
    size: str
    modified: str

    @property
    def kind(self) -> str:
        return "Cloud" if is_cloud_model(self.name) else "ローカル"


@dataclass
class CheckResult:
    level: str
    title: str
    detail: str


def settings_file(system: str | None = None, home: Path | None = None) -> Path:
    system = system or platform.system()
    home = home or Path.home()
    if system == "Darwin":
        base = home / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(
            os.environ.get("LOCALAPPDATA")
            or os.environ.get("APPDATA")
            or home / "AppData" / "Local"
        )
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return base / APP_NAME / "settings.json"


def load_settings(path: Path | None = None) -> AppSettings:
    path = path or settings_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return AppSettings()
    model = str(data.get("install_model", "")).strip()
    if model and not is_valid_model(model):
        model = ""
    codex_model = str(data.get("codex_model", DEFAULT_CODEX_OLLAMA_MODEL)).strip()
    if not is_valid_model(codex_model):
        codex_model = DEFAULT_CODEX_OLLAMA_MODEL
    geometry = str(data.get("window_geometry", AppSettings.window_geometry))
    return AppSettings(
        install_model=model,
        window_geometry=geometry,
        codex_model=codex_model,
    )


def save_settings(settings: AppSettings, path: Path | None = None) -> Path:
    path = path or settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def detect_ollama() -> str | None:
    if platform.system() == "Darwin":
        for candidate in MAC_OLLAMA_CANDIDATES:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return shutil.which("ollama")


def codex_app_exists(system: str | None = None) -> bool:
    system = system or platform.system()
    if system == "Darwin":
        return MAC_CODEX_APP.is_dir()
    return True


def codex_config_file(home: Path | None = None) -> Path:
    return (home or Path.home()) / ".codex" / "config.toml"


def is_valid_model(model: str) -> bool:
    return bool(MODEL_PATTERN.fullmatch(model.strip()))


def is_cloud_model(model: str) -> bool:
    lowered = model.strip().lower()
    return lowered.endswith(":cloud") or lowered.endswith("-cloud")


def model_kind(model: str) -> str:
    return "Cloudモデル" if is_cloud_model(model) else "ローカルモデル"


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", text)
    if not match:
        return None
    return tuple(int(value) for value in match.groups())


def parse_codex_state(config_text: str) -> CodexState:
    # Only inspect top-level values. Ollama Launch owns all config changes.
    top_level = config_text.split("\n[", 1)[0]
    values: dict[str, str] = {}
    for match in re.finditer(
        r'(?m)^\s*(model|model_provider|profile)\s*=\s*"([^"]*)"\s*$', top_level
    ):
        values[match.group(1)] = match.group(2)
    model = values.get("model", "")
    provider = values.get("model_provider", "")
    profile = values.get("profile", "")
    combined = f"{provider} {profile}".lower()
    if "ollama" in combined:
        return CodexState(
            "ollama",
            model=model,
            provider=provider,
            detail=f"Ollama経由: {model or 'モデル名不明'}",
        )
    if provider:
        return CodexState(
            "normal",
            model=model,
            provider=provider,
            detail=f"通常のCodex GPT: {model or 'デフォルトモデル'}",
        )
    return CodexState(
        "unknown",
        model=model,
        provider=provider,
        detail="現在の接続状態を判定できません。",
    )


def read_codex_state(path: Path | None = None) -> CodexState:
    path = path or codex_config_file()
    try:
        return parse_codex_state(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return CodexState("unknown", detail="Codex設定ファイルが見つかりません。")
    except OSError as exc:
        return CodexState("unknown", detail=f"Codex設定を読み取れません: {exc}")


def state_matches_target(
    state: CodexState,
    mode: str,
    model: str = DEFAULT_CODEX_OLLAMA_MODEL,
) -> bool:
    if mode == "normal":
        return state.mode == "normal"
    if mode == "ollama":
        return state.mode == "ollama" and state.model == model
    return False


def _run(
    args: Sequence[str],
    timeout: int = 30,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[bool, str]:
    try:
        completed = runner(
            list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    output = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )
    return completed.returncode == 0, output


def codex_app_is_running(
    system: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    system = system or platform.system()
    if system != "Darwin":
        return False
    ok, _ = _run(
        ["/usr/bin/pgrep", "-f", "^/Applications/Codex.app/Contents/MacOS/Codex$"],
        timeout=5,
        runner=runner,
    )
    return ok


def quit_codex_app(
    system: str | None = None,
    timeout: float = 12,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[bool, str]:
    system = system or platform.system()
    if system != "Darwin":
        return False, "現在はmacOS版のみ対応しています。"
    if not codex_app_is_running(system=system, runner=runner):
        return True, "Codex Appは起動していません。"
    ok, output = _run(
        ["/usr/bin/osascript", "-e", 'tell application "Codex" to quit'],
        timeout=10,
        runner=runner,
    )
    if not ok:
        lowered = output.lower()
        if "not authorized" in lowered or "-1743" in output:
            return (
                False,
                "macOSでCodex Appを終了する許可がありません。"
                "表示された許可画面で操作を許可し、もう一度お試しください。",
            )
        return False, output or "Codex Appを終了できませんでした。"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not codex_app_is_running(system=system, runner=runner):
            return True, "Codex Appを終了しました。"
        sleep(0.25)
    return False, "Codex Appの終了を待ちましたが、まだ起動しています。"


def build_switch_args(
    ollama_path: str,
    mode: str,
    model: str = DEFAULT_CODEX_OLLAMA_MODEL,
) -> list[str]:
    if not ollama_path:
        raise ValueError("Ollamaが見つかりません。")
    if mode == "ollama":
        if not is_valid_model(model):
            raise ValueError("モデル名に使用できない文字が含まれています。")
        return [
            ollama_path,
            "launch",
            "codex-app",
            "--model",
            model.strip(),
            "--yes",
        ]
    if mode == "normal":
        return [ollama_path, "launch", "codex-app", "--restore", "--yes"]
    raise ValueError("切り替え先が正しくありません。")


def build_pull_args(ollama_path: str, model: str) -> list[str]:
    if not ollama_path:
        raise ValueError("Ollamaが見つかりません。")
    if not is_valid_model(model):
        raise ValueError("モデル名に使用できない文字が含まれています。")
    return [ollama_path, "pull", model.strip()]


def switch_codex_connection(
    ollama_path: str,
    mode: str,
    model: str = DEFAULT_CODEX_OLLAMA_MODEL,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[bool, str]:
    return _run(build_switch_args(ollama_path, mode, model), timeout=120, runner=runner)


def launch_codex_app(
    system: str | None = None,
    popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
) -> tuple[bool, str]:
    system = system or platform.system()
    if system != "Darwin":
        return False, "現在はmacOS版のみ対応しています。"
    if not MAC_CODEX_APP.is_dir():
        return False, "Codex Appが /Applications に見つかりません。"
    try:
        popen(
            ["/usr/bin/open", "-a", "Codex"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return False, str(exc)
    return True, "Codex Appを起動しました。"


def parse_ollama_models(output: str) -> list[OllamaModel]:
    models: list[OllamaModel] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.upper().startswith("NAME "):
            continue
        parts = re.split(r"\s{2,}", stripped)
        if len(parts) < 4 or not is_valid_model(parts[0]):
            continue
        models.append(
            OllamaModel(
                name=parts[0],
                model_id=parts[1],
                size=parts[2],
                modified="  ".join(parts[3:]),
            )
        )
    return models


def list_ollama_models(ollama_path: str) -> tuple[bool, list[OllamaModel], str]:
    if not ollama_path:
        return False, [], "Ollamaが見つかりません。"
    ok, output = _run([ollama_path, "list"], timeout=30)
    return ok, parse_ollama_models(output) if ok else [], output


def run_checks() -> tuple[list[CheckResult], list[OllamaModel], CodexState]:
    results: list[CheckResult] = []
    state = read_codex_state()
    results.append(CheckResult("ok" if state.mode != "unknown" else "warning", "Codex接続", state.detail))
    results.append(
        CheckResult(
            "ok" if codex_app_exists() else "error",
            "Codex App",
            "インストールされています。" if codex_app_exists() else "Codex Appが見つかりません。",
        )
    )
    ollama_path = detect_ollama()
    if not ollama_path:
        results.append(CheckResult("error", "Ollama", "Ollamaが見つかりません。"))
        return results, [], state
    version_ok, version_output = _run([ollama_path, "--version"], timeout=15)
    version = parse_version(version_output)
    version_level = "ok" if version_ok and version and version >= (0, 24, 0) else "warning"
    results.append(
        CheckResult(
            version_level if version_ok else "error",
            "Ollama",
            (
                version_output
                if version_level == "ok"
                else f"{version_output or 'バージョンを確認できません。'} v0.24.0以降へ更新してください。"
            ),
        )
    )
    list_ok, models, list_output = list_ollama_models(ollama_path)
    results.append(
        CheckResult(
            "ok" if list_ok else "warning",
            "モデル一覧",
            f"{len(models)}件を確認しました。" if list_ok else list_output,
        )
    )
    return results, models, state


def format_checks(results: Iterable[CheckResult]) -> str:
    labels = {"ok": "[OK]", "warning": "[注意]", "error": "[エラー]"}
    return "\n".join(
        f"{labels.get(result.level, '[情報]')} {result.title}: {result.detail}"
        for result in results
    )
