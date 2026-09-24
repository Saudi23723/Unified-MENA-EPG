"""Run the real Shasha generator on a runner and show what it would
publish. Writes shasha_epg.xml on the runner only; commits nothing."""

import subprocess
import sys
import xml.etree.ElementTree as ET

done = subprocess.run([sys.executable, "-u", "update_shasha_epg.py"],
                      capture_output=True, text=True)
print(done.stdout[-6000:])
print(done.stderr[-3000:])
print("exit", done.returncode)
root = ET.parse("shasha_epg.xml").getroot()
for p in root.findall("programme"):
    title = p.findtext("title") or ""
    if "القادمة" in title or "لا توجد" in title or "بعد " in title:
        continue
    print(p.get("start"), "|", title)
