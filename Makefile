.PHONY: test bdd lint ci proof unit integration clean

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
	rm -rf .pytest_cache .ruff_cache dist/ reports/
