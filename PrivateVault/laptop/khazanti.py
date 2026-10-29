"""خزنتي للابتوب — the laptop side of the Private Vault app.

One program that keeps videos and documents in a hidden folder on the
laptop, shows them in a window where files are dragged in and arranged
into folders, and serves the same vault to the phone app over the home
network so videos play on the phone without being stored there.

Everything is behind one password. The phone logs in with it once and
keeps a device token; tokens can be revoked from the laptop.

Run:  khazanti.exe            (window + tray icon)
      khazanti.py --headless  (server only, used by the tests)
"""

import argparse
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import socket
import sys
import threading
import time
import urllib.parse
import uuid
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_NAME = "Khazanti"
VERSION = "1.0"
DEFAULT_PORT = 47801
DISCOVERY_PORT = 47802
DISCOVER_MSG = b"KHAZNATI_DISCOVER"
PBKDF2_ROUNDS = 200_000
MAX_TRIES = 5
LOCKOUT_SECONDS = 30
CHUNK = 1024 * 1024

# Builds published for the one-click update: the vault-builds-windows branch
# holds latest.json and Khazanti.exe, read through GitHub or its jsDelivr mirror.
UPDATE_SOURCES = [
    "https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/vault-builds-windows/",
    "https://cdn.jsdelivr.net/gh/Saudi23723/Unified-MENA-EPG@vault-builds-windows/",
]

mimetypes.add_type("video/x-matroska", ".mkv")
mimetypes.add_type("video/webm", ".webm")
mimetypes.add_type("video/mp4", ".m4v")
mimetypes.add_type("text/plain", ".srt")
mimetypes.add_type("audio/mp4", ".m4a")


def data_home() -> str:
    """The hidden folder holding the vault: %LOCALAPPDATA%\\Khazanti on Windows."""
    override = os.environ.get("KHAZANTI_HOME")
    if override:
        return override
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, APP_NAME)
    return os.path.join(os.path.expanduser("~"), "." + APP_NAME.lower())


