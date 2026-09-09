#!/usr/bin/env bash
# Install Ubuntu packages on a GitHub runner without letting a
# third-party apt repository take this service off the air.
#
# WHY THIS EXISTS. GitHub's runner image ships apt sources for vendors
# this repository never installs from — Google Chrome among them. On
# the 9th of September 2026 Google served a Packages.gz whose hash did
# not match its own Release file:
#
#     E: Failed to fetch https://dl.google.com/linux/chrome-stable/...
#        Hash Sum mismatch
#     E: Some index files failed to download.
#     Process completed with exit code 100
#
# apt-get update returned 100, the step died, and because EVERY
# workflow here begins "apt-get update && apt-get install", all three
# publishing workflows went down inside thirty seconds — Build every
# EPG, Build today's matches and Channel 6 — for a repository we do not
# use, hosting a browser we do not install.
#
# The fix is not to retry it. It is to stop an unrelated third party
# from being able to do that at all:
#
#   1. drop the apt sources this repository never installs from,
#   2. refresh TOLERANTLY, because a failed refresh is not the signal,
#   3. install STRICTLY, because the install is.
#
# Everything this service needs — tesseract, ffmpeg, fonts — comes from
# Ubuntu's own archive. If THAT is unreachable the install fails with a
# far better error than "Hash Sum mismatch", and the step fails then,
# which is correct.
#
# Usage:  tools/apt_install.sh ffmpeg fonts-noto-core
set -uo pipefail

if [ "$#" -eq 0 ]; then
  echo "apt_install: no packages named" >&2
  exit 64
fi

# The vendors GitHub preinstalls and this repository does not use. Named
# rather than "everything that is not Ubuntu", so a source somebody adds
# here on purpose is not silently thrown away.
UNUSED='^(google|.*chrome|microsoft|.*mssql|.*msprod|yarn|docker|azure|.*postgresql).*'

shopt -s nullglob
for list in /etc/apt/sources.list.d/*; do
  name=$(basename "$list")
  if [[ "$name" =~ $UNUSED ]]; then
    echo "apt_install: dropping unused apt source $name"
    sudo rm -f "$list"
  fi
done
shopt -u nullglob

# And the same vendors if they were written into the main list instead.
if [ -f /etc/apt/sources.list ] && grep -qE 'dl\.google\.com|packages\.microsoft\.com' /etc/apt/sources.list; then
  echo "apt_install: commenting out unused vendors in /etc/apt/sources.list"
  sudo sed -i -E 's#^(deb.*(dl\.google\.com|packages\.microsoft\.com).*)$#\# \1#' \
    /etc/apt/sources.list
fi

if ! sudo apt-get update -qq; then
  echo "apt_install: apt-get update was not clean — going on to the" \
       "install, which is the test that matters"
fi

sudo apt-get install -y --no-install-recommends "$@"
