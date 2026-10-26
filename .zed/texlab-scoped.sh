#!/bin/sh
set -eu

runtime_dir="/run/user/$(id -u)/texlab-public-space"
mkdir -p "$runtime_dir"
chmod 700 "$runtime_dir"
export XDG_RUNTIME_DIR="$runtime_dir"

exec /home/frank/.local/share/zed/remote_extensions/work/latex/texlab-v5.26.0/texlab "$@"
