.PHONY: help install install-offline doctor index test test-e2e demo serve generate lint clean

PY ?= python3
export PYTHONPATH := src

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'

install:  ## install runtime + dev deps and the chromium bundle
	$(PY) -m pip install -e ".[dev,visual]"
	$(PY) -m playwright install chromium

install-offline:  ## install from a local wheelhouse (no network)
	$(PY) -m pip install --no-index --find-links=wheelhouse -e ".[dev,visual]"

doctor:  ## check offline readiness
	$(PY) -m forkable_ai_agent doctor

index:  ## build the local RAG index
	$(PY) -m forkable_ai_agent index

test:  ## run everything except the real-browser suite
	$(PY) -m pytest -m "not e2e"

test-e2e:  ## run the real-browser suite
	$(PY) -m pytest -m e2e

demo:  ## login flow on the stable UI, then on the refactored one
	$(PY) -m forkable_ai_agent demo

serve:  ## serve the offline demo target
	$(PY) -m forkable_ai_agent serve

generate:  ## regenerate the example standalone test
	$(PY) -m forkable_ai_agent generate --file examples/nl_specs/login.txt --out tests/generated

lint:
	ruff check src tests

clean:
	rm -rf .forkable .pytest_cache **/__pycache__ tests/generated
