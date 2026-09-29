"""Synthetic child only: no identity, ledger, collector, deployment or network access."""

import sys
import time

mode = sys.argv[1]
success = b'{"success":true,"code":"LOCAL_PREFLIGHT_READY"}\n'
if mode == "success":
    sys.stdout.buffer.write(success)
elif mode == "failure":
    sys.stdout.buffer.write(b'{"success":false,"code":"LINEAGE_INVALID"}\n')
    sys.exit(1)
elif mode == "extra":
    sys.stdout.buffer.write(success + success)
elif mode == "secret":
    sys.stdout.buffer.write(b'{"success":true,"code":"synthetic-private-canary"}\n')
elif mode == "invalid_utf8":
    sys.stdout.buffer.write(b"\xff\xfe")
elif mode == "exact_limit":
    sys.stdout.buffer.write(b"z" * 512)
elif mode == "over_limit":
    sys.stdout.buffer.write(b"z" * 513)
elif mode == "stderr":
    sys.stderr.buffer.write(b"synthetic-private-canary")
elif mode in {"flood", "stderr_flood"}:
    stream = sys.stderr.buffer if mode == "stderr_flood" else sys.stdout.buffer
    while True:
        stream.write(b"z" * 4096)
        stream.flush()
elif mode == "timeout":
    time.sleep(30)
elif mode == "partial_timeout":
    sys.stdout.buffer.write(success[:10])
    sys.stdout.buffer.flush()
    time.sleep(30)
elif mode == "wrong_exit":
    sys.stdout.buffer.write(success)
    sys.exit(1)
elif mode == "empty":
    pass
else:
    raise SystemExit(2)
