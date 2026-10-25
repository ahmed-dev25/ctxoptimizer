# Third-party licenses

ctxproxy is distributed under the MIT License. Runtime dependencies are
installed from PyPI; this file records their upstream licenses for release
review. Verify exact versions in `uv.lock` and the installed package metadata
before shipping a binary.

| Dependency | Purpose | License (upstream) |
|---|---|---|
| httpx / httpcore / h11 / h2 | HTTP client, HTTP/2 | BSD-3-Clause |
| starlette | ASGI application/routing | BSD-3-Clause |
| uvicorn | ASGI server | BSD-3-Clause |
| jinja2 / markupsafe | Dashboard templates | BSD-3-Clause |
| orjson | Fast JSON | Apache-2.0 / MIT |
| pydantic / pydantic-core | Config validation | MIT |
| typer / click | CLI | MIT / BSD-3-Clause |
| platformdirs | Per-user paths | MIT |
| certifi | TLS roots | MPL-2.0 |
| idna / sniffio / anyio | HTTP dependencies | BSD-3-Clause / MIT |
| tiktoken (optional) | Token estimation | MIT |
| google-re2 (optional) | ReDoS-resistant regex | BSD-3-Clause |
| hypothesis / pytest / ruff / mypy / coverage (dev) | Development and CI | MIT / Apache-2.0 / PSF |

No standalone binary build tool is used for distribution.

No provider SDK is bundled. Provider names are used descriptively only; see
`SPEC.md` §26 for the trademark note.
