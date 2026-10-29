"""Checks the laptop vault server end to end: python khazanti_selftest.py"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Client:
    def __init__(self, base):
        self.base = base
        self.token = None

    def call(self, method, path, body=None, raw=None, headers=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read(), e.headers

    def json(self, method, path, body=None):
        status, data, _ = self.call(method, path, body)
        return status, json.loads(data or b"{}")


def check_contents_parsing():
    """The printed contents of a book, as text comes out of PDFs, joined to page footers."""
    sys.path.insert(0, HERE)
    import khazanti
    assert khazanti.page_label("Chapter 1\nBody text, see Figure 1-4.\n1-9\n") == "1-9"
    assert khazanti.page_label("Preface\nvii") == "vii"
    assert khazanti.page_label("Body mentioning 1-4 only inline") is None
    two_columns = ("Introduction To Flying\n.......\n1-1\nAeronautical Decision-Making\n.....\n2-1\n"
                   "Aeronautical Information Manual (AIM) .............. 1-9 Risk Management........2-3\n"
                   "Preface ......iii\n")
    got = khazanti.toc_entries(two_columns)
    assert ("Introduction To Flying", "1-1") in got and ("Aeronautical Decision-Making", "2-1") in got, got
    assert ("Aeronautical Information Manual (AIM)", "1-9") in got and ("Risk Management", "2-3") in got, got
    assert ("Preface", "iii") in got, got


def main():
    check_contents_parsing()
    home = tempfile.mkdtemp(prefix="khazanti-test-")
    port = free_port()
    env = dict(os.environ, KHAZANTI_HOME=home)
    exe = sys.argv[1:] or [sys.executable, os.path.join(HERE, "khazanti.py")]
    proc = subprocess.Popen(exe + ["--headless", "--port", str(port)], env=env)
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/api/status", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        c = Client(base)

        st, s = c.json("GET", "/api/status")
        assert st == 200 and s["setup"] is False and s["authed"] is False, s
        # The built program must know its own build, or it can never see an update.
        if os.environ.get("EXPECT_BUILD"):
            assert s.get("build") == int(os.environ["EXPECT_BUILD"]), s
        st, data, _ = c.call("GET", "/")
        assert st == 200 and "خزنتي".encode() in data

        # Nothing is reachable before logging in.
        assert c.json("GET", "/api/index")[0] == 401
        assert c.call("PUT", "/api/upload?name=a.txt", raw=b"x")[0] == 401

        st, r = c.json("POST", "/api/setup", {"password": "1234", "device": "test"})
        assert st == 200 and r["token"], r
        assert c.json("POST", "/api/setup", {"password": "9999"})[0] == 409
        c.token = r["token"]

        # Folders, a nested upload as from a dropped directory, and a plain upload.
        st, top = c.json("POST", "/api/folders", {"name": "أفلام", "parent": None})
        assert st == 200
        video = os.urandom(300_000)
        st, data, _ = c.call("PUT", f"/api/upload?folder={top['id']}&path=" + urllib.request.quote("رحلة/يوم 1/clip.mp4"), raw=video)
        assert st == 200, data
        clip = json.loads(data)
        assert clip["mime"] == "video/mp4" and clip["size"] == len(video)
        st, data, _ = c.call("PUT", "/api/upload?name=notes.txt", raw="مرحبا".encode())
        notes = json.loads(data)

        # Files sent from the phone land in their folders once, however often they are sent.
        phone_path = "/api/upload?src=phone:abc&path=" + urllib.request.quote("الهاتف/دروس/pdf1.pdf")
        st, data, _ = c.call("PUT", phone_path, raw=b"%PDF-1.4 one")
        first = json.loads(data)
        st, data, _ = c.call("PUT", phone_path, raw=b"%PDF-1.4 one")
        assert json.loads(data)["id"] == first["id"] and first["src"] == "phone:abc"
        st, idx = c.json("GET", "/api/index")
        assert sum(1 for i in idx["items"] if i.get("src") == "phone:abc") == 1
        c.json("POST", "/api/delete", {"kind": "folder", "id": [d for d in idx["folders"] if d["name"] == "الهاتف"][0]["id"]})

        st, idx = c.json("GET", "/api/index")
        names = {d["name"]: d for d in idx["folders"]}
        assert set(names) == {"أفلام", "رحلة", "يوم 1"}, names
        assert names["رحلة"]["parent"] == top["id"] and clip["folder"] == names["يوم 1"]["id"]
        assert notes["folder"] is None

        # Streaming with seeking, as the phone's player does.
        st, data, h = c.call("GET", f"/api/file/{clip['id']}")
        assert st == 200 and data == video and h["Accept-Ranges"] == "bytes"
        st, data, h = c.call("GET", f"/api/file/{clip['id']}", headers={"Range": "bytes=1000-1999"})
        assert st == 206 and data == video[1000:2000] and h["Content-Range"] == f"bytes 1000-1999/{len(video)}"
        st, data, _ = c.call("GET", f"/api/file/{clip['id']}", headers={"Range": "bytes=-500"})
        assert st == 206 and data == video[-500:]
        assert c.call("GET", f"/api/file/{clip['id']}", headers={"Range": f"bytes={len(video)}-"})[0] == 416
        # The token also works in the address, for players that cannot send headers.
        tok = c.token
        c.token = None
        assert c.call("GET", f"/api/file/{notes['id']}?t={tok}")[0] == 200
        assert c.call("GET", f"/api/file/{notes['id']}?t=wrong")[0] == 401
        c.token = tok

        # Rename, move, and the guard against moving a folder into itself.
        assert c.json("POST", "/api/rename", {"kind": "item", "id": notes["id"], "name": "ملاحظات.txt"})[0] == 200
        assert c.json("POST", "/api/move", {"kind": "item", "id": notes["id"], "parent": top["id"]})[0] == 200
        assert c.json("POST", "/api/move", {"kind": "folder", "id": top["id"], "parent": names["يوم 1"]["id"]})[0] == 400
        rev_before = c.json("GET", "/api/rev")[1]["rev"]

        # Deleting a folder removes everything below it, files included.
        clip_path = os.path.join(home, "files", clip["file"])
        assert os.path.exists(clip_path)
        assert c.json("POST", "/api/delete", {"kind": "folder", "id": names["رحلة"]["id"]})[0] == 200
        st, idx = c.json("GET", "/api/index")
        assert [d["name"] for d in idx["folders"]] == ["أفلام"]
        assert [i["name"] for i in idx["items"]] == ["ملاحظات.txt"]
        assert not os.path.exists(clip_path)
        assert idx["rev"] > rev_before

        # Word files come back as PDF where LibreOffice is installed.
        if shutil.which("soffice"):
            src = os.path.join(home, "letter.txt")
            with open(src, "w") as f:
                f.write("Lift and drag\nFour forces of flight\n")
            subprocess.run(["soffice", "--headless", "--convert-to", "docx", "--outdir", home, src],
                           capture_output=True, timeout=180)
            with open(os.path.join(home, "letter.docx"), "rb") as f:
                st, data, _ = c.call("PUT", "/api/upload?name=letter.docx", raw=f.read())
            doc = json.loads(data)
            st, data, h = c.call("GET", f"/api/pdf/{doc['id']}")
            assert st == 200 and data.startswith(b"%PDF") and h["Content-Type"] == "application/pdf", (st, data[:20])
            assert c.call("GET", f"/api/pdf/{notes['id']}")[0] == 415
            c.json("POST", "/api/delete", {"kind": "item", "id": doc["id"]})
            print("word to pdf works")

        # Notes from two devices merge page by page; the later change of a page wins.
        st, a = c.json("POST", f"/api/notes?item={notes['id']}", {"v": 2, "pages": {"1": [{"t": "PEN"}], "2": [{"t": "PEN"}]},
                                                               "t": {"1": 100, "2": 100}, "bm": {"t": 100, "list": [{"p": 1}]}})
        st, b = c.json("POST", f"/api/notes?item={notes['id']}", {"v": 2, "pages": {"2": [], "3": [{"t": "OVAL"}]},
                                                               "t": {"2": 200, "3": 50}, "bm": {"t": 90, "list": []}})
        assert b["pages"]["1"] == [{"t": "PEN"}] and b["pages"]["2"] == [] and b["pages"]["3"] == [{"t": "OVAL"}], b
        assert b["bm"]["list"] == [{"p": 1}], b
        st, g = c.json("GET", f"/api/notes?item={notes['id']}")
        assert g == b, g
        assert c.json("GET", "/api/notes?src=phone:none")[0] == 404

        # Running from source never offers to update itself. The built program
        # must reach the update source from inside the .exe (network and TLS).
        st, u = c.json("GET", "/api/update")
        if os.environ.get("EXPECT_BUILD"):
            assert st == 200 and isinstance(u["latest"], int), u
            print("update check from the .exe:", u)
        else:
            assert st == 200 and u["available"] is False, u

        # Wrong passwords are counted and then refused for a while.
        anon = Client(base)
        for _ in range(4):
            assert anon.json("POST", "/api/login", {"password": "0000"})[0] == 403
        st, r = anon.json("POST", "/api/login", {"password": "0000"})
        assert st == 403 and r["wait"] > 0
        assert anon.json("POST", "/api/login", {"password": "1234"})[0] == 429

        # A revoked device loses access.
        st, info = c.json("GET", "/api/info")
        assert info["me"] and any(d["id"] == info["me"] for d in info["devices"])
        assert c.json("POST", "/api/devices/revoke", {"id": info["me"]})[0] == 200
        assert c.json("GET", "/api/index")[0] == 401

        # The index survives a restart.
        with open(os.path.join(home, "index.json"), encoding="utf-8") as f:
            assert len(json.load(f)["items"]) == 1
        print("all laptop server checks passed")
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    main()
