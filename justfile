# Graflow Django Development Commands
# Install just: https://github.com/casey/just

# Default recipe - show help
default:
    just --list

# Format code with black
format:
    black .

# Lint code with ruff
lint:
    ruff check .

# Fix linting issues automatically
lint-fix:
    ruff check --fix .

# Type check with mypy
type-check:
    mypy graflow myflows

# Run all checks (lint + type-check)
check:
    just lint
    just type-check

# Run tests
test:
    pytest

# Run tests with coverage
test-cov:
    pytest --cov=graflow --cov-report=html --cov-report=term

# Run tests with coverage using Docker Postgres defaults (for sandboxed environments)
sandbox-test-cov:
    DB_USER=postgres DB_PASSWORD=postgres DB_HOST=127.0.0.1 DB_PORT=5432 DB_NAME=myflows pytest --cov=graflow --cov-report=html --cov-report=term

# Clean up temporary files
clean:
    find . -type f -name "*.pyc" -delete
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
    find . -type d -name ".coverage" -exec rm -f {} + 2>/dev/null || true
    rm -rf htmlcov

# Django management commands
migrate:
    python manage.py migrate

makemigrations:
    python manage.py makemigrations

runserver:
    python manage.py runserver

shell:
    python manage.py shell
