#!/bin/sh
# Fixed standard-VM operator entry point. No caller interpreter or script path.
# Isolation must be set before Python startup, not by migration.py afterwards.
[ "$#" -eq 2 ] || exit 64
case "$1" in
    inventory-existing|apply-existing|inventory-legacy-seal|seal-existing) ;;
    *) exit 64 ;;
esac
expected="$2"
[ "${#expected}" -eq 64 ] || exit 64
case "$expected" in *[!0123456789abcdef]*) exit 64 ;; esac
exec /usr/bin/python -E -s -B -c __CADENCE_DOMAIN_ENTRY__ "${0%/*}" "$1" "$expected"
