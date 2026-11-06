.PHONY: help install dev migrate seed stop contracts build
help:
	@echo "install: dependencies; dev: isolated Compose stack; migrate/seed: explicit data setup; stop: preserve volumes; contracts: regenerate DTOs; build: compile images"
install:
	pnpm install --frozen-lockfile
	cd services/backend && go mod download
	cd services/runtime && uv sync --frozen
build:
	docker compose build backend runtime web demo-mcp
dev: build
	docker compose up -d --wait postgres
	$(MAKE) migrate seed
	docker compose up -d --wait backend runtime web demo-mcp
migrate:
	docker compose exec -T postgres sh -c 'psql -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -f /opt/phase1.sql'
	docker compose run --rm --no-deps backend migrate
	docker compose run --rm --no-deps runtime python -m app.migrate
seed:
	docker compose run --rm --no-deps backend seed
stop:
	docker compose down
contracts:
	python scripts/generate-contracts.py

.PHONY: verify-mock
verify-mock:
	pwsh -NoProfile -File scripts/verify-mock.ps1 -Authorized
