.PHONY: dev run fmt lint migrate

dev:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt && python -m app.main

run:
	. .venv/bin/activate && python -m app.main

fmt:
	. .venv/bin/activate && black .
	. .venv/bin/activate && ruff check --fix .

lint:
	. .venv/bin/activate && ruff check .