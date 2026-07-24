#!/usr/bin/env bash
set -euo pipefail

APP_NAME="tg-marketing-system"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/backend/.env"
ENV_EXAMPLE="$PROJECT_DIR/backend/.env.example"
COMPOSE_ENV_FILE="$PROJECT_DIR/.env"
COMPOSE_ENV_EXAMPLE="$PROJECT_DIR/.env.example"

info() {
  printf '\033[1;34m[INFO]\033[0m %s\n' "$1"
}

warn() {
  printf '\033[1;33m[WARN]\033[0m %s\n' "$1"
}

fail() {
  printf '\033[1;31m[ERROR]\033[0m %s\n' "$1"
  exit 1
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

install_docker_if_needed() {
  if need_cmd docker; then
    info "Docker already installed."
  else
    info "Installing Docker..."
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg
    . /etc/os-release
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" |
      sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  fi

  sudo systemctl enable docker >/dev/null 2>&1 || true
  sudo systemctl start docker

  if ! docker compose version >/dev/null 2>&1; then
    fail "Docker Compose plugin is not available."
  fi
}

prepare_env() {
  if [ ! -f "$COMPOSE_ENV_FILE" ]; then
    info "Creating .env from .env.example"
    cp "$COMPOSE_ENV_EXAMPLE" "$COMPOSE_ENV_FILE"
  fi

  if [ ! -f "$ENV_FILE" ]; then
    info "Creating backend/.env from backend/.env.example"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    warn "Please edit backend/.env and set TELEGRAM_API_ID, TELEGRAM_API_HASH and AUTH_SECRET before production use."
  fi

  mkdir -p "$PROJECT_DIR/backend/static"
  touch "$PROJECT_DIR/backend/static/.gitkeep"
}

deploy() {
  cd "$PROJECT_DIR"
  info "Pulling latest code if this is a git repository..."
  if [ -d .git ]; then
    git pull --ff-only || warn "git pull failed or local changes exist; continuing with current files."
  fi

  info "Building and starting Docker services..."
  sudo --preserve-env=SESSION_WORKER_COUNT "$PROJECT_DIR/deploy/compose-up.sh"

  info "Service status:"
  sudo docker compose ps

  info "Deployment finished."
  printf '\nOpen: http://%s:%s/login\n' "$(hostname -I | awk '{print $1}')" "${FRONTEND_PORT:-8080}"
  printf 'Default users: root/root and test/test\n'
}

main() {
  if [ "$(uname -s)" != "Linux" ]; then
    fail "This script is intended for Ubuntu/Linux servers."
  fi

  install_docker_if_needed
  prepare_env
  deploy
}

main "$@"
