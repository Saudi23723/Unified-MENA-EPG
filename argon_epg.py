#!/usr/bin/env python3
"""argon_epg.xml / hydra_epg.xml: the unified guide, re-published under each playlist's own channel names.

DreamTV's Xtream login gives its channels no tvg-id, so it can only match a guide by the exact
channel name ("ARA: BEIN SPORTS 1 [1080p]"). argon_names.json maps each unified channel id to
the Argon names that carry it; every one of those names becomes a channel here with that
channel's programmes. Only the window a player shows (3 h back, 48 h ahead) is kept, so the
file stays small enough for DreamTV. Names only: no links or logins live in this repository.
"""
import datetime
import html
import json
import re
from collections import defaultdict

SRC = "unified_mena_epg.xml"
# One guide per playlist: its name map -> the file DreamTV is pointed at.
PLAYLISTS = [("argon_names.json", "argon_epg.xml"), ("hydra_names.json", "hydra_epg.xml")]
now = datetime.datetime.now(datetime.timezone.utc)
lo = (now - datetime.timedelta(hours=3)).strftime("%Y%m%d%H%M%S")
hi = (now + datetime.timedelta(hours=48)).strftime("%Y%m%d%H%M%S")

text = open(SRC, encoding="utf-8").read()


def build(NAMES, OUT):
  names = json.load(open(NAMES, encoding="utf-8"))
  progs = defaultdict(list)
  for m in re.finditer(r'<programme\b[^>]*?start="(\d{14})[^"]*"[^>]*?stop="(\d{14})[^"]*"'
                       r'[^>]*?channel="([^"]*)"[^>]*>.*?</programme>', text, re.S):
      if m.group(3) in names and m.group(2) >= lo and m.group(1) <= hi:
          progs[m.group(3)].append(re.sub(r'\s*<icon[^>]*/>', "", m.group(0)))

  out = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="Unified-MENA-EPG argon_epg">']
  body = []
  for cid in sorted(names):
      for name in names[cid]:
          e = html.escape(name, quote=True)
          out.append(f'  <channel id="{e}"><display-name>{e}</display-name></channel>')
          body += [re.sub(r'channel="[^"]*"', f'channel="{e}"', p, count=1) for p in progs[cid]]
  out += body + ["</tv>"]
  open(OUT, "w", encoding="utf-8").write("\n".join(out) + "\n")
  print(f"{OUT}: {sum(map(len, names.values()))} channel names, {len(body)} programmes")


for names_file, out_file in PLAYLISTS:
    build(names_file, out_file)
