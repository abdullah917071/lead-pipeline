#!/usr/bin/env bash
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

echo -e "${GREEN}═ Lead Pipeline + Dograh AI Setup ═${NC}"

# 1. Prerequisites
echo -e "${YELLOW}[1/6] Prerequisites...${NC}"
command -v docker >/dev/null 2>&1 || { echo -e "${RED}Install Docker first${NC}"; exit 1; }
command -v docker compose >/dev/null 2>&1 || { echo -e "${RED}Need Docker Compose v2${NC}"; exit 1; }

# 2. .env
echo -e "${YELLOW}[2/6] Environment...${NC}"
[ ! -f .env ] && cp .env.example .env && echo "  Created .env — edit with real credentials!"

# 3. Dograh secrets
echo -e "${YELLOW}[3/6] Dograh config...${NC}"
if [ ! -f .env.dograh ]; then
    DJWT=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32)
    RPASS=$(python3 -c "import secrets;print(secrets.token_urlsafe(16))" 2>/dev/null || openssl rand -base64 16)
    PGPASS=$(python3 -c "import secrets;print(secrets.token_urlsafe(16))" 2>/dev/null || openssl rand -base64 16)
    cat > .env.dograh <<EOF
OSS_JWT_SECRET=${DJWT}
REDIS_PASSWORD=${RPASS}
POSTGRES_PASSWORD=${PGPASS}
POSTGRES_USER=dograh
POSTGRES_DB=dograh
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
S3_ENDPOINT=http://dograh-minio:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=dograh
EOF
    echo "  Created .env.dograh"
fi

# 4. Build
echo -e "${YELLOW}[4/6] Building...${NC}"
docker compose build orchestrator

# 5. Start
echo -e "${YELLOW}[5/6] Starting services...${NC}"
docker compose up -d postgres redis dograh-redis dograh-postgres dograh-minio
sleep 10
docker compose up -d dograh dograh-ui
sleep 30
docker compose up -d orchestrator

# 6. Seed
echo -e "${YELLOW}[6/6] Seeding DB...${NC}"
python3 scripts/seed_db.py 2>/dev/null || echo "  Run manually: python3 scripts/seed_db.py"

echo ""
echo -e "${GREEN}═ Setup Complete ═${NC}"
echo "  API:     http://localhost:9000"
echo "  Docs:    http://localhost:9000/docs"
echo "  Dograh:  http://localhost:3010"
echo ""
echo "  Next: Configure Twilio in Dograh, set up WA Business API, edit .env"
