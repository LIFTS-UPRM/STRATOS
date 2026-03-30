#!/usr/bin/env bash
# test_prediction.sh — smoke test the Tawhiri predictor API
# Usage: bash scripts/test_prediction.sh [BASE_URL]
# Defaults to http://localhost:8100 if TAWHIRI_BASE_URL is not set.
#
# Exit codes:
#   0 — server is up and API is responding (even if no dataset is loaded yet)
#   1 — server is unreachable or returned non-JSON

set -euo pipefail

BASE_URL="${1:-${TAWHIRI_BASE_URL:-http://localhost:8100}}"
ENDPOINT="${BASE_URL}/api/v1/"

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

HTTP_CODE=$(curl -s -o /tmp/tawhiri_response.json -w "%{http_code}" "${URL}" 2>/dev/null || echo "000")

if [ "${HTTP_CODE}" = "000" ]; then
  echo "FAIL — server unreachable at ${BASE_URL}"
  exit 1
fi

if ! python3 -c "import json,sys; json.load(open('/tmp/tawhiri_response.json'))" 2>/dev/null; then
  echo "FAIL — response is not valid JSON (HTTP ${HTTP_CODE})"
  cat /tmp/tawhiri_response.json
  exit 1
fi

ERROR_TYPE=$(python3 -c "
import json
data = json.load(open('/tmp/tawhiri_response.json'))
print(data.get('error', {}).get('type', ''))
" 2>/dev/null || echo "")

if [ "${HTTP_CODE}" = "200" ]; then
  STAGE_COUNT=$(python3 -c "
import json
data = json.load(open('/tmp/tawhiri_response.json'))
print(len(data['prediction']))
" 2>/dev/null || echo "unknown")
  echo "PASS — HTTP 200, prediction returned with ${STAGE_COUNT} stage(s)"

elif [ "${ERROR_TYPE}" = "InvalidDatasetException" ]; then
  echo "PASS (no data) — API is up and responding. No GFS forecast dataset loaded yet."
  echo "       Run the downloader to fetch NOAA data, then re-test with a recent launch_datetime."

else
  echo "FAIL — HTTP ${HTTP_CODE}"
  cat /tmp/tawhiri_response.json
  exit 1
fi
