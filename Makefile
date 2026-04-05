.PHONY: run test lint build clean install

run:
	uvicorn bookforge.main:app --reload --port 8000

test:
	pytest tests/ -v --cov=bookforge --cov-report=term-missing

test-unit:
	pytest tests/ -v --ignore=tests/test_integration

test-integration:
	pytest tests/test_integration/ -v

lint:
	ruff check bookforge/ tests/
	ruff format --check bookforge/ tests/

format:
	ruff format bookforge/ tests/

install:
	pip install -e ".[dev]"

build:
	docker build -t bookforge .

up:
	docker-compose up

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .coverage htmlcov/ dist/ .pytest_cache/
	rm -rf data/jobs/*/temp/
