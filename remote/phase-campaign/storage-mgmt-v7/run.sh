#!/bin/bash
set -eu
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/storage-mgmt-v7"
[ "$#" -eq 3 ] || exit 64
case "$1" in ''|*[!0-9a-f]*) exit 64 ;; esac
[ "${#1}" -eq 64 ] || exit 64
case "$2" in inventory|cleanup) ;; *) exit 64 ;; esac
case "$3" in ''|*[!0-9a-f]*) exit 64 ;; esac
[ "${#3}" -ge 2 ] && [ "${#3}" -le 16384 ] || exit 64
[ "$(( ${#3} % 2 ))" -eq 0 ] || exit 64
cd "$VERSION"
sha256sum -c manifest.sha256 >/dev/null 2>&1 || exit 69
RUNTIME="$VERSION/runtime/$1"
[ "$(sha256sum "$RUNTIME/manifest.json" | cut -d ' ' -f 1)" = "$1" ] || exit 69
exec /usr/bin/python -B "$RUNTIME/storage.py" "$2" "$3"
