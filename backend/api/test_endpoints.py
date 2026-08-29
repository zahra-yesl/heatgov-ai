"""End-to-end test of the HeatGov AI API.

Starts a real uvicorn server on port 8000, exercises every endpoint over HTTP,
then shuts the server down. Nothing is mocked: this is the same path the
frontend will take in Step 6.

    .venv/Scripts/python.exe backend/api/test_endpoints.py
    .venv/Scripts/python.exe backend/api/test_endpoints.py --no-agent   # skip Gemini
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import requests  # noqa: E402

BASE_URL = "http://127.0.0.1:8000"
STARTUP_TIMEOUT_S = 120

_passed = 0
_failed: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    global _passed
    if condition:
        _passed += 1
        print(f"  PASS  {name}" + (f"  {detail}" if detail else ""))
    else:
        _failed.append(name)
        print(f"  FAIL  {name}  {detail}")


def start_server() -> subprocess.Popen:
    """Launch uvicorn and wait until /api/health answers."""
    print("Starting uvicorn on port 8000 ...")
    process = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "api.main:app",
            "--app-dir", str(BACKEND_DIR),
            "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning",
        ],
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    deadline = time.time() + STARTUP_TIMEOUT_S
    while time.time() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"uvicorn exited early:\n{output[-3000:]}")
        try:
            if requests.get(f"{BASE_URL}/api/health", timeout=3).ok:
                print(f"  server up after {STARTUP_TIMEOUT_S - (deadline - time.time()):.1f}s\n")
                return process
        except requests.RequestException:
            time.sleep(1)

    process.terminate()
    raise RuntimeError(f"Server did not answer within {STARTUP_TIMEOUT_S}s")


def test_health() -> None:
    print("GET /api/health")
    response = requests.get(f"{BASE_URL}/api/health", timeout=30)
    check("health returns 200", response.ok, f"HTTP {response.status_code}")
    body = response.json()
    print(f"        {json.dumps(body)}")
    check("status is ok", body.get("status") == "ok")
    check("model_a_r2 present", body.get("model_a_r2") is not None, f"{body.get('model_a_r2')}")
    check("model_b_r2 present", body.get("model_b_r2") is not None, f"{body.get('model_b_r2')}")


def test_heatmap() -> None:
    print("\nGET /api/heatmap/tcm_peak_22h")
    response = requests.get(f"{BASE_URL}/api/heatmap/tcm_peak_22h", timeout=180)
    check("heatmap returns 200", response.ok, f"HTTP {response.status_code}")
    body = response.json()
    features = body.get("features", [])
    check("returns GeoJSON FeatureCollection", body.get("type") == "FeatureCollection")
    check("has tiles", len(features) > 8000, f"{len(features):,} features")
    if features:
        print(f"        first tile properties: {features[0]['properties']}")
    print(f"        metadata: {body.get('metadata')}")

    print("\nGET /api/heatmap/does_not_exist")
    response = requests.get(f"{BASE_URL}/api/heatmap/does_not_exist", timeout=30)
    check("unknown layer returns 404", response.status_code == 404, f"HTTP {response.status_code}")


def test_zones() -> str:
    print("\nGET /api/zones/ranked?top_n=5")
    response = requests.get(f"{BASE_URL}/api/zones/ranked", params={"top_n": 5}, timeout=120)
    check("zones returns 200", response.ok, f"HTTP {response.status_code}")
    body = response.json()
    zones = body.get("zones", [])
    check("returns 5 zones", len(zones) == 5, f"{len(zones)}")
    for zone in zones:
        print(f"        {zone['tract_fips']}  risk {zone['risk_score']:>5}  "
              f"physical {zone['physical_score']:>5}  night {zone['night_temp_c']}C  "
              f"({zone['lat']}, {zone['lon']})")
    check("scores descend", all(
        zones[i]["risk_score"] >= zones[i + 1]["risk_score"] for i in range(len(zones) - 1)
    ))
    check("has coordinates", all(z.get("lat") and z.get("lon") for z in zones))
    return zones[0]["tract_fips"] if zones else ""


def test_predict(tract_fips: str) -> None:
    print(f"\nPOST /api/predict  {{'tract_fips': '{tract_fips}'}}")
    response = requests.post(f"{BASE_URL}/api/predict",
                             json={"tract_fips": tract_fips}, timeout=120)
    check("predict returns 200", response.ok, f"HTTP {response.status_code}")
    body = response.json()
    print(f"        risk_score_b {body.get('risk_score_b')} | "
          f"risk_score_a {body.get('risk_score_a')} | "
          f"official {body.get('official_calenviroscreen_score')}")
    for feature in body.get("top_shap_features", []):
        print(f"          - {feature['explanation']}")
    check("both model scores returned",
          body.get("risk_score_a") is not None and body.get("risk_score_b") is not None)
    check("three SHAP drivers", len(body.get("top_shap_features", [])) == 3)

    print("\nPOST /api/predict  unknown tract")
    response = requests.post(f"{BASE_URL}/api/predict",
                             json={"tract_fips": "00000000000"}, timeout=60)
    check("unknown tract returns 404", response.status_code == 404, f"HTTP {response.status_code}")


def test_optimize() -> None:
    print("\nPOST /api/optimize  {'budget_usd': 500000, 'top_n': 10}")
    response = requests.post(f"{BASE_URL}/api/optimize",
                             json={"budget_usd": 500000, "top_n": 10}, timeout=120)
    check("optimize returns 200", response.ok, f"HTTP {response.status_code}")
    body = response.json()
    print(f"        funded {body.get('zones_funded')}/{body.get('zones_considered')} | "
          f"spent ${body.get('total_cost_usd'):,.0f} | "
          f"coverage {body.get('coverage_score')}%")
    for item in body.get("plan", []):
        print(f"          {item['tract_fips']}  {item['intervention']:<10} "
              f"${item['cost_usd']:>9,.0f}  risk {item['risk_score']}  "
              f"-{item['expected_reduction_c']}C")
    check("plan fits the budget", body.get("total_cost_usd", 0) <= 500000,
          f"${body.get('total_cost_usd', 0):,.0f}")
    check("plan is non-empty", len(body.get("plan", [])) > 0)
    check("no summed-degrees field", "total_expected_reduction_c" not in body)
    check("data caveat surfaced", "data_caveat" in body or body.get("canopy_data_available"))

    print("\nPOST /api/optimize  negative budget")
    response = requests.post(f"{BASE_URL}/api/optimize",
                             json={"budget_usd": -1, "top_n": 5}, timeout=30)
    check("negative budget rejected", response.status_code == 422,
          f"HTTP {response.status_code}")


def test_cors() -> None:
    print("\nCORS preflight from http://localhost:3000")
    response = requests.options(
        f"{BASE_URL}/api/zones/ranked",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
        timeout=30,
    )
    allowed = response.headers.get("access-control-allow-origin")
    check("localhost:3000 allowed", allowed == "http://localhost:3000", f"got {allowed!r}")


def test_agent() -> None:
    print("\nPOST /api/agent/chat")
    question = "I have $500,000 for Central Los Angeles. Where should I invest?"
    print(f"        message: {question!r}")

    started = time.time()
    response = requests.post(
        f"{BASE_URL}/api/agent/chat",
        json={"message": question, "session_id": "test-session"},
        timeout=300,
    )
    elapsed = time.time() - started

    if response.status_code == 503:
        check("agent available", False, f"503: {response.json().get('detail')}")
        return

    check("agent returns 200", response.ok, f"HTTP {response.status_code}")
    body = response.json()
    called = [call["tool"] for call in body.get("tool_calls", [])]
    print(f"        [{elapsed:.1f}s, {body.get('rounds')} rounds, model {body.get('model')}]")
    print(f"        tools called: {called}")
    check("agent used tools", len(called) > 0)
    check("agent priced the plan",
          "optimize_budget" in called or "get_top_risk_zones" in called)
    check("reply is substantial", len(body.get("reply", "")) > 200,
          f"{len(body.get('reply', ''))} chars")

    print("\n        --- agent reply ---")
    for line in body.get("reply", "").splitlines():
        print(f"        {line}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-agent", action="store_true",
                        help="skip the Gemini test (saves an API call)")
    args = parser.parse_args()

    server = start_server()
    try:
        test_health()
        test_heatmap()
        tract = test_zones()
        if tract:
            test_predict(tract)
        test_optimize()
        test_cors()
        if not args.no_agent:
            test_agent()
    finally:
        print("\nStopping server ...")
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()

    print()
    print("=" * 74)
    print(f"RESULT: {_passed} passed, {len(_failed)} failed")
    if _failed:
        for name in _failed:
            print(f"  FAILED: {name}")
    print("=" * 74)
    return 1 if _failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
