.DEFAULT_GOAL := help

BRIDGE := bridge-server
HOST ?= 127.0.0.1
PORT ?= 8000

.PHONY: help setup env run login login-paytmmoney login-indmoney health clean

help:
	@echo "make setup            - create bridge-server/.venv and install dependencies"
	@echo "make env              - create bridge-server/.env from .env.example (never overwrites an existing one)"
	@echo "make run              - start the bridge-server dev server on http://$(HOST):$(PORT) (reload on)"
	@echo "make login            - refresh BOTH PaytmMoney and INDmoney access tokens, one restart at the end"
	@echo "make login-paytmmoney - refresh just the PaytmMoney access token"
	@echo "make login-indmoney   - refresh just the INDmoney (INDstocks) access token"
	@echo "make health           - curl /api/health on a running server"
	@echo "make clean            - remove __pycache__ and the local SQLite DB (never touches .env)"

setup:
	cd $(BRIDGE) && python3 -m venv .venv
	cd $(BRIDGE) && .venv/bin/pip install --upgrade pip -q
	cd $(BRIDGE) && .venv/bin/pip install -r requirements.txt

env:
	cd $(BRIDGE) && test -f .env || cp .env.example .env

run:
	cd $(BRIDGE) && .venv/bin/uvicorn app.main:app --reload --host $(HOST) --port $(PORT)

login:
	cd $(BRIDGE) && .venv/bin/python scripts/login.py

login-paytmmoney:
	cd $(BRIDGE) && .venv/bin/python scripts/paytmmoney_login.py

login-indmoney:
	cd $(BRIDGE) && .venv/bin/python scripts/indmoney_login.py

health:
	curl -s http://$(HOST):$(PORT)/api/health && echo

clean:
	find $(BRIDGE)/app -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -f $(BRIDGE)/vantage.db