def resource(name: str) -> str:
    """A file shipped next to this script, or inside the PyInstaller bundle."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


def write_json(path: str, obj) -> None:
    # Write beside the file and swap it in, so a crash never leaves half a file.
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def clean_name(name: str) -> str:
    name = (name or "").replace("\\", "/").split("/")[-1].strip()
    return "".join(c for c in name if c >= " ")[:200] or "file"


class Vault:
    """Folders and items, kept in index.json in the same shape the phone uses."""

    def __init__(self, home: str):
        self.home = home
        self.files_dir = os.path.join(home, "files")
        os.makedirs(self.files_dir, exist_ok=True)
        self.index_path = os.path.join(home, "index.json")
        self.lock = threading.RLock()
        self.folders: list = []
        self.items: list = []
        # Bumped on every change, so open windows and phones know to reload.
        self.rev = 0
        self._load()

    def _load(self):
        if not os.path.exists(self.index_path):
            return
        with open(self.index_path, encoding="utf-8") as f:
            data = json.load(f)
        self.folders = data.get("folders", [])
        self.items = data.get("items", [])

    def save(self):
        with self.lock:
            self.rev += 1
            write_json(self.index_path, {"version": 1, "folders": self.folders, "items": self.items})

    def snapshot(self) -> dict:
        with self.lock:
            return {"rev": self.rev, "folders": list(self.folders), "items": list(self.items)}

    def folder(self, fid):
        return next((d for d in self.folders if d["id"] == fid), None)

    def item(self, iid):
        return next((i for i in self.items if i["id"] == iid), None)

    def path_of(self, item) -> str:
        return os.path.join(self.files_dir, item["file"])

    def subtree(self, fid) -> set:
        out = {fid}
        grew = True
        while grew:
            grew = False
            for d in self.folders:
                if d.get("parent") in out and d["id"] not in out:
                    out.add(d["id"])
                    grew = True
        return out

    def add_folder(self, name, parent):
        with self.lock:
            if parent is not None and self.folder(parent) is None:
                raise ValueError("no such folder")
            d = {"id": str(uuid.uuid4()), "name": clean_name(name), "parent": parent,
                 "created": int(time.time() * 1000)}
            self.folders.append(d)
            self.save()
            return d

    def folder_by_path(self, parent, parts):
        """Find or make the chain of folders a dropped directory needs."""
        with self.lock:
            for part in parts:
                part = clean_name(part)
                found = next((d for d in self.folders if d.get("parent") == parent and d["name"] == part), None)
                if found is None:
                    found = {"id": str(uuid.uuid4()), "name": part, "parent": parent,
                             "created": int(time.time() * 1000)}
                    self.folders.append(found)
                parent = found["id"]
            self.save()
            return parent

    def rename(self, kind, oid, name):
        with self.lock:
            obj = self.folder(oid) if kind == "folder" else self.item(oid)
            if obj is None:
                raise KeyError(oid)
            obj["name"] = clean_name(name)
            self.save()

    def move(self, kind, oid, parent):
        with self.lock:
            if parent is not None and self.folder(parent) is None:
                raise ValueError("no such folder")
            if kind == "folder":
                d = self.folder(oid)
                if d is None:
                    raise KeyError(oid)
                if parent in self.subtree(oid):
                    raise ValueError("cannot move a folder into itself")
                d["parent"] = parent
            else:
                it = self.item(oid)
                if it is None:
                    raise KeyError(oid)
                it["folder"] = parent
            self.save()

    def delete(self, kind, oid):
        with self.lock:
            if kind == "folder":
                ids = self.subtree(oid)
                gone = [i for i in self.items if i.get("folder") in ids]
                self.items = [i for i in self.items if i.get("folder") not in ids]
                self.folders = [d for d in self.folders if d["id"] not in ids]
            else:
                gone = [i for i in self.items if i["id"] == oid]
                self.items = [i for i in self.items if i["id"] != oid]
            self.save()
        for it in gone:
            try:
                os.remove(self.path_of(it))
            except OSError:
                pass

    def by_source(self, src):
        with self.lock:
            return next((i for i in self.items if src and i.get("src") == src), None)

    def add_upload(self, name, folder, stream, length, src=None):
        name = clean_name(name)
        ext = os.path.splitext(name)[1].lower()
        iid = str(uuid.uuid4())
        stored = iid + (ext if 0 < len(ext) <= 7 else "")
        target = os.path.join(self.files_dir, stored)
        tmp = target + ".part"
        left = length
        try:
            with open(tmp, "wb") as out:
                while left > 0:
                    chunk = stream.read(min(CHUNK, left))
                    if not chunk:
                        raise ConnectionError("upload cut short")
                    out.write(chunk)
                    left -= len(chunk)
            os.replace(tmp, target)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        item = {"id": iid, "name": name, "file": stored, "mime": mime, "size": length,
                "added": int(time.time() * 1000), "folder": folder}
        if src:
            # Where it came from, e.g. "phone:<id>", so sending again skips it.
            item["src"] = src[:120]
        with self.lock:
            if folder is not None and self.folder(folder) is None:
                item["folder"] = None
            self.items.append(item)
            self.save()
        return item

    def total_bytes(self) -> int:
        with self.lock:
            return sum(int(i.get("size", 0)) for i in self.items)


class Auth:
    """The vault password and the tokens handed to the window and to phones."""

    def __init__(self, home: str):
        self.path = os.path.join(home, "config.json")
        self.lock = threading.Lock()
        self.cfg = {}
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.cfg = json.load(f)
        self.cfg.setdefault("tokens", {})
        self.tries = 0
        self.locked_until = 0.0

    def _save(self):
        write_json(self.path, self.cfg)

    @property
    def has_password(self) -> bool:
        return "pw_hash" in self.cfg

    @staticmethod
    def _hash(pw: str, salt: bytes) -> str:
        return hashlib.pbkdf2_hmac("sha256", pw.encode("utf-8"), salt, PBKDF2_ROUNDS).hex()

    def set_password(self, pw: str):
        salt = secrets.token_bytes(16)
        with self.lock:
            self.cfg["pw_salt"] = salt.hex()
            self.cfg["pw_hash"] = self._hash(pw, salt)
            self._save()

    def check_password(self, pw: str) -> bool:
        if not self.has_password:
            return False
        ok = hmac.compare_digest(self._hash(pw, bytes.fromhex(self.cfg["pw_salt"])), self.cfg["pw_hash"])
        with self.lock:
            if ok:
                self.tries = 0
            else:
                self.tries += 1
                if self.tries >= MAX_TRIES:
                    self.tries = 0
                    self.locked_until = time.time() + LOCKOUT_SECONDS
        return ok

    def wait_seconds(self) -> int:
        return max(0, int(self.locked_until - time.time() + 0.999))

    @staticmethod
    def _key(token: str) -> str:
        # Only a hash of each token is written to disk.
        return hashlib.sha256(token.encode()).hexdigest()

    def new_token(self, device: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.lock:
            self.cfg["tokens"][self._key(token)] = {
                "name": clean_name(device or "device")[:60],
                "created": int(time.time() * 1000),
            }
            self._save()
        return token

    def valid(self, token) -> bool:
        return bool(token) and self._key(token) in self.cfg["tokens"]

    def device_id(self, token) -> str:
        return self._key(token)[:12] if token else ""

    def devices(self):
        return [{"id": k[:12], **v} for k, v in self.cfg["tokens"].items()]

    def revoke(self, device_id: str):
        with self.lock:
            for k in [k for k in self.cfg["tokens"] if k[:12] == device_id]:
                del self.cfg["tokens"][k]
            self._save()

    def revoke_all(self):
        with self.lock:
            self.cfg["tokens"] = {}
            self._save()


def lan_addresses() -> list:
    """The laptop's addresses on the home network, for typing into the phone."""
    found = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        found.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            found.append(info[4][0])
    except OSError:
        pass
    out = []
    for a in found:
        if a not in out and not a.startswith("127."):
            out.append(a)
    return out


