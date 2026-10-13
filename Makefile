PY    ?= python3
VENV  ?= .venv
BIN    = $(VENV)/bin

.PHONY: setup test lint format benchmark benchmark-smoke analyze verify demo clean

setup:            ## create the venv and install the package + dev tools (pinned)
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt
	$(BIN)/pip install -e ".[dev]"

test:             ## run the test suite (~30 s)
	$(BIN)/pytest -q

lint:             ## ruff lint + format check
	$(BIN)/ruff check src tests benchmarks
	$(BIN)/ruff format --check src tests benchmarks

format:
	$(BIN)/ruff check --fix src tests benchmarks
	$(BIN)/ruff format src tests benchmarks

benchmark:        ## full benchmark grid (~45 min on 4 cores) -> results/
	$(BIN)/python benchmarks/run_benchmark.py --config benchmarks/config.yaml

benchmark-smoke:  ## tiny grid (~10 s) -> results/smoke/
	$(BIN)/python benchmarks/run_benchmark.py --config benchmarks/smoke.yaml

analyze:          ## rebuild results/summary.* and plots from results/benchmark.csv
	$(BIN)/python benchmarks/run_benchmark.py --config benchmarks/config.yaml --analyze-only

verify:           ## re-generate every instance and re-validate every stored solution
	$(BIN)/python benchmarks/run_benchmark.py --verify results/solutions.jsonl --csv results/benchmark.csv

demo:             ## generate a 50-stop instance and compare all methods (~45 s)
	mkdir -p results/demo
	$(BIN)/route-opt generate --n 50 --type RC --seed 1 --tw loose --out results/demo/rc50.json
	$(BIN)/route-opt compare --instance results/demo/rc50.json --time-limit 30 --plot results/demo/rc50_greedy_vs_ilp.png

clean:
	rm -rf results/smoke results/demo .pytest_cache .ruff_cache build dist src/*.egg-info
