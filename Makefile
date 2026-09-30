.PHONY: up redis model seed serve build dev eval memory-eval context-export context-seed context-check context-test context-migrate context-publish shipment-delivered shipment-delayed fmt lint test down

SHOP_SCRIPTS = scripts/setup_shop_playbook.py scripts/evaluate_shop_memory.py

up: redis model build ## Prepare once, then open the comparison app
	uv run python -m seed.load --if-needed
	uv run python -m app.runtime --port $(or $(PORT),8000)

redis: ## Preserve an existing service container and its data
	docker compose up -d --no-recreate --wait

model: ## Download the pinned local model once; verify cached files afterwards
	uv run python -m app.embeddings

seed: ## Bootstrap bundled source records; refuse to overwrite managed live catalogues
	uv run python -m seed.load

serve: ## Start the prepared backend and built frontend
	uv run python -m app.runtime --port $(or $(PORT),8000)

build:
	npm --prefix web ci
	npm --prefix web run build

dev: ## Frontend dev server; backend uses port 8000
	npm --prefix web run dev

eval:
	uv run python -m eval.run --check

memory-eval: ## Write isolated fictional fixtures and measure real RAM extraction
	uv run python -m scripts.evaluate_shop_memory --timeout 420

context-export: ## Print Context Retriever entity schema and eleven fixture records
	uv run --extra context-retriever python -m scripts.check_context_retriever export

context-seed: ## Seed only isolated smoke-test JSON keys into CTX_REDIS_URL
	uv run --extra context-retriever python -m scripts.check_context_retriever seed

context-check: ## Check the configured service using two scoped agent keys
	uv run --extra context-retriever python -m scripts.check_context_retriever check

context-migrate: ## Upgrade known fictional records to the shipment demo; reject conflicts
	uv run --extra context-retriever python -m scripts.setup_shipment_demo migrate

context-publish: ## Publish the linked shipment model to the existing demo service
	uv run --extra context-retriever python -m scripts.setup_shipment_demo publish

shipment-delivered: ## Replay the delivered snapshot for Alex's fictional microphone
	uv run --extra context-retriever python -m scripts.setup_shipment_demo delivered

shipment-delayed: ## Reset the fictional microphone to the deck's depot-delay snapshot
	uv run --extra context-retriever python -m scripts.setup_shipment_demo delayed

context-test: ## Test service and chat contracts; TEST_REDIS_URL enables JSON integration
	uv run --extra context-retriever pytest tests/test_context_retriever.py tests/test_shop_context_retriever.py tests/test_shop_context_retriever_api.py tests/test_shop_mcp.py tests/test_shop_shipments.py tests/test_shop_shipment_api.py tests/test_shipment_setup.py -q
	uv run --extra context-retriever ruff check seed/shop_context.py scripts/check_context_retriever.py scripts/setup_shipment_demo.py tests/test_context_retriever.py tests/test_shop_shipments.py tests/test_shop_shipment_api.py tests/test_shipment_setup.py
	uv run --extra context-retriever mypy seed/shop_context.py scripts/check_context_retriever.py scripts/setup_shipment_demo.py

fmt:
	uv run ruff format app seed/load.py eval tests scripts/prepare_cameras.py scripts/search_load.py $(SHOP_SCRIPTS)
	uv run ruff check --fix app seed/load.py eval tests scripts/prepare_cameras.py scripts/search_load.py $(SHOP_SCRIPTS)

lint:
	uv run ruff check app seed/load.py eval tests scripts/prepare_cameras.py scripts/search_load.py $(SHOP_SCRIPTS)
	uv run mypy app seed/load.py eval scripts/prepare_cameras.py scripts/search_load.py $(SHOP_SCRIPTS)

test:
	uv run pytest -q

down: ## Stop the container without deleting data
	docker compose stop
