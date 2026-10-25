# PyPI release

ctxproxy is distributed as a wheel/sdist only. There are no standalone
binaries or OS code-signing credentials.

## One-time PyPI setup

1. Create a PyPI account and enable 2FA.
2. Open **Account settings → Publishing** and add a **pending trusted
   publisher** (the project does not exist yet). Use the values below.
3. On GitHub, create the `pypi` environment restricted to `v*` tags.

The PyPI project must have a **pending trusted publisher** configured before
the first workflow run:

| Field | Value |
|---|---|
| PyPI project name | `ctxproxy` |
| Publisher | GitHub |
| Owner | `ahmed-dev25` |
| Repository | `ctxproxy` |
| Workflow name | `release.yml` |
| Environment | `pypi` |

On GitHub, create an environment named `pypi` and restrict it to tags matching
`v*`. The publish job uses `id-token: write`; no PyPI token or password is
stored in this repository.

If the `ctxproxy` name is already owned on PyPI by another project, do not
attempt to upload over it. Choose a different distribution name and update
`pyproject.toml`, this document and the README.

## Release process

1. Bump the version in `pyproject.toml` and `src/ctxproxy/__init__.py`.
2. Update `CHANGELOG.md` and `docs/test-report.md`.
3. Run all gates and merge the release commit to `main`.
4. Tag and push:

   ```powershell
   git tag -a v0.4.1 -m "ctxproxy 0.4.1"
   git push origin v0.4.1
   ```

5. The `Release` workflow:
   - builds wheel/sdist;
   - runs a clean-venv install smoke;
   - attests build provenance;
   - publishes to PyPI using Trusted Publishing and PEP 740 attestations;
   - creates a GitHub release with wheel, sdist and `SHA256SUMS`.

## Verification

```powershell
uv tool install ctxproxy
ctxproxy --version
uv tool upgrade ctxproxy
```

Check the PyPI project page and its attestation/provenance details. Also verify:

```powershell
gh release download v0.4.1 --pattern SHA256SUMS
```

Do not add a PyPI API token unless Trusted Publishing is temporarily
unavailable; prefer OIDC.
