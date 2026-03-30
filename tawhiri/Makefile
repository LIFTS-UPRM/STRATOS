.PHONY: up down logs rebuild status test

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

rebuild:
	docker compose build --no-cache

status:
	docker compose ps

test:
	bash scripts/test_prediction.sh
