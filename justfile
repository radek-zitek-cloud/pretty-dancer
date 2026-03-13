# Default — list all tasks
default:
    @just --list

# Setup
setup:
    uv sync --all-extras
    uv run pre-commit install

# Quality
lint:
    uv run ruff check src/ tests/

format:
    uv run ruff format src/ tests/
    uv run ruff check --fix src/ tests/

typecheck:
    uv run pyright src/ tests/

check: lint typecheck

# Testing
test:
    uv run pytest tests/unit/ -v

test-coverage:
    uv run pytest tests/unit/ --cov=src/multiagent --cov-report=term-missing --cov-fail-under=80

test-integration:
    uv run pytest tests/integration/ -v -m integration

test-all:
    uv run pytest tests/ -v

# Running
run:
    uv run multiagent

# Maintenance
clean:
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
    rm -rf .coverage htmlcov/ .pytest_cache/ .ruff_cache/
