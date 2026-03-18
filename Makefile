VERSION   := 0.3.3
COMPOSE   := docker compose

.PHONY: deploy rebuild restart start stop logs clean nuke help

deploy:
	@echo "==> NumsBot $(VERSION) — rebuilding from current files"
	$(COMPOSE) down
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d
	@echo "==> Done. Run 'make logs' to follow output."

rebuild:
	$(COMPOSE) down
	$(COMPOSE) up -d --build
	@echo "==> Done. Run 'make logs' to follow output."

restart:
	$(COMPOSE) down
	$(COMPOSE) up -d
	@echo "==> Done. Run 'make logs' to follow output."

start:
	$(COMPOSE) up -d

stop:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

clean:
	$(COMPOSE) down --rmi local
	@echo "==> Containers and images removed. Data volumes untouched."

nuke:
	@echo "WARNING: This permanently deletes places.json and all bot data."
	@read -p "Type 'yes' to confirm: " confirm && [ "$$confirm" = "yes" ]
	$(COMPOSE) down -v --rmi local
	@echo "==> Everything removed."

help:
	@echo ""
	@echo "  NumsBot $(VERSION) — available targets:"
	@echo ""
	@echo "  make deploy    — clean rebuild from current files, start"
	@echo "  make rebuild   — faster rebuild using Docker cache"
	@echo "  make restart   — stop and start without rebuilding"
	@echo "  make start     — start container"
	@echo "  make stop      — stop container"
	@echo "  make logs      — tail logs"
	@echo "  make clean     — remove containers/images, keep data"
	@echo "  make nuke      — remove everything including data (DESTRUCTIVE)"
	@echo ""