def current_build() -> int:
    """The CI build number baked into the .exe; 0 when run from source."""
    try:
        with open(resource("build_info.json"), encoding="utf-8") as f:
            return int(json.load(f).get("build", 0))
    except (OSError, ValueError):
        return 0


def fetch(url: str, timeout=15):
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Khazanti/" + VERSION})
    return urllib.request.urlopen(req, timeout=timeout)


def latest_release():
    """{"build": n, "exe": url} from the first source that answers, or None."""
    for base in UPDATE_SOURCES:
        try:
            with fetch(base + "latest.json?t=" + str(int(time.time()))) as r:
                info = json.loads(r.read().decode("utf-8"))
            return {"build": int(info["build"]), "exe": base + info.get("exe", "Khazanti.exe")}
        except Exception:
            continue
    return None


def apply_update(latest) -> None:
    """Download the new .exe beside this one, then swap it in once this process exits and start it."""
    if not getattr(sys, "frozen", False) or os.name != "nt":
        raise RuntimeError("updates apply to the installed Khazanti.exe only")
    exe = sys.executable
    new = exe + ".new"
    urls = [latest["exe"]] + [b + "Khazanti.exe" for b in UPDATE_SOURCES if b + "Khazanti.exe" != latest["exe"]]
    for url in urls:
        try:
            with fetch(url, timeout=60) as r, open(new, "wb") as out:
                while True:
                    chunk = r.read(CHUNK)
                    if not chunk:
                        break
                    out.write(chunk)
            if os.path.getsize(new) > 1_000_000:
                break
        except Exception:
            pass
    else:
        raise RuntimeError("download failed")
    bat = exe + ".update.bat"
    with open(bat, "w", encoding="utf-8") as f:
        # The running .exe is locked until it exits; keep trying the swap until then.
        f.write(
            "@echo off\r\n"
            ":wait\r\n"
            "ping -n 2 127.0.0.1 >nul\r\n"
            f'move /y "{new}" "{exe}" >nul 2>&1 || goto wait\r\n'
            f'start "" "{exe}" --no-window\r\n'
            'del "%~f0"\r\n'
        )
    import subprocess
    subprocess.Popen(["cmd", "/c", bat], creationflags=0x08000000 | 0x00000008)  # no window, detached
    # Let the browser receive the reply before this process goes away.
    threading.Timer(1.5, lambda: os._exit(0)).start()


