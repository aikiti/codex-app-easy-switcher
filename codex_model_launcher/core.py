from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import time
import urllib.parse
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


APP_NAME = "CodexModelLauncher"
DEFAULT_CODEX_OLLAMA_MODEL = "gpt-oss:120b-cloud"
WORKSHOP_MODEL_8GB = "gemma3:1b"
WORKSHOP_MODEL_16GB = "gemma4:e2b-it-qat"
WORKSHOP_MODEL_GEMMA4_E4B = "gemma4:e4b-it-qat"
WORKSHOP_MODEL_GEMMA4_12B = "gemma4:12b-it-qat"
WORKSHOP_MODEL_QWEN_9B = "qwen3.5:9b"
WORKSHOP_MODEL_32GB = "qwen3.5:27b"
# Ollama Launch が config.toml に書き込むプロファイル名。新しい Codex は
# トップレベルの `profile = "..."` を廃止したため、切り替え後にこの行だけ取り除く。
OLLAMA_LAUNCH_PROFILE = "ollama-launch-codex-app"
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
MAC_CODEX_APP = Path("/Applications/Codex.app")
OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"
OLLAMA_LIBRARY_BASE_URL = "https://ollama.com/library/"
MAC_OLLAMA_CANDIDATES = (
    Path("/usr/local/bin/ollama"),
    Path("/opt/homebrew/bin/ollama"),
)
WINDOWS_CODEX_EXISTS_SCRIPT = (
    "$app = Get-StartApps | Where-Object { $_.Name -like 'Codex*' } | "
    "Select-Object -First 1; "
    "if ($null -ne $app) { exit 0 } else { exit 1 }"
)
WINDOWS_CODEX_RUNNING_SCRIPT = (
    "if (Get-Process -Name 'Codex' -ErrorAction SilentlyContinue) "
    "{ exit 0 } else { exit 1 }"
)
WINDOWS_CODEX_QUIT_SCRIPT = (
    "$closed = $false; "
    "Get-Process -Name 'Codex' -ErrorAction SilentlyContinue | ForEach-Object { "
    "if ($_.MainWindowHandle -ne 0 -and $_.CloseMainWindow()) { $closed = $true } }; "
    "if ($closed) { exit 0 } else { exit 1 }"
)
WINDOWS_CODEX_LAUNCH_SCRIPT = (
    "$app = Get-StartApps | Where-Object { $_.Name -like 'Codex*' } | "
    "Select-Object -First 1; "
    "if ($null -eq $app) { exit 1 }; "
    "Start-Process explorer.exe -ArgumentList ('shell:AppsFolder\\' + $app.AppID)"
)


@dataclass
class AppSettings:
    install_model: str = ""
    window_geometry: str = "900x720"
    codex_model: str = ""


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
    capabilities: tuple[str, ...] = ()
    context_length: int = 0

    @property
    def kind(self) -> str:
        return "Cloud" if is_cloud_model(self.name) else "ローカル"

    @property
    def codex_status(self) -> str:
        if is_codex_compatible_model(self):
            return "Codex対応Cloud" if is_cloud_model(self.name) else "Codex対応"
        if self.capabilities:
            return "Codex非対応Cloud" if is_cloud_model(self.name) else "Ollama体験用"
        return "Cloud未確認" if is_cloud_model(self.name) else "未確認"


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
    codex_model = str(data.get("codex_model", "")).strip()
    if codex_model and not is_valid_model(codex_model):
        codex_model = ""
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


def backup_codex_config(
    path: Path | None = None,
    backup_dir: Path | None = None,
    timestamp: str | None = None,
) -> Path:
    """Create an atomic, non-overwriting snapshot before changing Codex config."""
    source = path or codex_config_file()
    if not source.is_file():
        raise FileNotFoundError(f"Codex設定ファイルが見つかりません: {source}")
    destination_dir = backup_dir or (settings_file().parent / "backups")
    destination_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = destination_dir / f"config.before-switch.{stamp}.toml"
    suffix = 1
    while destination.exists():
        destination = destination_dir / f"config.before-switch.{stamp}-{suffix}.toml"
        suffix += 1
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return destination


def detect_ollama() -> str | None:
    system = platform.system()
    if system == "Darwin":
        for candidate in MAC_OLLAMA_CANDIDATES:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    elif system == "Windows":
        candidates = []
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(
                Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Ollama" / "ollama.exe"
            )
        if os.environ.get("ProgramFiles"):
            candidates.append(Path(os.environ["ProgramFiles"]) / "Ollama" / "ollama.exe")
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return shutil.which("ollama")


def detect_windows_powershell() -> str | None:
    for name in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
        path = shutil.which(name)
        if path:
            return path
    return None


