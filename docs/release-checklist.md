# Release checklist

Use this before tagging a public release. Items marked **owner** need a human
decision or external credentials.

## 1. Gates

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy --strict src`
- [ ] `uv run pytest -q --cov --cov-fail-under=80`
- [ ] `uv build` (wheel + sdist)
- [ ] `uv run ctxproxy --version`
- [ ] Install the wheel in a clean venv and run `ctxproxy --version`.

## 2. Live/provider contract (owner keys)

- [ ] DeepSeek: stream once, confirm `usage_source=provider` and cache fields.
- [ ] Anthropic: two identical-prefix requests, confirm cache read increases.
- [ ] OpenAI: stream with `include_usage`, confirm usage.
- [ ] Gemini native: function call/response capture, confirm usage metadata.
- [ ] Ollama native: NDJSON final event, confirm prompt/eval counts.
- [ ] Update `docs/provider-notes.md` with date and source/capture notes.

## 3. Client smoke (manual)

- [ ] Claude Code ≥20 turns in shadow then active: no errors, savings visible.
- [ ] OpenCode (`opencode run --standalone`) through `/u/<name>`.
- [ ] Aider or an SDK script.
- [ ] Verify no drift “our-fault” events, no transform fallbacks.

## 4. Security/privacy

- [ ] Dashboard works only with the per-run token; bad Host is rejected.
- [ ] CSRF required on mutations; no CORS headers.
- [ ] `ctxproxy purge --all` removes DB and blobs.
- [ ] Capture is off/limited unless intentionally enabled.
- [ ] No credentials in logs, DB, blobs or fixtures.

## 5. Packaging and PyPI

- [ ] Build wheel/sdist and run the clean-venv install smoke.
- [ ] Configure the PyPI trusted publisher:
      owner `ahmed-dev25`, repo `ctxproxy`, workflow `release.yml`,
      environment `pypi`, project `ctxproxy`.
- [ ] Create the GitHub `pypi` environment restricted to `v*` tags.
- [ ] Publish with Trusted Publishing; confirm PEP 740 attestations on PyPI.
- [ ] Publish wheel/sdist and `SHA256SUMS` as GitHub release assets.
- [ ] Confirm `uv tool upgrade ctxproxy` / `pipx upgrade ctxproxy` behavior.
- [ ] Fresh-machine install test on Windows, macOS and Linux.
- [x] No standalone binaries or OS code signing in this release path.

## 6. Product/legal (owner)

- [x] Choose the project license: MIT open source.
- [ ] Confirm provider/trademark wording in README and metadata.
- [ ] Finalize model pricing/current model IDs and peak/off-peak policy.
- [ ] Review `THIRD_PARTY_LICENSES.md` against the built artifact.
- [ ] Tag with SemVer (`v0.4.1` recommended for the PyPI release) and update
      `CHANGELOG.md`/`docs/test-report.md`.
