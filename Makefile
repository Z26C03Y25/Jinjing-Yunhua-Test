.PHONY: up down validate test
up:
	sh scripts/bootstrap.sh
down:
	docker compose down --remove-orphans
validate: up
	python3 validation/run_validation.py --url http://127.0.0.1:$${WEB_PORT:-80}
test:
	python3 -m unittest discover -s backend -v
	python3 -m unittest discover -s validation -v
