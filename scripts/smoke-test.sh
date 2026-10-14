#!/usr/bin/env bash
set -euo pipefail

compose=(docker compose)

echo "Bayora container status"
"${compose[@]}" ps

echo "Waiting for the control plane"
ready=0
for attempt in $(seq 1 30); do
  if "${compose[@]}" exec -T bayora python3 -c 'import urllib.request; urllib.request.urlopen("http://127.0.0.1:8080/healthz", timeout=2).read()' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  echo "Bayora did not become healthy" >&2
  exit 1
fi

admin_password="${BAYORA_SMOKE_ADMIN_PASSWORD:-${BAYORA_BOOTSTRAP_ADMIN_PASSWORD:-}}"
red_password="${BAYORA_SMOKE_RED_PASSWORD:-${BAYORA_BOOTSTRAP_RED_PASSWORD:-$admin_password}}"
auditor_password="${BAYORA_SMOKE_AUDITOR_PASSWORD:-${BAYORA_BOOTSTRAP_AUDITOR_PASSWORD:-$admin_password}}"
if [ -z "$admin_password" ] || [ -z "$red_password" ] || [ -z "$auditor_password" ]; then
  echo "Set BAYORA_SMOKE_ADMIN_PASSWORD, BAYORA_SMOKE_RED_PASSWORD, and BAYORA_SMOKE_AUDITOR_PASSWORD (or the matching bootstrap variables) before running this check." >&2
  exit 1
fi

"${compose[@]}" exec -T \
  -e "BAYORA_SMOKE_ADMIN_PASSWORD=$admin_password" \
  -e "BAYORA_SMOKE_RED_PASSWORD=$red_password" \
  -e "BAYORA_SMOKE_AUDITOR_PASSWORD=$auditor_password" \
  bayora python3 - <<'PY'
import json
import os
from http.cookiejar import CookieJar
from urllib.request import Request, urlopen
from urllib.request import HTTPCookieProcessor, build_opener

base = "http://127.0.0.1:8080"
def login(username, password):
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    request = Request(
        base + "/api/v1/auth/login",
        data=json.dumps({"username": username, "password": password}).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with opener.open(request) as response:
        assert response.status == 200
    return opener

def get(opener, path):
    with opener.open(Request(base + path)) as response:
        return json.load(response)

assert json.load(urlopen(base + "/healthz"))["status"] == "ok"
admin = login("security-admin", os.environ["BAYORA_SMOKE_ADMIN_PASSWORD"])
red = login("red-analyst", os.environ["BAYORA_SMOKE_RED_PASSWORD"])
auditor = login("audit-reviewer", os.environ["BAYORA_SMOKE_AUDITOR_PASSWORD"])

provider = get(admin, "/api/v1/provider/status")
assert provider["provider"]["provider"] == "fixture"
assert provider["health"]["status"] == "connected"
assert "api_key" not in provider and "base_url" not in provider

request = Request(
    base + "/api/v1/evaluations",
    data=json.dumps({"prompt": "container fixture smoke evaluation"}).encode(),
    method="POST",
    headers={"Content-Type": "application/json"},
)
with red.open(request) as response:
    evaluation = json.load(response)
assert evaluation["state"] == "completed"
assert "workspace" not in evaluation
assert "Test Fixture — Not Real Model Evidence" in evaluation["response"]
assert [event["event_type"] for event in evaluation["audit_events"]] == [
    "evaluation_created", "policy_checked", "llm_invocation", "llm_response_received", "evaluation_completed"
]

validation_request = Request(
    base + "/api/v1/security/validation",
    data=b"{}",
    method="POST",
    headers={"Content-Type": "application/json"},
)
with admin.open(validation_request) as response:
    assert json.load(response)["passed"] is True
assert get(auditor, "/api/v1/audit/verify")["valid"] is True
print("frontend, backend, fixture, database, audit, and validation: passed")
PY
