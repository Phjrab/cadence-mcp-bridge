#!/bin/bash
set -eu
ROOT=/home/buet/cds_work/.cadence_mcp
VERSION="$ROOT/phase-campaign/storage-mgmt-v6"
[ "$#" -eq 2 ] || exit 64
case "$1" in inventory|cleanup) ;; *) exit 64 ;; esac
case "$2" in ''|*[!0-9a-f]*) exit 64 ;; esac
[ "${#2}" -le 16384 ] || exit 64
cd "$VERSION"
sha256sum -c manifest.sha256 >/dev/null 2>&1 || exit 69
exec /usr/bin/python "$VERSION/worker.py" "$1" "$2"
