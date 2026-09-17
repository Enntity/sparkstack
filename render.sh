#!/usr/bin/env bash
# Render wrapper.
#
# Cycles compiles its Metal kernels on the first GPU render of a session and
# caches them under $HOME/Library/Caches. Under a workspace-write sandbox that
# path is unwritable, so the compile is repeated on EVERY launch - measured at
# 152-208 s, against 10.8 s once the cache can persist. Point HOME somewhere
# writable so the ~63 MB cache survives between runs.
#
#   ./render.sh --background --python render_hive.py
#
# Harmless outside a sandbox, it just uses a local cache instead of the global.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

# Override if Blender lives somewhere else:
#   BLENDER=/path/to/blender ./render.sh --background --python render_hive.py
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
if [ ! -x "$BLENDER" ]; then
  echo "render.sh: no Blender at $BLENDER" >&2
  echo "set BLENDER=/path/to/blender and try again" >&2
  exit 1
fi

export HOME="$HERE/.blender_home"
mkdir -p "$HOME/Library/Caches"
exec "$BLENDER" "$@"
