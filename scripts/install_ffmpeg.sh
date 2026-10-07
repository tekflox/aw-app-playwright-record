#!/bin/sh
set -eu
if ffmpeg -version >/dev/null 2>&1; then exit 0; fi
sudo apt-get update
sudo apt-get install -y --reinstall ffmpeg
ffmpeg -version >/dev/null
