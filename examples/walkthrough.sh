#!/usr/bin/env bash
# The whole token lifecycle against a running template, with nothing but curl:
#
#   sign up -> JWT -> your API -> refresh -> log out -> log in again
#
# Every step checks the HTTP status it expects and stops if something is off,
# so CI runs this file as an end-to-end test.
#
# Usage:  examples/walkthrough.sh [base URL]      (default http://localhost:5566)
#         EMAIL=you@example.com PASSWORD=... examples/walkthrough.sh
set -euo pipefail

BASE="${1:-${BASE_URL:-http://localhost:5566}}"
APP="$BASE/_allauth/app/v1"   # allauth's API for apps: tokens, no cookies
API="$BASE/api"               # your own API
EMAIL="${EMAIL:-walkthrough-$(date +%s)-$RANDOM@example.com}"
PASSWORD="${PASSWORD:-correct-horse-battery-staple}"

BODY="$(mktemp)"
trap 'rm -f "$BODY"' EXIT

step() {
  if [ -t 1 ]; then printf '\n\033[1m%s\033[0m\n' "$*"; else printf '\n%s\n' "$*"; fi
}

# request METHOD URL [JSON body] [curl options...]  -> sets STATUS, body in $BODY
request() {
  local method="$1" url="$2" data="${3:-}"
  shift 3 2>/dev/null || shift $#
  local args=(-sS -X "$method" -o "$BODY" -w '%{http_code}' -H 'Accept: application/json')
  if [ -n "$data" ]; then
    args+=(-H 'Content-Type: application/json' --data "$data")
  fi
  STATUS="$(curl "${args[@]}" "$@" "$url")"
  printf '  %-6s %-46s -> %s\n' "$method" "${url#"$BASE"}" "$STATUS"
}

expect() {
  if [ "$STATUS" != "$1" ]; then
    printf '  expected HTTP %s; the response was:\n' "$1" >&2
    cat "$BODY" >&2
    echo >&2
    exit 1
  fi
}

# field NAME -> the first "NAME": "value" in the last response (enough for JWTs).
field() { grep -o "\"$1\": *\"[^\"]*\"" "$BODY" | head -n 1 | cut -d '"' -f 4; }
short() { printf '%s…' "${1:0:24}"; }
credentials() { printf '{"email": "%s", "password": "%s"}' "$EMAIL" "$PASSWORD"; }

step "1. Sign up as $EMAIL"
request POST "$APP/auth/signup" "$(credentials)"
expect 200
ACCESS="$(field access_token)"
REFRESH="$(field refresh_token)"
echo "  access token:  $(short "$ACCESS")"
echo "  refresh token: $(short "$REFRESH")"

step "2. Call your API with the access token"
request GET "$API/me" "" -H "Authorization: Bearer $ACCESS"
expect 200
echo "  $(cat "$BODY")"
request GET "$API/me" ""
expect 401
echo "  (no token, no entry)"

step "3. Refresh: a new access token and a new refresh token"
request POST "$APP/tokens/refresh" "{\"refresh_token\": \"$REFRESH\"}"
expect 200
OLD_REFRESH="$REFRESH"
ACCESS="$(field access_token)"
REFRESH="$(field refresh_token)"
echo "  new access token:  $(short "$ACCESS")"
request POST "$APP/tokens/refresh" "{\"refresh_token\": \"$OLD_REFRESH\"}"
expect 400
echo "  (the old refresh token works only once)"

step "4. Log out with the access token"
request DELETE "$APP/auth/session" "" -H "Authorization: Bearer $ACCESS"
expect 401
echo "  (401 here means: you are signed out now)"
request GET "$API/me" "" -H "Authorization: Bearer $ACCESS"
expect 401
request POST "$APP/tokens/refresh" "{\"refresh_token\": \"$REFRESH\"}"
expect 400
echo "  (both tokens of that session are dead)"

step "5. Log in again with the password"
request POST "$APP/auth/login" "$(credentials)"
expect 200
ACCESS="$(field access_token)"
request GET "$API/me" "" -H "Authorization: Bearer $ACCESS"
expect 200
request DELETE "$APP/auth/session" "" -H "Authorization: Bearer $ACCESS"
expect 401

step "Every step behaved as expected."
