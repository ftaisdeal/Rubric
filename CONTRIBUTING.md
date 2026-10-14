# Contributing to Rubric

Thanks for your interest! Bug reports, ideas, and pull requests are welcome.

## Reporting bugs and suggesting features

Open an issue using one of the templates. For bugs, include your OS, Python version, and steps to reproduce.

## Development setup

```sh
git clone https://github.com/ftaisdeal/Rubric.git
cd Rubric
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
.venv/bin/python -m rubric
```

## Pull requests

1. Fork the repo and create a branch from `main`.
2. Keep changes focused, and match the style of the surrounding code.
3. Add or update tests in `tests/` for any change to scoring or storage logic.
4. Make sure `python -m pytest` passes.
5. Describe what changed and why in the PR, and add a line to `CHANGELOG.md` under Unreleased.

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
