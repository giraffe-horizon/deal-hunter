.PHONY: install test lint typecheck verify-example

install:
	python -m pip install -e ".[dev]"

test:
	python -m pytest tests/ -v --tb=short

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy --ignore-missing-imports deal_hunter.py sources/ filters/ notifiers/ utils/

verify-example:
	python deal_hunter.py --profile headphones --verify
