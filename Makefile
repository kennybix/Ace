API=apps/api

db-up:
	docker compose -f infra/docker-compose.yml up -d --wait

db-down:
	docker compose -f infra/docker-compose.yml down

migrate:
	cd $(API) && uv run python -c "from ace_api.db.migrate import run_migrations; print(run_migrations())"

dev: db-up migrate
	cd $(API) && uv run uvicorn ace_api.main:app --host 0.0.0.0 --port 8040 --reload

test:
	cd $(API) && uv run pytest -q

eval:
	cd $(API) && uv run pytest -q -m eval

accelerate:
	cd $(API) && uv run ace accelerate ../../resources

smoke:
	cd $(API) && uv run ace llm-smoke
