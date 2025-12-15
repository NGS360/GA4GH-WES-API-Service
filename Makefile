test:
	uv sync --extra dev
	uv run pytest --cov=src --cov-report=html

run:
	uv run python -m src.wes_service.main

lint:
	uv run flake8 .