# ---- printed contents of PDF books ----
#
# Many books print a contents page ("Lift ........ 5-3") without making its
# lines links, so nothing happens when they are clicked. The book's own page
# footers say which printed number each page carries, so the two can be
# joined: "5-3" in the contents is the page whose footer reads 5-3.

import re

LABEL = r"(?:\d{1,2}-\d{1,3}|[ivxlcdm]{1,7})"
LABEL_LINE = re.compile(r"^\s*(" + LABEL + r")\s*$", re.I | re.M)
TOC_LINE = re.compile(
    r"([^\n.][^\n]*?)[ \t]*\n?[ \t]*\.{3,}[ \t]*\n?[ \t]*(" + LABEL + r")(?=\s|$)", re.I)


def page_label(text: str):
    """The printed page number of a page: a line holding only that number, the last such (the footer)."""
    found = LABEL_LINE.findall(text or "")
    return found[-1].lower() if found else None


def toc_entries(text: str):
    out = []
    for m in TOC_LINE.finditer(text or ""):
        title = m.group(1).strip(" .\t")
        if len(title) >= 2:
            out.append((title, m.group(2).lower()))
    return out


def build_pdf_index(path: str) -> dict:
    """{"pages": n, "labels": [...], "toc": [{"title", "label", "page"}]} for one PDF."""
    from pypdf import PdfReader
    reader = PdfReader(path)
    n = len(reader.pages)
    labels = []
    toc = []
    for i, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        labels.append(page_label(text))
        # Contents pages sit near the front of a book.
        if i < 40:
            toc.extend(toc_entries(text))
    first = {}
    for i, lab in enumerate(labels):
        if lab and lab not in first:
            first[lab] = i
    entries = []
    seen = set()
    for title, lab in toc:
        if lab in first and (title, first[lab]) not in seen:
            seen.add((title, first[lab]))
            entries.append({"title": title, "label": lab, "page": first[lab]})
    # Two-column contents come out interleaved; book order is page order.
    entries.sort(key=lambda e: e["page"])
    return {"pages": n, "labels": labels, "toc": entries}


