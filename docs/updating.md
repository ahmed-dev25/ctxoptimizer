# Updating ctxproxy

ctxproxy does **not** ship a built-in self-update command. Updates are handled
by the package manager or installation method you used.

## uv / pipx

If installed from GitHub or PyPI:

```powershell
uv tool upgrade ctxproxy
# or
pipx upgrade ctxproxy
```

## Local wheel

Download the new wheel from the official GitHub release, verify `SHA256SUMS`,
then reinstall it:

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

Each release publishes:

- `ctxproxy-<version>-py3-none-any.whl` and the sdist;
- `SHA256SUMS`;
- unsigned PyInstaller binaries for Linux, macOS and Windows.

There is no update `manifest.json` or signing key. Integrity and authenticity
come from the GitHub release/package-index channel and TLS. Only install from
the official repository, and compare checksums when downloading binaries
manually.

The PyPI package is not published yet; the README uses a Git install in the
meantime. Windows SmartScreen and macOS Gatekeeper may warn because release
binaries are not code-signed/notarized yet.
