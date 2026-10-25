# Updating ctxproxy

ctxproxy does **not** ship a built-in self-update command. Updates are handled
by the package manager or installation method you used.

## uv / pipx

```powershell
uv tool upgrade ctxproxy
# or
pipx upgrade ctxproxy
```

## Local wheel

Download the new wheel from the official release, verify `SHA256SUMS`, then
reinstall it:

```powershell
uv tool install --force .\ctxproxy-<version>-py3-none-any.whl
```

## From a checkout

```powershell
git pull
uv sync --extra dev
uv run ctxproxy --version
```

## Release artifacts

Each release should publish:

- `ctxproxy-<version>-py3-none-any.whl` and the sdist;
- `SHA256SUMS`;
- unsigned PyInstaller binaries where available.

There is no update `manifest.json` or signing key. Integrity and authenticity
come from the package index/GitHub release channel and TLS. Only install from
the official repository or package index, and compare checksums when
downloading binaries manually.

Windows SmartScreen and macOS Gatekeeper may warn because release binaries are
not code-signed/notarized yet.