class PdfIndexes:
    """Builds each book's index once, in the background, and keeps it on disk."""

    def __init__(self, home):
        self.dir = os.path.join(home, "pdfindex")
        os.makedirs(self.dir, exist_ok=True)
        self.lock = threading.Lock()
        self.working = set()

    def get(self, vault, item):
        path = os.path.join(self.dir, item["id"] + ".json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        with self.lock:
            if item["id"] not in self.working:
                self.working.add(item["id"])
                threading.Thread(target=self._build, args=(vault.path_of(item), item["id"], path), daemon=True).start()
        return None

    def _build(self, src, iid, path):
        try:
            write_json(path, build_pdf_index(src))
        except Exception:
            write_json(path, {"pages": 0, "labels": [], "toc": []})
        finally:
            with self.lock:
                self.working.discard(iid)


class App:
    def __init__(self, home: str, port: int):
        os.makedirs(home, exist_ok=True)
        self.vault = Vault(home)
        self.auth = Auth(home)
        self.pdf_indexes = PdfIndexes(home)
        self.port = port


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Khazanti/" + VERSION
    app: App = None  # set by make_server

    def log_message(self, fmt, *args):
        pass

    # ---- plumbing ----

    def _send(self, status, body: bytes = b"", ctype="application/json; charset=utf-8", headers=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, status=200, headers=None):
        self._send(status, json.dumps(obj, ensure_ascii=False).encode("utf-8"), headers=headers)

    def _error(self, status, msg):
        self._json({"error": msg}, status)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        if n > 1_000_000:
            raise ValueError("body too large")
        return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

    def _token(self):
        h = self.headers.get("Authorization", "")
        if h.startswith("Bearer "):
            return h[7:].strip()
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        if "t" in q:
            return q["t"][0]
        c = SimpleCookie(self.headers.get("Cookie", ""))
        if "kt" in c:
            return c["kt"].value
        return None

    def _authed(self) -> bool:
        return self.app.auth.valid(self._token())

    def _cookie(self, token):
        return {"Set-Cookie": f"kt={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=31536000"}

    # ---- routing ----

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        try:
            self._get()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def do_POST(self):
        try:
            self._post()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except (ValueError, KeyError) as e:
            self._error(400, str(e))

    def do_PUT(self):
        try:
            self._put()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, ConnectionError):
            pass
        except (ValueError, KeyError) as e:
            self._error(400, str(e))

    def _get(self):
        url = urllib.parse.urlsplit(self.path)
        path = url.path
        if path in ("/", "/index.html"):
            with open(resource("index.html"), "rb") as f:
                return self._send(200, f.read(), "text/html; charset=utf-8")
        if path == "/api/status":
            return self._json({
                "app": "khazanti", "version": VERSION, "build": current_build(), "name": socket.gethostname(),
                "setup": self.app.auth.has_password, "authed": self._authed(),
            })
        if not self._authed():
            return self._error(401, "login required")
        if path == "/api/update":
            latest = latest_release()
            mine = current_build()
            return self._json({
                "current": mine, "latest": latest["build"] if latest else None,
                "available": bool(latest and mine and latest["build"] > mine),
            })
        if path == "/api/rev":
            return self._json({"rev": self.app.vault.rev})
        if path == "/api/index":
            return self._json(self.app.vault.snapshot())
        if path == "/api/info":
            return self._json({
                "addresses": lan_addresses(), "port": self.app.port, "name": socket.gethostname(),
                "devices": self.app.auth.devices(), "me": self.app.auth.device_id(self._token()),
                "bytes": self.app.vault.total_bytes(), "count": len(self.app.vault.items),
                "home": self.app.vault.home,
            })
        if path.startswith("/api/pdfindex/"):
            item = self.app.vault.item(path[len("/api/pdfindex/"):])
            if item is None:
                return self._error(404, "not found")
            index = self.app.pdf_indexes.get(self.app.vault, item)
            return self._json(index if index is not None else {"working": True})
        if path.startswith("/api/file/"):
            item = self.app.vault.item(path[len("/api/file/"):])
            if item is None:
                return self._error(404, "not found")
            download = "download=1" in (url.query or "")
            return self._send_file(item, download)
        self._error(404, "not found")

    def _post(self):
        path = urllib.parse.urlsplit(self.path).path
        auth = self.app.auth
        vault = self.app.vault
        if path in ("/api/setup", "/api/login"):
            body = self._body()
            pw = str(body.get("password", ""))
            if path == "/api/setup":
                if auth.has_password:
                    return self._error(409, "already set up")
                if len(pw) < 4:
                    return self._error(400, "password too short")
                auth.set_password(pw)
            else:
                wait = auth.wait_seconds()
                if wait:
                    return self._json({"error": "wait", "wait": wait}, 429)
                if not auth.check_password(pw):
                    wait = auth.wait_seconds()
                    return self._json({"error": "wrong password", "wait": wait}, 403)
            token = auth.new_token(str(body.get("device", "")) or "laptop")
            return self._json({"token": token}, headers=self._cookie(token))
        if not self._authed():
            return self._error(401, "login required")
        body = self._body()
        if path == "/api/logout":
            auth.revoke(auth.device_id(self._token()))
            return self._json({"ok": True}, headers={"Set-Cookie": "kt=; Path=/; Max-Age=0"})
        if path == "/api/folders":
            return self._json(vault.add_folder(body.get("name", ""), body.get("parent")))
        if path == "/api/rename":
            vault.rename(body.get("kind"), body["id"], body.get("name", ""))
            return self._json({"ok": True})
        if path == "/api/move":
            vault.move(body.get("kind"), body["id"], body.get("parent"))
            return self._json({"ok": True})
        if path == "/api/delete":
            vault.delete(body.get("kind"), body["id"])
            return self._json({"ok": True})
        if path == "/api/update/apply":
            latest = latest_release()
            if not latest:
                return self._error(502, "no update source reachable")
            try:
                apply_update(latest)
            except RuntimeError as e:
                return self._error(500, str(e))
            return self._json({"ok": True, "build": latest["build"]})
        if path == "/api/password":
            if not auth.check_password(str(body.get("old", ""))):
                return self._error(403, "wrong password")
            new = str(body.get("new", ""))
            if len(new) < 4:
                return self._error(400, "password too short")
            auth.set_password(new)
            return self._json({"ok": True})
        if path == "/api/devices/revoke":
            if body.get("all"):
                auth.revoke_all()
            else:
                auth.revoke(str(body.get("id", "")))
            return self._json({"ok": True})
        self._error(404, "not found")

    def _put(self):
        url = urllib.parse.urlsplit(self.path)
        if url.path != "/api/upload":
            return self._error(404, "not found")
        if not self._authed():
            return self._error(401, "login required")
        q = urllib.parse.parse_qs(url.query)
        folder = (q.get("folder") or [None])[0] or None
        rel = (q.get("path") or q.get("name") or ["file"])[0].replace("\\", "/")
        parts = [p for p in rel.split("/") if p not in ("", ".", "..")]
        if not parts:
            return self._error(400, "no name")
        if len(parts) > 1:
            # A dropped directory: its folders are made inside the current one.
            folder = self.app.vault.folder_by_path(folder, parts[:-1])
        length = int(self.headers.get("Content-Length") or -1)
        if length < 0:
            return self._error(411, "length required")
        src = (q.get("src") or [None])[0]
        existing = self.app.vault.by_source(src)
        if existing is not None:
            # Already here from an earlier send: drain the body and keep the one we have.
            left = length
            while left > 0:
                chunk = self.rfile.read(min(CHUNK, left))
                if not chunk:
                    break
                left -= len(chunk)
            return self._json(existing)
        item = self.app.vault.add_upload(parts[-1], folder, self.rfile, length, src)
        self._json(item)

    def _send_file(self, item, download):
        path = self.app.vault.path_of(item)
        try:
            size = os.path.getsize(path)
        except OSError:
            return self._error(404, "file missing")
        start, end, status = 0, size - 1, 200
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):
            spec = rng[6:].split(",")[0].strip()
            a, _, b = spec.partition("-")
            try:
                if a == "":
                    start, end = max(0, size - int(b)), size - 1
                else:
                    start = int(a)
                    end = min(int(b), size - 1) if b else size - 1
            except ValueError:
                start, end = 0, size - 1
            if start >= size or start > end:
                return self._send(416, b"", headers={"Content-Range": f"bytes */{size}"})
            status = 206
        quoted = urllib.parse.quote(item["name"])
        disp = "attachment" if download else "inline"
        self.send_response(status)
        self.send_header("Content-Type", item.get("mime") or "application/octet-stream")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", f"{disp}; filename*=UTF-8''{quoted}")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(256 * 1024, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)


