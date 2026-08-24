#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runs the info channel as a real 24/7 HLS stream.

Pipeline: the renderer produces raw RGB frames -> ffmpeg encodes them to
H.264 with a silent AAC track -> HLS segments land in a directory that the
built-in web server publishes. An IPTV player adds the resulting .m3u8 the
same way it adds any other channel.

    python3 stream.py                         # serve on :8080, guide from GitHub
    python3 stream.py --preview shot.png      # just draw one frame and exit

ffmpeg is restarted automatically if it ever dies, and a failed guide
refresh keeps the last good data on screen instead of blanking it.
"""

from __future__ import annotations

import argparse
import http.server
import os
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

from epg_source import DEFAULT_EPG_URL, EPGSource, wait_for_first_load
from renderer import Renderer

UTC = timezone.utc
_shutdown = threading.Event()


def log(msg: str) -> None:
    print(f"[stream] {msg}", flush=True)


def local_ip() -> str:
    """Best-effort LAN address, for printing a URL the user can actually type."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:  # noqa: BLE001
        return "127.0.0.1"


# --- HTTP -------------------------------------------------------------------
class Handler(http.server.SimpleHTTPRequestHandler):
    """Serves the HLS directory, plus a ready-made .m3u playlist."""

    channel_name = "MENA Sports Info"
    channel_id = "MENAInfo"
    stream_file = "info.m3u8"

    def __init__(self, *args, directory: str | None = None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def log_message(self, fmt: str, *args) -> None:  # keep the console readable
        pass

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        # Players must never cache the rolling playlist or they stall on a
        # stale segment list.
        if self.path.endswith(".m3u8") or self.path.endswith(".m3u"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        if self.path.split("?")[0] in ("/playlist.m3u", "/playlist", "/"):
            host = self.headers.get("Host") or f"{local_ip()}:8080"
            body = (
                "#EXTM3U\n"
                f'#EXTINF:-1 tvg-id="{self.channel_id}" '
                f'tvg-name="{self.channel_name}" group-title="INFO",'
                f"{self.channel_name}\n"
                f"http://{host}/{self.stream_file}\n"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "audio/x-mpegurl")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(directory: str, port: int, name: str) -> ThreadedHTTPServer:
    Handler.channel_name = name

    def factory(*args, **kwargs):
        return Handler(*args, directory=directory, **kwargs)

    httpd = ThreadedHTTPServer(("0.0.0.0", port), factory)
    threading.Thread(target=httpd.serve_forever, name="http", daemon=True).start()
    return httpd


# --- ffmpeg -----------------------------------------------------------------
def build_ffmpeg_cmd(args, out_dir: str) -> list[str]:
    gop = max(2, args.fps * 2)
    return [
        args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin",
        # video: raw frames on stdin
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{args.width}x{args.height}", "-r", str(args.fps), "-i", "pipe:0",
        # audio: silence, because some players reject a video-only stream
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-map", "0:v", "-map", "1:a", "-shortest",
        "-c:v", "libx264", "-preset", args.preset, "-tune", "stillimage",
        "-profile:v", "main", "-pix_fmt", "yuv420p",
        "-b:v", f"{args.bitrate}k", "-maxrate", f"{args.bitrate}k",
        "-bufsize", f"{args.bitrate * 2}k",
        "-g", str(gop), "-keyint_min", str(args.fps), "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", "64k", "-ar", "48000", "-ac", "2",
        "-f", "hls", "-hls_time", "4", "-hls_list_size", "6",
        "-hls_flags", "delete_segments+independent_segments+omit_endlist+program_date_time",
        "-hls_segment_type", "mpegts",
        "-hls_segment_filename", os.path.join(out_dir, "seg_%05d.ts"),
        os.path.join(out_dir, "info.m3u8"),
    ]


def start_ffmpeg(args, out_dir: str) -> subprocess.Popen:
    cmd = build_ffmpeg_cmd(args, out_dir)
    log(f"starting ffmpeg ({args.width}x{args.height} @ {args.fps}fps, {args.bitrate}kbps)")
    return subprocess.Popen(cmd, stdin=subprocess.PIPE)


# --- main loop --------------------------------------------------------------
def run(args) -> int:
    source = EPGSource(
        args.epg,
        refresh_seconds=args.refresh,
        channel_filter=args.channels,
        exclude_filter=args.exclude_channels,
        sports_only=not args.all_programmes,
    )
    if not wait_for_first_load(source):
        log("FATAL: could not load the guide even once — check --epg and network")
        return 1
    source.start_refresh_thread()

    tz = None
    if args.tz:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(args.tz)
        except Exception as exc:  # noqa: BLE001
            log(f"WARN unknown timezone {args.tz!r} ({exc}); using system local time")

    renderer = Renderer(args.width, args.height, title=args.title,
                        subtitle=args.subtitle, tz=tz)

    # --preview: draw and save, no encoder needed. Handy for checking the
    # design on a machine that has no ffmpeg.
    if args.preview:
        now = datetime.now(UTC)
        live, upcoming = source.live_now(now), source.upcoming(now)
        pages = Renderer.page_count(live, upcoming)
        base, ext = os.path.splitext(args.preview)
        for page in range(min(args.preview_pages, pages)):
            img = renderer.frame(now, live, upcoming, page=page, pages=pages,
                                 updated=source.loaded_at)
            path = args.preview if args.preview_pages == 1 else f"{base}_{page + 1}{ext or '.png'}"
            img.save(path)
            log(f"wrote {path}")
        return 0

    if not shutil.which(args.ffmpeg):
        log(f"FATAL: {args.ffmpeg} not found. Install ffmpeg, or use --preview.")
        return 1

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    for stale in os.listdir(out_dir):
        if stale.endswith((".ts", ".m3u8")):
            try:
                os.remove(os.path.join(out_dir, stale))
            except OSError:
                pass

    httpd = serve(out_dir, args.port, args.title) if not args.no_serve else None
    if httpd:
        ip = local_ip()
        log(f"playlist : http://{ip}:{args.port}/playlist.m3u   <- add this to your IPTV app")
        log(f"stream   : http://{ip}:{args.port}/info.m3u8")

    proc = start_ffmpeg(args, out_dir)
    frame_interval = 1.0 / args.fps
    next_frame = time.monotonic()
    started = time.monotonic()

    cached_at = 0.0
    live: list = []
    upcoming: list = []
    frames = 0

    try:
        while not _shutdown.is_set():
            if proc.poll() is not None:
                log(f"WARN ffmpeg exited with {proc.returncode}; restarting in 2s")
                time.sleep(2)
                proc = start_ffmpeg(args, out_dir)
                next_frame = time.monotonic()

            now = datetime.now(UTC)
            monotonic = time.monotonic()

            # Re-slice the guide once a second, not once a frame.
            if monotonic - cached_at >= 1.0:
                live = source.live_now(now)
                upcoming = source.upcoming(now)
                cached_at = monotonic

            pages = Renderer.page_count(live, upcoming)
            page = int((monotonic - started) // args.rotate) % pages

            frame = renderer.frame(now, live, upcoming, page=page, pages=pages,
                                   updated=source.loaded_at)
            try:
                proc.stdin.write(frame.tobytes())
            except (BrokenPipeError, ValueError):
                log("WARN lost the ffmpeg pipe; restarting encoder")
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
                proc = start_ffmpeg(args, out_dir)
                next_frame = time.monotonic()
                continue

            frames += 1
            if frames % (args.fps * 300) == 0:  # every ~5 minutes
                log(f"alive | {frames} frames | live={len(live)} upcoming={len(upcoming)}")

            next_frame += frame_interval
            delay = next_frame - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                next_frame = time.monotonic()  # fell behind; resync rather than sprint
    finally:
        log("shutting down")
        source.stop()
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass
        if httpd:
            httpd.shutdown()
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="24/7 info channel built from the Unified MENA EPG guide.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--epg", default=DEFAULT_EPG_URL,
                   help="XMLTV guide: an http(s) URL or a local file path")
    p.add_argument("--refresh", type=int, default=300, help="guide refresh interval, seconds")
    p.add_argument("--out", default="hls", help="directory for HLS segments")
    p.add_argument("--port", type=int, default=8080, help="port for the built-in web server")
    p.add_argument("--no-serve", action="store_true",
                   help="only write HLS files; serve them with your own web server")

    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=5,
                   help="5 is plenty: only the clock moves")
    p.add_argument("--bitrate", type=int, default=900, help="video bitrate in kbps")
    p.add_argument("--preset", default="veryfast", help="x264 preset")
    p.add_argument("--ffmpeg", default="ffmpeg", help="path to the ffmpeg binary")

    p.add_argument("--rotate", type=int, default=12, help="seconds per page")
    p.add_argument("--tz", default="Asia/Riyadh", help="timezone for displayed times")
    p.add_argument("--title", default="MENA SPORTS INFO")
    p.add_argument("--subtitle", default="دليل المباريات المباشر · يتحدث تلقائياً")

    p.add_argument("--channels", default=None,
                   help="regex: only channels whose id/name matches are shown")
    p.add_argument("--exclude-channels", default=None, help="regex: channels to hide")
    p.add_argument("--all-programmes", action="store_true",
                   help="show every programme, not just sport")

    p.add_argument("--preview", default=None, metavar="PNG",
                   help="render frames to PNG files and exit (no ffmpeg needed)")
    p.add_argument("--preview-pages", type=int, default=1,
                   help="how many pages to write in --preview mode")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    def stop(_sig, _frm):
        _shutdown.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
