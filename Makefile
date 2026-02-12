deploy:
	uv lock
	uv pip compile pyproject.toml -o requirements.txt
	git add requirements.txt .ebextensions/
	eb deploy --staged
	git restore --staged requirements.txt .ebextensions/

test:
	uv sync --extra dev
	uv run pytest --cov=src --cov-report=html

run:
	uv run python -m src.wes_service.main

lint:
	uv run flake8 .

# Alembic migration commands
migrate-upgrade:
	uv run alembic upgrade head

migrate-new:
	uv run alembic revision --autogenerate -m "$(message)"

migrate-rollback:
	uv run alembic downgrade -1

# Create a new empty migration file
migrate-empty:
	uv run alembic revision -m "$(message)"

# Show current revision
migrate-current:
	uv run alembic current