def make_server(app: App) -> ThreadingHTTPServer:
    handler = type("BoundHandler", (Handler,), {"app": app})
    server = ThreadingHTTPServer(("0.0.0.0", app.port), handler)
    server.daemon_threads = True
    return server


def discovery_loop(port: int):
    """Answer the phone's "where is the laptop?" broadcast on the home network."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", DISCOVERY_PORT))
    except OSError:
        return
    reply = f"KHAZNATI {port} {socket.gethostname()}".encode("utf-8")
    while True:
        try:
            data, addr = s.recvfrom(256)
            if data.strip() == DISCOVER_MSG:
                s.sendto(reply, addr)
        except OSError:
            time.sleep(1)


def open_window(port: int):
    """Open the vault in an Edge app window (no browser bars), or the default browser."""
    url = f"http://127.0.0.1:{port}/"
    if os.name == "nt":
        import subprocess
        for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
            if not base:
                continue
            edge = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.exists(edge):
                subprocess.Popen([edge, f"--app={url}", "--window-size=1200,800"])
                return
    import webbrowser
    webbrowser.open(url)


def already_running(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def tray_icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((4, 4, 60, 60), radius=14, fill=(26, 35, 126, 255))
    d.arc((20, 12, 44, 38), 180, 360, fill="white", width=5)
    d.line((22, 25, 22, 32), fill="white", width=5)
    d.line((42, 25, 42, 32), fill="white", width=5)
    d.rounded_rectangle((15, 30, 49, 52), radius=5, fill="white")
    d.ellipse((29, 36, 35, 42), fill=(26, 35, 126, 255))
    return img


def run_tray(server, port):
    """Keep running in the notification area so the phone can reach the vault."""
    import pystray
    menu = pystray.Menu(
        pystray.MenuItem("فتح خزنتي", lambda icon, item: open_window(port), default=True),
        pystray.MenuItem("إيقاف خزنتي", lambda icon, item: (server.shutdown(), icon.stop())),
    )
    pystray.Icon(APP_NAME, tray_icon_image(), "خزنتي", menu).run()


def running_build(port: int):
    """The build of the copy already serving on this port; None for builds too old to say."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=3) as r:
            return json.loads(r.read().decode("utf-8")).get("build")
    except Exception:
        return None


