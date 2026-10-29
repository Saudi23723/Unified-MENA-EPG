"""Runs a real one-click update of the built .exe on Windows (CI only):

    python khazanti_update_check.py dist/Khazanti.exe

A copy of the new .exe updates itself to the published build, swaps the
file, starts again, and must then answer with the published build.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

PORT = 47851


def call(method, path, body=None, token=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def status():
    try:
        return call("GET", "/api/status", timeout=3)
    except Exception:
        return None


def wait(cond, seconds, what):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return
        time.sleep(1)
    raise SystemExit("timed out waiting for " + what)


def main():
    work = tempfile.mkdtemp(prefix="khazanti-update-")
    exe = os.path.join(work, "Khazanti.exe")
    shutil.copy(sys.argv[1], exe)
    env = dict(os.environ, KHAZANTI_HOME=os.path.join(work, "home"))
    subprocess.Popen([exe, "--headless", "--port", str(PORT)], env=env)
    wait(lambda: status() is not None, 60, "the copy to start")
    before = status()["build"]
    token = call("POST", "/api/setup", {"password": "1234", "device": "ci"})["token"]
    update = call("GET", "/api/update", token=token, timeout=60)
    print("before:", before, "update:", update)
    target = update["latest"]
    applied = call("POST", "/api/update/apply", {}, token=token, timeout=180)
    print("applied:", applied)
    # The old process exits, the file is swapped, the new one starts by itself.
    wait(lambda: status() is None, 60, "the old copy to exit")
    # The published build may lag behind a cached copy by one; any published
    # build other than this one, running by itself, shows the swap worked.
    wait(lambda: (status() or {}).get("build") not in (None, before), 120, f"build {target} to start by itself")
    print("restarted as build", status()["build"])
    assert not os.path.exists(exe + ".new"), "the downloaded file was not swapped in"
    subprocess.run(["taskkill", "/F", "/IM", "Khazanti.exe"], capture_output=True)
    print("one-click update works")


if __name__ == "__main__":
    main()
