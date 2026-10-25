# PyPI release

ctxoptimizer is distributed as a wheel/sdist only. There are no standalone
binaries or OS code-signing credentials.

## One-time PyPI setup

1. Create a PyPI account and enable 2FA.
2. Open **Account settings → Publishing**. If `ctxoptimizer` is not created yet,
   add a **pending trusted publisher**; otherwise edit the existing project's
   trusted publisher. Use the values below.
3. On GitHub, create the `pypi` environment restricted to `v*` tags.

If a trusted publisher was already created for the old `ctxproxy` repository,
update it to repository `ctxoptimizer` after the GitHub rename.

The PyPI project must have a **pending trusted publisher** configured before
the first workflow run:

| Field | Value |
|---|---|
| PyPI project name | `ctxoptimizer` |
| Publisher | GitHub |
| Owner | `ahmed-dev25` |
| Repository | `ctxoptimizer` |
| Workflow name | `release.yml` |
| Environment | `pypi` |

On GitHub, create an environment named `pypi` and restrict it to tags matching
`v*`. The publish job uses `id-token: write`; no PyPI token or password is
stored in this repository.

If the `ctxoptimizer` name is already owned on PyPI by another project, do not
attempt to upload over it. Choose a different distribution name and update
`pyproject.toml`, this document and the README.

## Release process

1. Bump the version in `pyproject.toml` and `src/ctxoptimizer/__init__.py`.
2. Update `CHANGELOG.md` and `docs/test-report.md`.
3. Run all gates and merge the release commit to `main`.
4. Tag and push:

   ```powershell
   git tag -a v0.4.1 -m "ctxoptimizer 0.4.1"
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
uv tool install ctxoptimizer
ctxoptimizer --version
uv tool upgrade ctxoptimizer
```

Check the PyPI project page and its attestation/provenance details. Also verify:

```powershell
gh release download v0.4.1 --pattern SHA256SUMS
```

Do not add a PyPI API token unless Trusted Publishing is temporarily
unavailable; prefer OIDC.

## `invalid-publisher` troubleshooting

The publish job failed once with `invalid-publisher`. PyPI reported these
claims:

- repository: `ahmed-dev25/ctxoptimizer`
- workflow: `.github/workflows/release.yml`
- environment: `pypi`

The trusted/pending publisher must match **all** of these fields. Common causes:

- the publisher still points at the old repository name `ctxproxy`;
- no GitHub environment is configured on PyPI;
- the workflow filename is different;
- the publisher belongs to a different PyPI project.

After fixing the publisher, rerun the failed GitHub Actions release run.
`v0.4.1` was published successfully after correcting the publisher.

