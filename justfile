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

# Listen for messages addressed to human
listen thread_id="":
    uv run multiagent listen {{if thread_id != "" { "--thread-id " + thread_id } else { "" }}}

# Interactive chat session with an agent
chat agent thread_id="":
    uv run multiagent chat {{agent}} {{if thread_id != "" { "--thread-id " + thread_id } else { "" }}}

# Start all agents defined in agents.toml concurrently
start experiment="":
    uv run multiagent start {{if experiment != "" { "--experiment " + experiment } else { "" }}}

# Request graceful shutdown of running agents (all or by name)
stop agent="":
    uv run multiagent stop {{agent}}

# ── Release ────────────────────────────────────────────────────────────────

# Show the current package version
version:
    uv run multiagent version

# Bump the patch version in pyproject.toml
bump-patch:
    uv run python -c "from multiagent.version import bump_in_pyproject; print(f'Bumped to {bump_in_pyproject(\"patch\")}')"

# Bump the minor version in pyproject.toml
bump-minor:
    uv run python -c "from multiagent.version import bump_in_pyproject; print(f'Bumped to {bump_in_pyproject(\"minor\")}')"

# Bump the major version in pyproject.toml
bump-major:
    uv run python -c "from multiagent.version import bump_in_pyproject; print(f'Bumped to {bump_in_pyproject(\"major\")}')"

# Run full release: check, test, bump, commit, and tag
release part="minor" description="":
    #!/usr/bin/env bash
    set -euo pipefail
    # 1. Clean working tree
    if [ -n "$(git status --porcelain)" ]; then
        echo "Error: working tree not clean"; exit 1
    fi
    # 2. Quality gates
    just check && just test
    # 3. Bump
    just bump-{{part}}
    # 4. Commit + tag
    NEW_VERSION=$(uv run multiagent version)
    git add pyproject.toml
    git commit -m "chore(release): bump version to ${NEW_VERSION}"
    TAG_MSG="Release ${NEW_VERSION}"
    [ -n "{{description}}" ] && TAG_MSG="Release ${NEW_VERSION} — {{description}}"
    git tag -a "v${NEW_VERSION}" -m "${TAG_MSG}"
    echo "Released v${NEW_VERSION}"

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

# Show cost summary by experiment
costs:
    uv run python scripts/show_costs.py

# Show cost breakdown by agent
costs-by-agent:
    uv run python scripts/show_costs.py --by-agent

# Show cost breakdown by model
costs-by-model:
    uv run python scripts/show_costs.py --by-model

# Maintenance
clean:
    find . -type d -name __pycache__ -exec rm -rf {} +
    find . -type f -name "*.pyc" -delete
    rm -rf .coverage htmlcov/ .pytest_cache/ .ruff_cache/