def build_windows_powershell_args(powershell_path: str, script: str) -> list[str]:
    return [
        powershell_path,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    ]


def subprocess_window_options(system: str | None = None) -> dict[str, int]:
    system = system or platform.system()
    if system == "Windows":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def codex_app_exists(
    system: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    system = system or platform.system()
    if system == "Darwin":
        return MAC_CODEX_APP.is_dir()
    if system == "Windows":
        powershell = detect_windows_powershell()
        if not powershell:
            return False
        ok, _ = _run(
            build_windows_powershell_args(powershell, WINDOWS_CODEX_EXISTS_SCRIPT),
            timeout=10,
            runner=runner,
        )
        return ok
    return False


def codex_config_file(
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return the active user-level Codex config path.

    An explicit ``home`` is retained for deterministic callers and tests. In normal
    operation, ``CODEX_HOME`` is authoritative when set; otherwise Codex defaults to
    ``~/.codex``.
    """
    if home is not None:
        return home / ".codex" / "config.toml"
    environment = os.environ if environ is None else environ
    configured_home = environment.get("CODEX_HOME", "").strip()
    if configured_home:
        expanded = os.path.expandvars(configured_home)
        return Path(expanded).expanduser() / "config.toml"
    return Path.home() / ".codex" / "config.toml"


def is_valid_model(model: str) -> bool:
    return bool(MODEL_PATTERN.fullmatch(model.strip()))


def ollama_model_library_url(model: str) -> str:
    """Return the official Ollama library URL for a validated model name."""
    normalized = model.strip()
    if not is_valid_model(normalized):
        raise ValueError("モデル名に使用できない文字が含まれています。")
    return OLLAMA_LIBRARY_BASE_URL + urllib.parse.quote(normalized, safe="")


def normalize_model_input(value: str) -> str | None:
    """Accept a bare model name or an exact Ollama run/pull command.

    Official Ollama model pages commonly show ``ollama run <model>``. Only that
    fixed, argument-free shape is accepted; the returned model is validated again
    before it can be passed to subprocess.
    """
    text = value.strip()
    if is_valid_model(text):
        return text
    match = re.fullmatch(r"ollama\s+(?:run|pull)\s+(\S+)", text, flags=re.IGNORECASE)
    if not match:
        return None
    model = match.group(1)
    return model if is_valid_model(model) else None


def is_cloud_model(model: str) -> bool:
    lowered = model.strip().lower()
    return lowered.endswith(":cloud") or lowered.endswith("-cloud")


def model_kind(model: str) -> str:
    return "Cloudモデル" if is_cloud_model(model) else "ローカルモデル"


def is_codex_compatible_model(model: OllamaModel) -> bool:
    """Return whether an installed model exposes the features Codex needs."""
    capabilities = {item.lower() for item in model.capabilities}
    return (
        {"tools", "thinking"}.issubset(capabilities)
        and model.context_length >= 65536
    )


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
    # Codex may omit model_provider for its built-in OpenAI provider. A
    # top-level model without an Ollama profile/provider is normal Codex.
    if model:
        return CodexState(
            "normal",
            model=model,
            detail=f"通常のCodex GPT: {model}",
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


def strip_top_level_profile(
    config_text: str,
    profile_name: str = OLLAMA_LAUNCH_PROFILE,
) -> tuple[str, bool]:
    """トップレベルの `profile = "<profile_name>"` 行だけを取り除く。

    新しい Codex はトップレベルの `profile = "..."` を廃止し、設定読み込み時に
    `failed to resolve feature override precedence` エラーを出す。Ollama Launch は
    このキーを書き込むため、切り替え後に取り除いて互換性を保つ。
    `[profiles.<name>]` セクション（最初の `[` 以降）には触れない。
    戻り値は (新しい本文, 変更したか)。
    """
    head, separator, rest = config_text.partition("\n[")
    pattern = re.compile(
        r'(?m)^[ \t]*profile[ \t]*=[ \t]*"'
        + re.escape(profile_name)
        + r'"[ \t]*\r?\n?'
    )
    new_head, count = pattern.subn("", head)
    if count == 0:
        return config_text, False
    return new_head + separator + rest, True


def remove_legacy_profile_from_config(
    path: Path | None = None,
    profile_name: str = OLLAMA_LAUNCH_PROFILE,
) -> bool:
    """config.toml から廃止された `profile = "..."` 行を取り除く。変更したら True。

    Ollama 切り替え（`ollama launch codex-app`）の直後に呼び出して、新しい Codex で
    プロンプトが通るようにする。本アプリは通常 config.toml を書き換えないが、これは
    Ollama Launch が残すレガシー設定を打ち消す最小限の互換処理。
    """
    path = path or codex_config_file()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    new_text, changed = strip_top_level_profile(text, profile_name)
    if not changed:
        return False
    temporary = path.with_suffix(".tmp")
    try:
        temporary.write_text(new_text, encoding="utf-8")
        os.replace(temporary, path)
    except OSError:
        return False
    return True


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
            **subprocess_window_options(),
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
    if system == "Darwin":
        ok, _ = _run(
            ["/usr/bin/pgrep", "-f", "^/Applications/Codex.app/Contents/MacOS/Codex$"],
            timeout=5,
            runner=runner,
        )
        return ok
    if system == "Windows":
        powershell = detect_windows_powershell()
        if not powershell:
            return False
        ok, _ = _run(
            build_windows_powershell_args(powershell, WINDOWS_CODEX_RUNNING_SCRIPT),
            timeout=5,
            runner=runner,
        )
        return ok
    return False


def quit_codex_app(
    system: str | None = None,
    timeout: float = 12,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[bool, str]:
    system = system or platform.system()
    if system not in ("Darwin", "Windows"):
        return False, "このOSには対応していません。"
    if not codex_app_is_running(system=system, runner=runner):
        return True, "Codex Appは起動していません。"
    if system == "Darwin":
        quit_args = ["/usr/bin/osascript", "-e", 'tell application "Codex" to quit']
    else:
        powershell = detect_windows_powershell()
        if not powershell:
            return False, "Windows PowerShellが見つかりません。"
        quit_args = build_windows_powershell_args(
            powershell,
            WINDOWS_CODEX_QUIT_SCRIPT,
        )
    ok, output = _run(quit_args, timeout=10, runner=runner)
    if not ok:
        if system == "Darwin":
            lowered = output.lower()
            if "not authorized" in lowered or "-1743" in output:
                return (
                    False,
                    "macOSでCodex Appを終了する許可がありません。"
                    "表示された許可画面で操作を許可し、もう一度お試しください。",
                )
            return False, output or "Codex Appを終了できませんでした。"
        return (
            False,
            "Codex Appを通常終了できませんでした。"
            "Codex Appを手動で閉じてから、もう一度お試しください。",
        )
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
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[bool, str]:
    system = system or platform.system()
    if system == "Darwin":
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
    if system == "Windows":
        powershell = detect_windows_powershell()
        if not powershell:
            return False, "Windows PowerShellが見つかりません。"
        ok, output = _run(
            build_windows_powershell_args(powershell, WINDOWS_CODEX_LAUNCH_SCRIPT),
            timeout=15,
            runner=runner,
        )
        if ok:
            return True, "Codex Appを起動しました。"
        return False, output or "WindowsのスタートメニューにCodex Appが見つかりません。"
    return False, "このOSには対応していません。"


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


def parse_ollama_show(output: str) -> tuple[tuple[str, ...], int]:
    capabilities: list[str] = []
    in_capabilities = False
    context_length = 0
    for line in output.splitlines():
        stripped = line.strip()
        context_match = re.fullmatch(r"context length\s+(\d+)", stripped, re.IGNORECASE)
        if context_match:
            context_length = int(context_match.group(1))
        if stripped == "Capabilities":
            in_capabilities = True
            continue
        if in_capabilities:
            if line.startswith("    ") and stripped:
                capabilities.append(stripped.lower())
                continue
            if stripped:
                in_capabilities = False
    return tuple(capabilities), context_length


def inspect_ollama_model(ollama_path: str, model: OllamaModel) -> OllamaModel:
    ok, output = _run([ollama_path, "show", model.name], timeout=30)
    if not ok:
        return model
    capabilities, context_length = parse_ollama_show(output)
    return replace(
        model,
        capabilities=capabilities,
        context_length=context_length,
    )


def list_ollama_models(ollama_path: str) -> tuple[bool, list[OllamaModel], str]:
    if not ollama_path:
        return False, [], "Ollamaが見つかりません。"
    ok, output = _run([ollama_path, "list"], timeout=30)
    if not ok:
        return False, [], output
    models = parse_ollama_models(output)
    models = [inspect_ollama_model(ollama_path, model) for model in models]
    return True, models, output


def run_checks() -> tuple[list[CheckResult], list[OllamaModel], CodexState]:
    results: list[CheckResult] = []
    state = read_codex_state()
    results.append(CheckResult("ok" if state.mode != "unknown" else "warning", "Codex接続", state.detail))
    app_exists = codex_app_exists()
    results.append(
        CheckResult(
            "ok" if app_exists else "error",
            "Codex App",
            "インストールされています。" if app_exists else "Codex Appが見つかりません。",
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
