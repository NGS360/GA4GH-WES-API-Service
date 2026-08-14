# Targets run from the repo root. This is a uv workspace: the root is not a
# package, so commands that act on one distribution name it with --package, and
# `uv sync` without one resolves the whole workspace into a single shared .venv.

# Alembic reads script_location and prepend_sys_path relative to the working
# directory, so migrations run from the server package rather than the root.
SERVICE_DIR := packages/wes-service

build:
	uv lock
	uv pip compile $(SERVICE_DIR)/pyproject.toml -o requirements.txt
	git add requirements.txt uv.lock
	git commit -m "Update requirements.txt/uv.lock" || echo "No changes to commit"

# One suite across the workspace. The server package's dev extra pulls in
# wes-client, which tests/contract needs.
test:
	uv sync --all-packages --all-extras
	uv run pytest

lint:
	uv run flake8 packages/ scripts/

run:
	uv run python -m wes_service.main

# Alembic migration commands
migrate-upgrade:
	cd $(SERVICE_DIR) && uv run alembic upgrade head

migrate-new:
	cd $(SERVICE_DIR) && uv run alembic revision --autogenerate -m "$(message)"

migrate-rollback:
	cd $(SERVICE_DIR) && uv run alembic downgrade -1

# Create a new empty migration file
migrate-empty:
	cd $(SERVICE_DIR) && uv run alembic revision -m "$(message)"

# Show current revision
migrate-current:
	cd $(SERVICE_DIR) && uv run alembic current
