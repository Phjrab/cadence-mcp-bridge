#!/bin/bash
set -eu
ROOT=/home/buet/cds_work/.cadence_mcp/phase-campaign
VERSION="$ROOT/storage-real-qual-v1"
[ "$#" -eq 1 ] || exit 64
case "$1" in prepare|inspect) ;; *) exit 64 ;; esac
cd "$ROOT/storage-mgmt-v6"
sha256sum -c manifest.sha256 >/dev/null 2>&1 || exit 69
cd "$VERSION"
sha256sum -c manifest.sha256 >/dev/null 2>&1 || exit 69
exec /usr/bin/python "$VERSION/helper.py" "$1"
