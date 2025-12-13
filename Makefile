test:
	uv sync --extra dev
	uv run pytest --cov=src --cov-report=html

lint:
	uv run flake8 .
