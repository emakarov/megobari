# Testing and Linting

## Running

```bash
uv run pytest                                    # 168+ tests, 95%+ coverage required
uv run flake8 src/ tests/                        # max-line-length=99
uv run isort --check src/ tests/                 # profile=black
uv run pydocstyle --config=pyproject.toml src/   # google convention
```

## Rules

- Coverage threshold: 95% (`--cov-fail-under=95`)
- All source files must have module docstrings (D100 is enforced)
- Tests use `pytest-asyncio` with `asyncio_mode = "auto"` — no need for `@pytest.mark.asyncio`
- Test files are exempt from docstring checks (D100-D104 ignored via `per-file-ignores`)

## Code style

- Max line length: 99
- Imports sorted with isort (black profile)
- Google-style docstrings (pydocstyle)
- Type hints throughout (`from __future__ import annotations`)
- Prefer editing existing files over creating new ones
- Keep responses and messages concise — this runs on mobile

## Test patterns

- `_make_update()` and `_make_context()` helpers create mock Telegram objects
- Streaming tests must invoke the callback via `side_effect` with a `fake_send` function
- All `send_to_claude` mocks must accept `on_text_chunk` and `on_tool_use` kwargs
- `conftest.py` provides the `session_manager` fixture (tmp_path-based)
