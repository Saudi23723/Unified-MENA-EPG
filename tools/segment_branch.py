#!/usr/bin/env python3
"""
Keep the screens' video segments off main.

THE FAULT THIS REPLACES
-----------------------
Every screen that changes is re-encoded every pass, and every segment was
committed to main. Measured on 2026-09-23: in twelve hours main gained
4,333 new .ts files — 3.3 GB — against 1.8 MB of guide XML. Git keeps
every one of them for ever, so the repository grew by about 8 GB a day,
GitHub began answering pushes with "Repository is approaching its size
quota", and a checkout took up to twenty minutes. Past the quota a push is
refused, and every guide and every screen stops at once.

THE FIX
-------
The segments of the screens named in MOVED live on their own branch,
hls-segments, which is ONE commit with no parent, replaced on every
publish. Nothing accumulates there: a segment that no playlist, no ledger
and no pass in the last hour names is simply left out of the next commit.

Nothing a player or a pass sees changes:

  * The link a player holds does not change. The M3U names
    main/stream/<screen>.m3u8 exactly as before; only the lines INSIDE
    that playlist change, from "today_prayer_0.7cfe0327.ts" to the full
    raw.githubusercontent.com address of that file on hls-segments.

  * The working tree does not change. A pass still sees relative names
    in its playlists and the segments themselves in stream/, so the
    encoder, the gate, the HLS audit and quarantine read exactly what
    they read before. A git filter does the translation: "clean" writes
    the full address into what is committed, "smudge" takes it back out
    of what is checked out (see .gitattributes).

  * Segments are pushed BEFORE the main commit that names them, and a
    segment is never dropped while origin/main or this pass still names
    it, or within an hour of it first appearing — so a television
    holding a five-minute-cached playlist, or two runs publishing in the
    same minute, never meet a 404.

If this file is missing or fails, the filter passes the playlist through
unchanged and publish() returns False, so the pass publishes nothing
rather than a playlist naming segments that are not there.

Usage:
  segment_branch.py clean | smudge   git filter, stdin to stdout
  segment_branch.py setup            configure the filter, re-check-out
  segment_branch.py hydrate          bring named segments onto disk
  segment_branch.py publish          push the segment branch
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

BRANCH = "hls-segments"
REMOTE = "origin"
TRACKING = f"refs/remotes/{REMOTE}/{BRANCH}"
STREAM = "stream"
RAW = ("https://raw.githubusercontent.com/Saudi23723/Unified-MENA-EPG/"
       f"{BRANCH}/{STREAM}/")
MANIFEST = f"{STREAM}/segments.json"
FILTER = "hlsseg"

# The screens whose segments live on hls-segments: board prefix -> the
# playlist that names them. Adding a screen here is the whole switch, and
# it must be matched by two lines elsewhere, which segment_branch_selftest
# checks: its segments in .gitignore, and its playlist in .gitattributes.
MOVED: dict[str, str] = {
    "today_prayer_": "prayer.m3u8",
    # The four that change every pass, and so almost all of the growth.
    "today_news_": "news.m3u8",
    "dubai_news_": "dubai_news.m3u8",
    "other_sports_": "sports.m3u8",
    "dubai_sports_": "dubai_sports.m3u8",
    # Every other screen publish_screens publishes. The flight tracker is
    # its own workflow with its own publishing, and stays on main.
    "today_matches_": "screen.m3u8",
    "sporttv_": "sporttv.m3u8",
    "dubai_sporttv_": "dubai_sporttv.m3u8",
    "today_weather_": "weather.m3u8",
    "dubai_matches_": "dubai_screen.m3u8",
    "dubai_weather_": "dubai_weather.m3u8",
    "ball_sports_": "ball_sports.m3u8",
    "dubai_ball_sports_": "dubai_ball_sports.m3u8",
    "hoops_gridiron_": "hoops_gridiron.m3u8",
    "dubai_hoops_gridiron_": "dubai_hoops_gridiron.m3u8",
    "f1_": "f1.m3u8",
    "dubai_f1_": "dubai_f1.m3u8",
    "turkish_ppv_": "turkish_ppv.m3u8",
    "dubai_turkish_ppv_": "dubai_turkish_ppv.m3u8",
}

# A segment nothing names any more is still kept this long after it first
# appeared: the grace ledger's thirty minutes, the raw cache's five, and
# room for a run that pushed its segments but lost the race to main.
KEEP_UNNAMED = 60 * 60

ATTEMPTS = 5


def log(message: str) -> None:
    print(f"[segments] {message}", flush=True)


def git(*args: str, env=None, stdin: bytes | None = None,
        ) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, check=False,
                          env=env, input=stdin)


def out(done: subprocess.CompletedProcess) -> str:
    return done.stdout.decode("utf-8", "replace").strip()


def moved_prefix(name: str) -> str | None:
    """The MOVED prefix a segment file name belongs to, if any."""
    if not name.endswith(".ts"):
        return None
    best = None
    for prefix in MOVED:
        if name.startswith(prefix) and (best is None or len(prefix) > len(best)):
            best = prefix
    return best


# ─── the filter ────────────────────────────────────────────────────────

def clean_line(line: str) -> str:
    """A relative segment line becomes its address on hls-segments."""
    body = line.rstrip("\r\n")
    ending = line[len(body):]
    name = body.strip()
    if name and not name.startswith("#") and "://" not in name \
            and "/" not in name and moved_prefix(name):
        return RAW + name + ending
    return line


def smudge_line(line: str) -> str:
    """An address on hls-segments becomes the relative name again."""
    body = line.rstrip("\r\n")
    ending = line[len(body):]
    name = body.strip()
    if name.startswith(RAW) and moved_prefix(name[len(RAW):]):
        return name[len(RAW):] + ending
    return line


def run_filter(convert) -> int:
    data = sys.stdin.buffer.read().decode("utf-8")
    sys.stdout.buffer.write(
        "".join(convert(line) for line in data.splitlines(True))
        .encode("utf-8"))
    return 0


# ─── what a screen names ───────────────────────────────────────────────

def names_in(text: str, prefix: str) -> set[str]:
    """Every segment of this prefix a playlist or ledger text names."""
    found = set()
    for line in text.splitlines():
        for token in line.split():
            if token.startswith(RAW):
                token = token[len(RAW):]
            if token.endswith(".ts") and token.startswith(prefix) \
                    and moved_prefix(token) == prefix:
                found.add(token)
    return found


def named_on_disk(prefix: str) -> set[str]:
    wanted = set()
    for name in (MOVED[prefix], f"{prefix}keeping.txt", f"{prefix}previous.txt"):
        path = os.path.join(STREAM, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8", errors="replace") as handle:
                wanted |= names_in(handle.read(), prefix)
    return wanted


def named_at(revision: str, prefix: str) -> set[str]:
    wanted = set()
    for name in (MOVED[prefix], f"{prefix}keeping.txt", f"{prefix}previous.txt"):
        shown = git("show", f"{revision}:{STREAM}/{name}")
        if shown.returncode == 0:
            wanted |= names_in(shown.stdout.decode("utf-8", "replace"), prefix)
    return wanted


def on_disk() -> dict[str, str]:
    """Every moved segment in stream/, name -> path."""
    if not os.path.isdir(STREAM):
        return {}
    return {name: os.path.join(STREAM, name) for name in os.listdir(STREAM)
            if moved_prefix(name)}


# ─── setup, hydrate, untrack ───────────────────────────────────────────

def setup() -> None:
    """Configure the filter in this clone and re-check-out the playlists.

    actions/checkout writes the playlists before the filter exists, so
    they arrive with full addresses in them. Each is checked out again
    through the filter — but only while it still holds an address, so a
    playlist this pass has already rewritten is never touched.
    """
    # Git runs a filter from the top of the working tree, so the path is
    # relative to that, whatever directory this was started from.
    git("config", f"filter.{FILTER}.clean",
        "python3 tools/segment_branch.py clean")
    git("config", f"filter.{FILTER}.smudge",
        "python3 tools/segment_branch.py smudge")
    for playlist in MOVED.values():
        path = os.path.join(STREAM, playlist)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            if RAW not in handle.read():
                continue
        if git("ls-files", "--error-unmatch", "--", path).returncode != 0:
            continue
        os.remove(path)
        git("checkout", "--", path)
        log(f"{path} checked out with relative names")


def fetch() -> str | None:
    """Fetch hls-segments; its commit, or None if it does not exist yet."""
    git("fetch", "--quiet", "--no-tags", REMOTE,
        f"+refs/heads/{BRANCH}:{TRACKING}")
    done = git("rev-parse", "--verify", "--quiet", TRACKING)
    return out(done) or None


def hydrate() -> int:
    """Bring every segment a moved screen names onto disk.

    What a checkout of main used to put there. Only ever ADDS: a segment
    on disk that nothing names is the encoder sweep's to retire, exactly
    as before. Returns how many named segments could not be found.
    """
    tip = fetch()
    missing = 0
    fetched = 0
    for prefix in MOVED:
        for name in sorted(named_on_disk(prefix)):
            path = os.path.join(STREAM, name)
            if os.path.exists(path):
                continue
            blob = git("cat-file", "blob", f"{TRACKING}:{STREAM}/{name}") \
                if tip else None
            if blob is None or blob.returncode != 0:
                missing += 1
                log(f"::warning::{name} is named but not on {BRANCH} — the "
                    f"encoder re-encodes a lost segment")
                continue
            os.makedirs(STREAM, exist_ok=True)
            with open(path + ".part", "wb") as handle:
                handle.write(blob.stdout)
            os.replace(path + ".part", path)
            fetched += 1
    if fetched:
        log(f"{fetched} segment(s) brought onto disk from {BRANCH}")
    return missing


def untrack() -> None:
    """Make main's index right for the moved screens; disk is untouched.

    Their playlists are staged again through the filter — `git add`
    re-cleans a file only when its size or time changed, so a playlist
    that did not change this pass would otherwise keep whatever form was
    staged before, relative names included — and their segments leave
    the index while staying on disk.
    """
    setup()
    for playlist in MOVED.values():
        path = os.path.join(STREAM, playlist)
        if os.path.exists(path):
            git("add", "--renormalize", "--", path)
    # A segment main still carries from before its screen moved leaves
    # main only once nothing on disk names it — the encoder's own grace,
    # thirty minutes after it left the playlist. A television that cached
    # the last playlist with relative names asks main for those files, and
    # they have to be there until that playlist has aged out. A new
    # segment is never tracked in the first place: .gitignore keeps it out.
    named = set()
    for prefix in MOVED:
        named |= named_on_disk(prefix)
    listed = out(git("ls-files", "--", STREAM)).splitlines()
    tracked = [path for path in listed
               if moved_prefix(os.path.basename(path))
               and os.path.basename(path) not in named]
    for start in range(0, len(tracked), 200):
        git("rm", "--cached", "--quiet", "--", *tracked[start:start + 200])
    if tracked:
        log(f"{len(tracked)} retired segment(s) no longer tracked on main")


# ─── publish ───────────────────────────────────────────────────────────

def publish() -> bool:
    """Replace hls-segments with every segment still wanted.

    Wanted: every moved segment on disk (what this pass publishes and
    spares), every one origin/main or HEAD names, and every one first
    seen less than KEEP_UNNAMED ago. True when hls-segments holds all of
    it — pushed now, or already there.
    """
    git("fetch", "--quiet", "--no-tags", REMOTE, "main")
    for attempt in range(1, ATTEMPTS + 1):
        tip = fetch()
        before: dict[str, str] = {}
        manifest: dict[str, float] = {}
        if tip:
            for line in out(git("ls-tree", "-r", tip, "--", STREAM)).splitlines():
                meta, _, path = line.partition("\t")
                parts = meta.split()
                if len(parts) == 3 and parts[1] == "blob":
                    before[path] = parts[2]
            shown = git("show", f"{tip}:{MANIFEST}")
            if shown.returncode == 0:
                try:
                    manifest = {k: float(v) for k, v in
                                json.loads(shown.stdout).items()}
                except (ValueError, TypeError, AttributeError):
                    manifest = {}

        now = time.time()
        named: set[str] = set()
        for prefix in MOVED:
            named |= named_on_disk(prefix)
            named |= named_at(f"{REMOTE}/main", prefix)
            named |= named_at("HEAD", prefix)

        after: dict[str, str] = {}
        seen: dict[str, float] = {}
        for path, blob in before.items():
            if path == MANIFEST:
                continue
            name = os.path.basename(path)
            first = manifest.get(name, now)
            if name in named or now - first < KEEP_UNNAMED:
                after[path] = blob
                seen[name] = first
        for name, path in on_disk().items():
            done = git("hash-object", "-w", "--", path)
            if done.returncode != 0:
                log(f"::error::could not store {path}")
                return False
            after[f"{STREAM}/{name}"] = out(done)
            seen.setdefault(name, manifest.get(name, now))

        # What the commit about to go to main names must ALL be here, or
        # main is not pushed: that is a playlist pointing at a 404.
        head_named = set()
        for prefix in MOVED:
            head_named |= named_at("HEAD", prefix)
        lost = sorted(name for name in head_named
                      if f"{STREAM}/{name}" not in after)
        if lost:
            log(f"::error::the commit for main names {len(lost)} segment(s) "
                f"that are neither on disk nor on {BRANCH}: "
                f"{', '.join(lost[:5])} — main is not pushed")
            return False
        stale = sorted(name for name in named - head_named
                       if f"{STREAM}/{name}" not in after)
        if stale:
            log(f"{len(stale)} segment(s) named only by an older copy are "
                f"already gone from {BRANCH}")

        payload = json.dumps(dict(sorted(seen.items())), indent=0).encode()
        stored = git("hash-object", "-w", "--stdin", stdin=payload)
        after[MANIFEST] = out(stored)

        unchanged = {k: v for k, v in after.items() if k != MANIFEST} == \
                    {k: v for k, v in before.items() if k != MANIFEST}
        if tip and unchanged:
            log(f"{BRANCH} already holds every segment ({len(after) - 1})")
            return True

        index = os.path.join(git_dir(), f"{BRANCH}.index")
        env = dict(os.environ, GIT_INDEX_FILE=index)
        if os.path.exists(index):
            os.remove(index)
        git("read-tree", "--empty", env=env)
        listing = "".join(f"100644 {blob}\t{path}\n"
                          for path, blob in sorted(after.items()))
        if git("update-index", "--index-info", env=env,
               stdin=listing.encode()).returncode != 0:
            log("::error::could not build the segment tree")
            return False
        tree = out(git("write-tree", env=env))
        os.remove(index)
        commit = out(git("commit-tree", tree, "-m",
                         f"HLS segments ({len(after) - 1})", env=env))
        if not commit:
            log("::error::could not commit the segment tree")
            return False

        lease = f"--force-with-lease=refs/heads/{BRANCH}:{tip or ''}"
        pushed = git("push", "--quiet", lease, REMOTE,
                     f"{commit}:refs/heads/{BRANCH}")
        if pushed.returncode == 0:
            added = len(set(after) - set(before) - {MANIFEST})
            dropped = len(set(before) - set(after) - {MANIFEST})
            log(f"{BRANCH} pushed: {len(after) - 1} segment(s), "
                f"{added} added, {dropped} dropped")
            git("update-ref", TRACKING, commit)
            return True
        log(f"{BRANCH} moved under this push, trying again "
            f"({attempt}/{ATTEMPTS}): "
            f"{pushed.stderr.decode('utf-8', 'replace').strip()[-200:]}")
        time.sleep(2 + attempt)
    log(f"::error::could not push {BRANCH} after {ATTEMPTS} attempts")
    return False


def head_problems() -> list[str]:
    """Why the commit about to go to main must not go, if it must not.

    Every moved playlist in HEAD must name its segments by their address
    on hls-segments. A relative name there means the filter did not run —
    and main no longer carries the file it names, so a player would get a
    404. Checked on the commit itself, not on the working tree.
    """
    problems = []
    for prefix, playlist in MOVED.items():
        shown = git("show", f"HEAD:{STREAM}/{playlist}")
        if shown.returncode != 0:
            continue
        for line in shown.stdout.decode("utf-8", "replace").splitlines():
            name = line.strip()
            if name.endswith(".ts") and not name.startswith("#") \
                    and not name.startswith(RAW):
                problems.append(f"{STREAM}/{playlist} names {name} without "
                                f"its {BRANCH} address")
                break
    return problems


def consistency() -> list[str]:
    """MOVED, .gitignore and .gitattributes must describe the same screens.

    A moved playlist without its filter line would be committed with
    relative names, and head_problems would then hold back every screen
    until it is fixed; a moved prefix missing from .gitignore only costs
    untrack() some work. Both are caught here, in CI, before a merge.
    """
    problems = []
    for prefix, playlist in MOVED.items():
        path = f"{STREAM}/{playlist}"
        attr = out(git("check-attr", "filter", "--", path))
        if not attr.endswith(f": {FILTER}"):
            problems.append(f"{path} has no 'filter={FILTER}' in .gitattributes")
        probe = f"{STREAM}/{prefix}0.00000000.ts"
        if git("check-ignore", "-q", "--no-index", "--", probe).returncode != 0:
            problems.append(f"{STREAM}/{prefix}*.ts is not in .gitignore")
    return problems


def git_dir() -> str:
    return out(git("rev-parse", "--absolute-git-dir"))


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    if command == "clean":
        return run_filter(clean_line)
    if command == "smudge":
        return run_filter(smudge_line)
    if command == "setup":
        setup()
        return 0
    if command == "hydrate":
        setup()
        return 1 if hydrate() else 0
    if command == "publish":
        return 0 if publish() else 1
    if command == "check":
        problems = consistency()
        for problem in problems:
            print(f"FAIL {problem}")
        print("segment branch configuration: "
              + ("consistent" if not problems else f"{len(problems)} problem(s)"))
        return 1 if problems else 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
