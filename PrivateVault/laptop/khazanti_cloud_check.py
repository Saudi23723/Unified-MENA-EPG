"""Sends a laptop vault to a cloud vault end to end: python khazanti_cloud_check.py [Khazanti.exe]

Two servers run side by side, one as the laptop and one as the cloud. A
1080p video inside folders, a PDF and a text file are sent with video
shrinking on; the cloud must get the same folders, a smaller 720p .mp4,
the other files as they are, and a second send must find nothing to do.
Needs ffmpeg on PATH, or downloads it the way the Windows program does.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Api:
    def __init__(self, port):
        self.base = f"http://127.0.0.1:{port}"
        self.token = None

    def call(self, method, path, body=None, raw=None, timeout=30):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())


def start(exe, home, port):
    env = dict(os.environ, KHAZANTI_HOME=home)
    p = subprocess.Popen(exe + ["--headless", "--port", str(port)], env=env)
    for _ in range(150):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1)
            return p
        except OSError:
            time.sleep(0.2)
    raise SystemExit("server did not start")


def main():
    exe = sys.argv[1:] or [sys.executable, os.path.join(HERE, "khazanti.py")]
    work = tempfile.mkdtemp(prefix="khazanti-cloud-")
    lp, cp = free_port(), free_port()
    procs = [start(exe, os.path.join(work, "laptop"), lp), start(exe, os.path.join(work, "cloud"), cp)]
    try:
        laptop, cloud = Api(lp), Api(cp)
        laptop.token = laptop.call("POST", "/api/setup", {"password": "1111", "device": "t"})["token"]
        cloud.call("POST", "/api/setup", {"password": "2222", "device": "t"})

        video = os.path.join(work, "lesson.mov")
        ffmpeg = os.environ.get("KHAZANTI_FFMPEG") or shutil.which("ffmpeg")
        if ffmpeg:
            subprocess.run([ffmpeg, "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=30",
                            "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6", "-c:v", "libx264", "-crf", "8",
                            "-c:a", "aac", "-b:a", "256k", video], check=True)
        else:
            raise SystemExit("ffmpeg is needed to make the test video")
        with open(video, "rb") as f:
            laptop.call("PUT", "/api/upload?path=" + urllib.parse.quote("Course/Part 1/1- Intro.mov"), raw=f.read())
        laptop.call("PUT", "/api/upload?path=" + urllib.parse.quote("Course/notes.txt"), raw="ملاحظات".encode())
        laptop.call("PUT", "/api/upload?name=book.pdf", raw=b"%PDF-1.4\n%%EOF\n")

        # Wrong password, then the right one.
        try:
            laptop.call("POST", "/api/cloud/link", {"url": f"http://127.0.0.1:{cp}", "password": "nope"})
            raise SystemExit("a wrong cloud password was accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 400
        st = laptop.call("POST", "/api/cloud/link", {"url": f"http://127.0.0.1:{cp}", "password": "2222"})
        assert st["linked"], st

        laptop.call("POST", "/api/cloud/start", {"compress": True})
        for _ in range(600):
            st = laptop.call("GET", "/api/cloud")
            if not st["running"]:
                break
            time.sleep(1)
        print("first send:", st)
        assert st["phase"] == "finished" and st["sent"] == 3 and st["failed"] == 0 and not st["error"], st
        assert st["saved"] > 0, st

        cloud.token = cloud.call("POST", "/api/login", {"password": "2222"})["token"]
        idx = cloud.call("GET", "/api/index")
        folders = {d["id"]: d for d in idx["folders"]}

        def path_of(item):
            names, d = [item["name"]], folders.get(item.get("folder"))
            while d:
                names.insert(0, d["name"])
                d = folders.get(d.get("parent"))
            return "/".join(names)

        paths = sorted(path_of(i) for i in idx["items"])
        print("cloud has:", paths)
        assert paths == ["Course/Part 1/1- Intro.mp4", "Course/notes.txt", "book.pdf"], paths
        clip = next(i for i in idx["items"] if i["name"].endswith(".mp4"))
        assert clip["size"] < os.path.getsize(video), (clip["size"], os.path.getsize(video))
        assert all(i.get("src", "").startswith("laptop:") for i in idx["items"])
        stored = os.path.join(work, "cloud", "files", clip["file"])
        probe = shutil.which("ffprobe") or (ffmpeg.replace("ffmpeg", "ffprobe") if os.path.exists(ffmpeg.replace("ffmpeg", "ffprobe")) else None)
        if probe:
            h = subprocess.run([probe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=height,codec_name",
                                "-of", "csv=p=0", stored], capture_output=True, text=True).stdout.strip()
            print("cloud video:", h, f"{clip['size']} bytes from {os.path.getsize(video)}")
            assert h == "h264,720", h

        # Sending again finds nothing new.
        laptop.call("POST", "/api/cloud/start", {"compress": True})
        for _ in range(60):
            st = laptop.call("GET", "/api/cloud")
            if not st["running"]:
                break
            time.sleep(0.5)
        assert st["phase"] == "finished" and st["total"] == 0 and st["sent"] == 0, st
        print("cloud send works")
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    import urllib.error
    main()
