.DEFAULT_GOAL := help
.PHONY: help test diagram diagram-check docs docs-build

help: ## List the targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

test: ## Run the tests
	python3 -m unittest discover -s tests

diagram: ## Render docs/assets/diagrams/*.d2 to SVG and PNG (needs Docker)
	docs/assets/diagrams/render.sh

# The SVGs are compared byte for byte. The PNGs are rasterized from them and differ by a few bytes
# between CPU architectures, so only their presence is checked.
diagram-check: diagram ## Fail if the committed diagrams differ from their sources
	@git diff --exit-code --stat -- 'docs/assets/diagrams/*.svg' || { echo "Run make diagram and commit the result."; exit 1; }
	@for f in docs/assets/diagrams/[!_]*.d2; do git ls-files --error-unmatch "$${f%.d2}.png" >/dev/null 2>&1 || { echo "$${f%.d2}.png is not committed"; exit 1; }; done
	@git checkout -- 'docs/assets/diagrams/*.png'

.venv-docs/bin/properdocs: docs/requirements.txt
	python3 -m venv .venv-docs && .venv-docs/bin/pip install -q --require-hashes -r docs/requirements.txt
	@touch $@

docs: .venv-docs/bin/properdocs ## Preview the docs site on http://127.0.0.1:8000
	.venv-docs/bin/properdocs serve

docs-build: .venv-docs/bin/properdocs ## Build the docs site the way CI does (strict)
	.venv-docs/bin/properdocs build --strict --site-dir site
