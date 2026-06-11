PYTHON ?= python3
export PYTHONPATH := src

.PHONY: test eval gate drift demo scan verify

test:
	$(PYTHON) -m unittest discover -s tests -v

eval:
	$(PYTHON) scripts/run_eval.py --summaries eval/baselines/baseline

gate:
	$(PYTHON) scripts/run_regression_gate.py --candidate eval/baselines/baseline

drift:
	@echo "expecting the gate to FAIL on the drifted set:"
	@if $(PYTHON) scripts/run_regression_gate.py --candidate eval/baselines/drifted; then \
		echo "ERROR: gate passed on drifted summaries; the regression gate is broken"; exit 1; \
	else \
		echo "OK: gate correctly rejected the drifted summaries"; \
	fi

demo:
	$(PYTHON) scripts/run_judge_demo.py

scan:
	$(PYTHON) scripts/public_safety_scan.py --term "$${BANNED_TERM:-}"

verify: test gate drift demo scan
