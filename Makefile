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
