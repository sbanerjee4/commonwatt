.PHONY: setup demo test

setup:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

test:
	.venv/bin/pytest

demo:
	SMS_PROVIDER=simulated .venv/bin/python -m scripts.demo_sms
