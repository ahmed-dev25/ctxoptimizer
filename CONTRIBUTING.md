# Contributing

Thanks for helping improve ctxproxy.

## Before opening a pull request

- Search existing issues and pull requests first.
- Keep changes focused and explain the user-visible impact.
- Add or update tests for behavior changes.
- Never include real API keys, captured prompts, credentials, private logs, or
  signing material. Use fake values in tests.
- For security issues, follow [`SECURITY.md`](SECURITY.md) instead of opening a
  public issue.

## Development

Requirements: Python 3.11+ and `uv`.

```powershell
uv sync --extra dev
uv run ctxproxy run
uv run pytest -q
```

The proxy defaults to `http://127.0.0.1:8787` in `shadow` mode. Use a fake
upstream or the test suite; do not test against a real provider with a
production key in a pull request.

## Gates

All pull requests must pass:

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src
uv run pytest -q --cov --cov-report=term-missing --cov-fail-under=80
```

## Pull requests

- Use a descriptive title and link the relevant issue.
- Include a short test plan.
- Keep generated files and local caches out of the commit.
- Do not bump the version or create release tags unless asked by the maintainer.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
