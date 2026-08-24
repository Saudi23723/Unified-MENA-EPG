# Self-contained info channel.
#
#   docker build -t mena-info infochannel/
#   docker run -d --restart unless-stopped -p 8080:8080 --name mena-info mena-info
#
# Then add http://<host>:8080/playlist.m3u to your IPTV player.

FROM python:3.12-slim

# ffmpeg does the encoding; the fonts decide whether Arabic renders at all.
# fonts-dejavu-core is the important one — it covers Arabic AND Latin in a
# single face, which is what keeps mixed titles free of .notdef boxes.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        fonts-dejavu-core \
        fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./

ENV PYTHONUNBUFFERED=1
EXPOSE 8080

# Writing segments to a tmpfs keeps constant rewrites off the disk.
VOLUME ["/tmp/hls"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python3 -c "import urllib.request,sys; \
        sys.exit(0 if b'#EXTM3U' in urllib.request.urlopen('http://127.0.0.1:8080/info.m3u8', timeout=4).read() else 1)"

ENTRYPOINT ["python3", "stream.py", "--out", "/tmp/hls", "--port", "8080"]
CMD ["--tz", "Asia/Riyadh"]
