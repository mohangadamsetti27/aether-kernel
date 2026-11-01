#!/usr/bin/env python3
import os
import sys
import threading
import time
import json
import base64
import urllib.request
import urllib.error

BASE = os.environ.get("SN_URL", "").rstrip("/")
USER = os.environ.get("SN_USER")
PASS = os.environ.get("SN_PASS")

if not (BASE and USER and PASS):
    sys.exit("Set SN_URL, SN_USER and SN_PASS environment variables first.")

TABLE = f"{BASE}/api/now/table/incident"
AUTH_HEADER = "Basic " + base64.b64encode(f"{USER}:{PASS}".encode("utf-8")).decode("utf-8")

class ResponseWrapper:
    def __init__(self, status_code, body_bytes, headers):
        self.status_code = status_code
        self.headers = headers
        self._body = body_bytes

    def json(self):
        return json.loads(self._body.decode("utf-8"))

    @property
    def text(self):
        return self._body.decode("utf-8", errors="replace")

def call(method, url, body=None):
    req_headers = {
        "Authorization": AUTH_HEADER,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return ResponseWrapper(resp.status, resp.read(), dict(resp.headers))
    except urllib.error.HTTPError as exc:
        return ResponseWrapper(exc.code, exc.read(), dict(exc.headers))

def get_incident(sys_id):
    r = call("GET", f"{TABLE}/{sys_id}?sysparm_fields=description,sys_mod_count")
    return r.json()["result"]

class AetherOCCGateway:
    def __init__(self):
        self.lock = threading.Lock()

    def guarded_patch(self, sys_id, expected_mod_count, body):
        with self.lock:
            current = get_incident(sys_id)
            actual_mod_count = int(current["sys_mod_count"])
            if actual_mod_count != expected_mod_count:
                return {
                    "status_code": 409,
                    "error": f"CONFLICT: Stale write detected. Current sys_mod_count is {actual_mod_count}, but write expected {expected_mod_count}."
                }
            r = call("PATCH", f"{TABLE}/{sys_id}", body=body)
            return {"status_code": r.status_code, "data": r.json()["result"]}

def main():
    print("=" * 72)
    print("AETHER OCC GUARD TEST: Preventing Lost Updates on ServiceNow")
    print("=" * 72)

    init = call("POST", TABLE, body={"short_description": "Aether Guard Demo", "description": "base"}).json()["result"]
    sys_id = init["sys_id"]
    gateway = AetherOCCGateway()
    print(f"Created Incident sys_id: {sys_id}")

    try:
        out = {}
        barrier = threading.Barrier(2)

        def agent_work(name, delay):
            def run():
                time.sleep(delay)
                rec = get_incident(sys_id)
                read_version = int(rec["sys_mod_count"])
                print(f"  [Agent {name}] Read version {read_version}, reasoning for 1.5s...")
                time.sleep(1.5)
                barrier.wait()
                res = gateway.guarded_patch(sys_id, read_version, {"description": f"{rec['description']} | from-{name}"})
                out[name] = res
            return run

        t1 = threading.Thread(target=agent_work("A", 0.0))
        t2 = threading.Thread(target=agent_work("B", 0.2))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        print("\n--- RESULTS ---")
        print(f"Agent A response: {out['A']['status_code']}")
        print(f"Agent B response: {out['B']['status_code']} -> {out['B'].get('error', 'Success')}")

        final_rec = get_incident(sys_id)
        print(f"Final description in ServiceNow: {final_rec['description']!r}")

        if (out["A"]["status_code"] == 200 and out["B"]["status_code"] == 409) or \
           (out["B"]["status_code"] == 200 and out["A"]["status_code"] == 409):
            print("\n[SUCCESS] Aether guarded the write: Stale overwrite blocked, data corruption prevented.")

    finally:
        call("DELETE", f"{TABLE}/{sys_id}")
        print("Cleanup: Deleted test incident.")

if __name__ == "__main__":
    main()
