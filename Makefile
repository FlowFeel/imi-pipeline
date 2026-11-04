.PHONY: test bdd lint ci proof unit integration doi-prep doi-up doi-down doi-test clean

# ── Core ──

test:            ## Unit + integration tests
	uv run pytest tests/ -v --tb=short

bdd:             ## BDD behavioral proof
	uv run behave features/ --no-capture --format pretty

lint:            ## Ruff check + format
	uv run ruff check --fix src/ tests/ features/
	uv run ruff format src/ tests/ features/

# ── Gates (CI order) ──

ci: lint bdd test  ## Full CI: lint → behavioral proof → supporting tests

proof: bdd test    ## Proof sequence: contract first, then evidence

# ── Selective ──

unit:            ## Unit tests only
	uv run pytest tests/unit -v --tb=short

integration:     ## Integration tests only
	uv run pytest tests/integration -v --tb=short

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache dist/ reports/ testdata/wp-mu-plugins/

# ── DOI Harness (WP + MariaDB + Crossref stub) ──

COMPOSE_DOI := testdata/docker-compose.doi.yml
IMI_WP_PATH ?= ../imi-wordpress

doi-prep:         ## Ensure testdata/wp-mu-plugins/ exists (vendored in repo or staged from IMI_WP_PATH)
	@if [ -d "$(IMI_WP_PATH)/src/php" ]; then \
		mkdir -p testdata/wp-mu-plugins; \
		cp -r $(IMI_WP_PATH)/src/php/. testdata/wp-mu-plugins/; \
		cp $(IMI_WP_PATH)/wp-content/mu-plugins/*.php testdata/wp-mu-plugins/; \
	elif [ -d "testdata/wp-mu-plugins" ]; then \
		echo "Using vendored testdata/wp-mu-plugins"; \
	else \
		echo "Error: testdata/wp-mu-plugins not found and $(IMI_WP_PATH) unavailable" >&2; exit 1; \
	fi

doi-up: doi-prep  ## Boot the DOI harness stack and configure WP
	docker compose -f $(COMPOSE_DOI) up -d --wait
	python3 testdata/setup_wp.py

doi-test:         ## Run DOI lifecycle BDD scenarios against the stack
	WP_BASE_URL=http://localhost:$${WP_PORT:-18091} CROSSREF_STUB_URL=http://localhost:$${STUB_PORT:-18092} \
		uv run behave features/doi_preprint_lifecycle.feature --no-capture --format pretty

doi-down:         ## Tear down the DOI harness stack
	docker compose -f $(COMPOSE_DOI) down -v
