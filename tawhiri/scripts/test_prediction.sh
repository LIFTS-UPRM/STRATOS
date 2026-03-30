#!/usr/bin/env bash
# test_prediction.sh — smoke test the Tawhiri predictor API
# Usage: bash scripts/test_prediction.sh [BASE_URL]
# Defaults to http://localhost:8000 if TAWHIRI_BASE_URL is not set.

set -euo pipefail

BASE_URL="${1:-${TAWHIRI_BASE_URL:-http://localhost:8100}}"
ENDPOINT="${BASE_URL}/api/v1/"

# Sample params — a standard ascent from Cambridge, UK
PARAMS=(
  "launch_latitude=52.2135"
  "launch_longitude=0.0964"
  "launch_altitude=0"
  "launch_datetime=2000-01-01T12:00:00Z"
  "ascent_rate=5"
  "burst_altitude=28000"
  "descent_rate=5"
  "profile=standard_profile"
  "version=1"
)

QUERY_STRING=$(IFS='&'; echo "${PARAMS[*]}")
URL="${ENDPOINT}?${QUERY_STRING}"

echo "Testing Tawhiri predictor at: ${BASE_URL}"
echo "GET ${ENDPOINT}"
echo ""

HTTP_CODE=$(curl -s -o /tmp/tawhiri_response.json -w "%{http_code}" "${URL}")

if [ "${HTTP_CODE}" -ne 200 ]; then
  echo "FAIL — HTTP ${HTTP_CODE}"
  cat /tmp/tawhiri_response.json
  exit 1
fi

if ! grep -q '"prediction"' /tmp/tawhiri_response.json; then
  echo "FAIL — response does not contain 'prediction' key"
  cat /tmp/tawhiri_response.json
  exit 1
fi

STAGE_COUNT=$(python3 -c "
import json, sys
data = json.load(open('/tmp/tawhiri_response.json'))
print(len(data['prediction']))
" 2>/dev/null || echo "unknown")

echo "PASS — HTTP 200, prediction returned with ${STAGE_COUNT} stage(s)"
