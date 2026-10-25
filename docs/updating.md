# Updating ctxproxy

ctxproxy ships a signed self-update path:

```bash
ctxproxy update --check
ctxproxy update --yes
```

## Release artifacts

Each release should publish:

- `ctxproxy-<version>-py3-none-any.whl` and/or a one-file binary;
- `manifest.json`;
- a detached SHA-256 and Ed25519 signature inside the manifest.

Manifest shape:

```json
{
  "version": "0.3.1",
  "url": "https://example.com/ctxproxy-0.3.1-py3-none-any.whl",
  "sha256": "…64 hex…",
  "signature": "base64 Ed25519 signature",
  "notes": "optional"
}
```

The signature covers canonical JSON of every field except `signature`.

## Configuration

```toml
[update]
enabled = true
manifest_url = "https://github.com/ahmed-dev25/ctxproxy/releases/latest/download/manifest.json"
public_key = "base64 Ed25519 public key"
```

Environment overrides:

```powershell
$env:CTXPROXY_UPDATE_MANIFEST = "https://…/manifest.json"
$env:CTXPROXY_UPDATE_PUBLIC_KEY = "…"
```

## Generate a signed manifest (dev only)

```powershell
uv run --extra update python tools/make_update_manifest.py `
  --artifact dist\ctxproxy-0.3.1-py3-none-any.whl `
  --version 0.3.1 `
  --url https://example.com/ctxproxy-0.3.1-py3-none-any.whl `
  --private-key key.hex `
  --out dist\manifest.json
```

Never commit the private key. The public key is embedded/shipped in the release
build.

## Install behavior

- Wheel artifacts: `pip install --upgrade <wheel>` in the active environment.
- Frozen one-file builds: the running executable is backed up as
  `ctxproxy.exe.old` (or equivalent) and replaced; restart ctxproxy afterwards.
- Source/Python installs of a binary artifact are not replaced automatically;
  the command reports that the verified artifact was downloaded.
- `--dry-run` verifies and prints the action without installing.
- `--allow-unsigned` exists only for local development; never use it for a
  release.

## Version policy

- Updates are free; ctxproxy is MIT open source.
- `ctxproxy update --check` is safe to run frequently.
