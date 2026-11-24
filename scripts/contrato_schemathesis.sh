#!/usr/bin/env bash
# Pruebas de contrato generadas con schemathesis contra el esquema OpenAPI (M4).
# Requisitos: pip install schemathesis ; servidor corriendo (python manage.py runserver).
# Uso: ./scripts/contrato_schemathesis.sh <usuario> <contraseña> [http://localhost:8000]
set -euo pipefail
USUARIO="${1:?usuario}"; CLAVE="${2:?contraseña}"; BASE="${3:-http://localhost:8000}"

TOKEN=$(curl -s -X POST "$BASE/api/v1/auth/token/" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USUARIO\",\"password\":\"$CLAVE\"}" \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access"])')

schemathesis run "$BASE/api/v1/schema/?format=json" \
  --base-url "$BASE" \
  -H "Authorization: Bearer $TOKEN" \
  --checks all
