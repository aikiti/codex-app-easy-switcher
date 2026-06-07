# Security

## Security model

This application is a local GUI wrapper around official Ollama commands.
It does not collect telemetry, prompts, project files, API keys, or credentials.

It reads the top-level connection state from `~/.codex/config.toml`.
It does not directly edit that file. Connection changes and restoration are
delegated to `ollama launch codex-app`.

## Safety controls

- No `shell=True`, `os.system`, `eval`, or `exec`
- External processes use argument lists
- User-entered model names are allowlisted
- Selected Codex models are validated again before launch
- Cloud models are prioritized and local models require explicit warnings
- Selecting a model alone never restarts Codex App or changes Codex settings
- Confirmation before model downloads
- Confirmation before closing a running Codex App
- Windows requests a normal window close and never force-kills Codex App
- Windows child processes run without a visible command window
- Restore reminder when exiting in Ollama mode
- No model deletion or automatic Ollama installation

## Important operational behavior

Switching providers closes and restarts Codex App. Unsaved or unsubmitted
content may be lost. Ollama Launch modifies the Codex configuration and stores
backups under `~/.ollama/backup/codex-app/`.

The distributed macOS application is ad-hoc signed and is not Apple-notarized.
The Windows EXE is built by GitHub Actions and is not Authenticode-signed.

## Dependency posture

The application source uses only the Python standard library. PyInstaller is
used only to create the macOS distribution bundle and is not imported by the
application at runtime. A dependency CVE scan should still be performed when
the build environment or packaging toolchain changes.

## Reporting a vulnerability

Please open a GitHub issue without including credentials, private project
files, or sensitive logs.
