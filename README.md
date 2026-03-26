# balbes

Clean Python starter project with a `src` layout and CLI entry point.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
pre-commit install
balbes
pytest
```

## Developer workflow

Run all pre-commit hooks manually:

```bash
pre-commit run --all-files
```

## Project structure

- `src/balbes` - package source code
- `tests` - test suite
- `pyproject.toml` - project and tooling config