def stop_older_copy(port: int) -> bool:
    """Ends the process listening on the port (an older copy of this program) and waits for the port."""
    import subprocess
    no_window = 0x08000000
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                             creationflags=no_window, timeout=15).stdout
    except Exception:
        return False
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3].upper() == "LISTENING":
            pids.add(parts[4])
    mine = {str(os.getpid()), str(os.getppid())}
    for pid in pids - mine:
        subprocess.run(["taskkill", "/F", "/T", "/PID", pid], capture_output=True, creationflags=no_window)
    for _ in range(40):
        if not already_running(port):
            return True
        time.sleep(0.25)
    return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true", help="serve only: no window, no tray icon")
    ap.add_argument("--no-window", action="store_true", help="start in the tray without opening the window")
    ap.add_argument("--port", type=int, default=int(os.environ.get("KHAZANTI_PORT", DEFAULT_PORT)))
    args = ap.parse_args(argv)

    if already_running(args.port):
        other = running_build(args.port)
        mine = current_build()
        newer = os.name == "nt" and mine > 0 and (other is None or int(other) < mine)
        # A newer copy takes over from an older one still running, so opening
        # the downloaded program is enough; otherwise this just shows the window.
        if not (newer and stop_older_copy(args.port)):
            if not args.headless:
                open_window(args.port)
            return

    app = App(data_home(), args.port)
    server = make_server(app)
    threading.Thread(target=discovery_loop, args=(args.port,), daemon=True).start()
    if args.headless:
        if sys.stdout:  # absent in the windowed .exe
            print(f"Khazanti serving on port {args.port}, data in {app.vault.home}", flush=True)
        server.serve_forever()
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    if not args.no_window:
        open_window(args.port)
    try:
        run_tray(server, args.port)
    except Exception:
        # No tray available: keep serving until the program is closed.
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    main()
