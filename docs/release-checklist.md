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

## 5. Packaging

- [ ] PyInstaller binary runs on each OS (CI artifacts).
- [ ] Publish wheel/sdist, binaries and `SHA256SUMS` (release workflow).
- [ ] Confirm `uv tool upgrade ctxproxy` / `pipx upgrade ctxproxy` behavior.
- [ ] macOS codesign + notarization (**owner certificate**).
- [ ] Windows code signing (**owner certificate**).
- [ ] Fresh-machine install test on Windows, macOS and Linux.

## 6. Product/legal (owner)

- [x] Choose the project license: MIT open source.
- [ ] Confirm provider/trademark wording in README and metadata.
- [ ] Finalize model pricing/current model IDs and peak/off-peak policy.
- [ ] Review `THIRD_PARTY_LICENSES.md` against the built artifact.
- [ ] Tag with SemVer (`v0.4.0` recommended for the MIT release) and update
      `CHANGELOG.md`/`docs/test-report.md`.
