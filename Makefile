.PHONY: up down logs build

up:
	docker compose up --build -d
	@echo "Backend:  http://localhost:8000"
	@echo "Frontend: http://localhost:3000"

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build
