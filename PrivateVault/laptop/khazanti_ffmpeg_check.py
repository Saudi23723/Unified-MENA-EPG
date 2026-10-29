"""Downloads ffmpeg the way the Windows program does on first use, and checks it runs (CI only).
Prints the path for the next step."""

import os
import subprocess
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import khazanti  # noqa: E402

home = tempfile.mkdtemp(prefix="khazanti-ffmpeg-")
sync = khazanti.CloudSync(types.SimpleNamespace(vault=types.SimpleNamespace(home=home)))
sync._fetch_ffmpeg()
path = os.path.join(sync.tools, "ffmpeg.exe")
assert os.path.exists(path) and os.path.exists(os.path.join(sync.tools, "ffprobe.exe")), os.listdir(sync.tools)
print(subprocess.run([path, "-version"], capture_output=True, text=True).stdout.splitlines()[0])
with open(os.environ.get("GITHUB_ENV", os.devnull), "a") as f:
    f.write(f"KHAZANTI_FFMPEG={path}\n")
