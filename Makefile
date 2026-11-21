.PHONY: up down logs test clean

# Start the whole stack: backend on :8000, frontend on :3000.
up:
	@test -f .env || { cp .env.example .env; echo ">> Created .env from .env.example - put real keys in LLM_API_KEYS."; }
	docker compose up --build -d --wait --wait-timeout 180
	@echo ""
	@echo "Backend : http://localhost:8000/health"
	@echo "Frontend: http://localhost:3000"

# Stop containers; the named volume (sqlite_data) is KEPT so history survives restarts.
down:
	docker compose down

logs:
	docker compose logs -f

test:
	cd backend && python -m pytest -q

# Destructive: also deletes the sqlite_data volume.
clean:
	docker compose down -v
