#!/usr/bin/env python3
"""
sn_race_test_nodep.py - zero-dependency race condition harness for ServiceNow Table API.
Uses Python standard library (urllib) only.
"""
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
JOURNAL = f"{BASE}/api/now/table/sys_journal_field"
THINK = 1.5

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

def call(method, url, body=None, headers=None):
    req_headers = {
        "Authorization": AUTH_HEADER,
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    if headers:
        req_headers.update(headers)
    
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return ResponseWrapper(resp.status, resp.read(), dict(resp.headers))
    except urllib.error.HTTPError as exc:
        return ResponseWrapper(exc.code, exc.read(), dict(exc.headers))
    except Exception as exc:
        raise RuntimeError(f"Network error on {method} {url}: {exc}")

def get_incident(sys_id, fields="short_description,description,sys_mod_count,sys_updated_on"):
    url = f"{TABLE}/{sys_id}?sysparm_fields={fields}"
    r = call("GET", url)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code} GET: {r.text[:300]}")
    return r.json()["result"], r

def patch_incident(sys_id, body, headers=None):
    r = call("PATCH", f"{TABLE}/{sys_id}", body=body, headers=headers)
    if r.status_code >= 400 and headers and "If-Match" in headers:
        return r
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code} PATCH: {r.text[:300]}")
    return r

def mod_count(sys_id):
    rec, _ = get_incident(sys_id, "sys_mod_count")
    return int(rec["sys_mod_count"])

