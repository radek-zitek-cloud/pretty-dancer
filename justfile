# set shell := ["powershell", "-Command"]

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

# ── Application ────────────────────────────────────────────────────────────

# Run a named agent (polls for messages until interrupted)
run agent experiment="":
    uv run multiagent run {{agent}} {{if experiment != "" { "--experiment " + experiment } else { "" }}}

# Inject a message into the transport for a named agent
send agent body:
    uv run multiagent send {{agent}} "{{body}}"

# Start all agents defined in agents.toml concurrently
start experiment="":
    uv run multiagent start {{if experiment != "" { "--experiment " + experiment } else { "" }}}

# ── Database ───────────────────────────────────────────────────────────────

# Show last N messages across all agents (default 20)
db-tail n="20":
    sqlite3 data/agents.db "SELECT id, from_agent, to_agent, substr(body,1,60) as body, processed_at FROM messages ORDER BY created_at DESC LIMIT {{n}};"

# Show all pending (unprocessed) messages by agent
db-pending:
    sqlite3 data/agents.db "SELECT to_agent, count(*) as pending FROM messages WHERE processed_at IS NULL GROUP BY to_agent;"

# Show per-agent message counts and last activity
db-agents:
    sqlite3 data/agents.db "SELECT to_agent, count(*) as total, sum(processed_at IS NOT NULL) as done, max(created_at) as last_seen FROM messages GROUP BY to_agent;"

# Clear all messages from the transport database
db-clear:
    sqlite3 data/agents.db "DELETE FROM messages;"

# ── Inspection scripts ──────────────────────────────────────────────────────

# Show a conversation thread from SQLite, formatted with rich
thread thread_id:
    uv run python scripts/show_thread.py {{thread_id}}

# Browse all conversation threads interactively
threads:
    uv run python scripts/browse_threads.py

# Show a summary of a single run log file
run-summary log_file:
    uv run python scripts/show_run.py {{log_file}}

# Compare two run log files side by side
compare log1 log2:
    uv run python scripts/compare_runs.py {{log1}} {{log2}}

# List all run log files
runs:
    @ls -lt logs/*.jsonl 2>/dev/null || echo "No run logs found in logs/"

# Maintenance
clean:
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
    rm -rf .coverage htmlcov/ .pytest_cache/ .ruff_cache/
