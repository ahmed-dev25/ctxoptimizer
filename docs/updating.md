# Updating ctxoptimizer

ctxoptimizer does **not** ship a built-in self-update command. Updates are handled
by the package manager or installation method you used.

## uv / pipx

```powershell
uv tool upgrade ctxoptimizer
# or
pipx upgrade ctxoptimizer
```

## Local wheel

Download the new wheel from PyPI or the official GitHub release, verify its
attestation/checksum, then reinstall it:

```powershell
uv tool install --force .\ctxoptimizer-<version>-py3-none-any.whl
```

## From a checkout

```powershell
git pull
uv sync --extra dev
uv run ctxoptimizer --version
```

## Release artifacts

Each release publishes a wheel, sdist and `SHA256SUMS` on GitHub. PyPI releases
are uploaded with Trusted Publishing and PEP 740 attestations; there is no
`manifest.json`, signing key, standalone binary or OS code-signing step.

Only install from PyPI or the official GitHub release. There is no phone-home
update check.