def run_pair(fn_a, fn_b):
    barrier = threading.Barrier(2)
    out = {}

    def wrap(name, fn):
        def run():
            barrier.wait()
            try:
                out[name] = fn()
            except Exception as exc:
                out[name] = exc
        return run

    threads = [threading.Thread(target=wrap("A", fn_a)), threading.Thread(target=wrap("B", fn_b))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out

def status_of(x):
    if isinstance(x, Exception):
        return f"ERROR: {x}"
    return f"HTTP {x.status_code}"

def header(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)

def main():
    header("Setup: creating one throwaway incident")
    resp = call("POST", TABLE, body={"short_description": "AETHER race test (safe to delete)", "description": "base"})
    if resp.status_code >= 400:
        sys.exit(f"Failed to create incident: HTTP {resp.status_code} - {resp.text}")
    created = resp.json()["result"]
    sys_id = created["sys_id"]
    print(f"Created incident {created.get('number', '?')} (sys_id {sys_id})")

    results = {}
    try:
        # Experiment 1
        header("EXPERIMENT 1: same field (short_description), two simultaneous PATCHes")
        before = mod_count(sys_id)
        out = run_pair(
            lambda: patch_incident(sys_id, {"short_description": "WRITTEN-BY-A"}),
            lambda: patch_incident(sys_id, {"short_description": "WRITTEN-BY-B"}),
        )
        rec, _ = get_incident(sys_id)
        after = int(rec["sys_mod_count"])
        print(f"Agent A: {status_of(out['A'])} | Agent B: {status_of(out['B'])}")
        print(f"Final short_description = {rec['short_description']!r}")
        print(f"sys_mod_count went {before} -> {after}")
        both_ok = not isinstance(out["A"], Exception) and not isinstance(out["B"], Exception)
        results[1] = (
            "Both writes returned success and one silently replaced the other (last writer wins, no conflict signal)."
            if both_ok else "A request errored - see above."
        )

        # Experiment 2
        header("EXPERIMENT 2: different fields, two simultaneous PATCHes")
        out = run_pair(
            lambda: patch_incident(sys_id, {"short_description": "DIFF-FIELD-A"}),
            lambda: patch_incident(sys_id, {"description": "DIFF-FIELD-B"}),
        )
        rec, _ = get_incident(sys_id)
        print(f"Agent A: {status_of(out['A'])} | Agent B: {status_of(out['B'])}")
        print(f"short_description = {rec['short_description']!r}")
        print(f"description       = {rec['description']!r}")
        ok = rec["short_description"] == "DIFF-FIELD-A" and rec["description"] == "DIFF-FIELD-B"
        results[2] = (
            "Both fields preserved: field-level PATCH is safe when agents touch different fields."
            if ok else "DATA LOSS on different fields - unexpected, inspect output above."
        )

        # Experiment 3
        header("EXPERIMENT 3: read-modify-write on ONE text field (the realistic agent case)")
        patch_incident(sys_id, {"description": "base"})

        def rmw(tag, delay):
            def agent():
                time.sleep(delay)
                rec_, _ = get_incident(sys_id, "description")
                old = rec_["description"]
                print(f"  [Agent {tag}] read description = {old!r}, reasoning {THINK}s ...")
                time.sleep(THINK)
                return patch_incident(sys_id, {"description": f"{old} | note-from-{tag}"})
            return agent

        out = run_pair(rmw("A", 0.0), rmw("B", 0.2))
        rec, _ = get_incident(sys_id)
        print(f"Agent A: {status_of(out['A'])} | Agent B: {status_of(out['B'])}")
        print(f"Final description = {rec['description']!r}")
        has_a = "note-from-A" in rec["description"]
        has_b = "note-from-B" in rec["description"]
        lost = not (has_a and has_b)
        results[3] = (
            "LOST UPDATE REPRODUCED: one agent's note was erased, and both requests still returned success."
            if lost else "Both notes survived (unexpected for read-modify-write)."
        )

        # Experiment 4
        header("EXPERIMENT 4: journal field (work_notes), two simultaneous PATCHes")
        out = run_pair(
            lambda: patch_incident(sys_id, {"work_notes": "journal-entry-from-A"}),
            lambda: patch_incident(sys_id, {"work_notes": "journal-entry-from-B"}),
        )
        url = f"{JOURNAL}?sysparm_query=element_id={sys_id}^element=work_notes&sysparm_fields=value"
        jr = call("GET", url).json().get("result", [])
        values = [j["value"] for j in jr]
        print(f"Agent A: {status_of(out['A'])} | Agent B: {status_of(out['B'])}")
        print(f"Journal entries found: {values}")
        ok = "journal-entry-from-A" in values and "journal-entry-from-B" in values
        results[4] = (
            "Both journal entries preserved: append-style fields are safe."
            if ok else "A journal entry is missing - inspect output above."
        )

        # Experiment 5
        header("EXPERIMENT 5: does the Table API enforce If-Match / ETag?")
        rec, resp = get_incident(sys_id)
        for h in ("ETag", "Last-Modified", "Cache-Control", "etag", "last-modified"):
            if h in resp.headers:
                print(f"Response header {h}: {resp.headers.get(h)!r}")
        
        r = patch_incident(
            sys_id, {"short_description": "IF-MATCH-PROBE"},
            headers={"If-Match": '"definitely-not-the-current-version"'}
        )
        print(f"PATCH with a bogus If-Match -> HTTP {r.status_code}")
        if r.status_code in (412, 409):
            results[5] = f"Server rejected bogus If-Match with HTTP {r.status_code}. Conditional writes supported!"
        else:
            rec2, _ = get_incident(sys_id)
            if rec2["short_description"] == "IF-MATCH-PROBE":
                results[5] = "If-Match was IGNORED: the write went through with a wrong version. No HTTP-level OCC here."
            else:
                results[5] = "Write did not apply despite success status - inspect manually."

    finally:
        header("Cleanup")
        try:
            call("DELETE", f"{TABLE}/{sys_id}")
            print("Deleted the test incident.")
        except Exception as exc:
            print(f"Could not delete {sys_id} automatically ({exc}). Delete it manually.")

    header("SUMMARY - paste this back to me")
    for k in sorted(results):
        print(f"{k}. {results[k]}")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        sys.exit(f"\nFailed: {exc}")

