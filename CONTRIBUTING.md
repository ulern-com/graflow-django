## Contributing to Graflow Django

Thanks for taking the time to improve this project! Please follow the guidelines below to keep the workflow smooth for everyone.

### 1. Code of Conduct

By participating you agree to abide by the [Code of Conduct](./CODE_OF_CONDUCT.md). Please report unacceptable behavior to the maintainers listed there.

### 2. Ways to Contribute

- Report bugs or request features via GitHub Issues.
- Improve documentation (README, docstrings, tutorials).
- Fix bugs, add tests, or build new features for the flows API, LangGraph integrations, or tooling.

### 3. Getting Started

```bash
git clone https://github.com/YOUR_ORG/graflow-django.git
cd graflow-django

python -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"
python manage.py migrate
```

Run the checks before committing:

```bash
ruff check .
black .
mypy graflow myflows
pytest
```

### 4. Style & Tooling

- **Python version:** 3.12+.
- **Formatting:** `black` (line length 100) and `ruff` for lint/import sorting.
- **Typing:** `mypy` with `django-stubs`; add type hints where practical.
- **Commits:** keep them focused and reference issues (e.g., `Fixes #123`) when applicable.

### 5. Pull Requests

1. Create a feature branch (`git checkout -b feature/cool-thing`).
2. Update docs/tests alongside code changes.
3. Ensure CI checks pass (`pytest`, `ruff`, `black`, `mypy`).
4. Describe the problem and solution clearly in the PR and link any related issues.

### 6. Releases

Maintainers should:

1. Update `pyproject.toml` with the new version.
2. Document notable changes in the release notes (GitHub Release).
3. Tag the release (`git tag vX.Y.Z && git push --tags`).

Thank you for helping make Graflow Django better! If you have questions, open a discussion or reach out via an issue.

