"""Exercise the fixed Stage B IPC verifier without loading installed PDK code."""

from hashlib import sha256
from inspect import getfile
from io import BytesIO
from subprocess import run
from sys import executable
from unittest import TestCase
from unittest.mock import patch

from cadence_mcp_bridge import _mos_pmos_width_callback as verifier


def _frame(payload: bytes, *, slot: bytes = b"pmos1v|w") -> BytesIO:
    header = slot + b"|" + str(len(payload)).encode("ascii") + b"\n"
    return BytesIO(header + payload + b"\nEND\n")


class PmosWidthCallbackTest(TestCase):
    def test_uses_only_the_enrolled_digest(self) -> None:
        self.assertEqual(
            verifier.PMOS_WIDTH_CALLBACK_SHA256,
            b"ee118e38a0bd277bb6fe1ac2a66d1b0d722813192e121a1615fcfa43464ce4ca",
        )
        payload = b"synthetic fixture\nwith a second line"
        self.assertFalse(verifier.check_width_callback(_frame(payload)))
        test_pin = sha256(payload).hexdigest().encode("ascii")
        with patch.object(verifier, "PMOS_WIDTH_CALLBACK_SHA256", test_pin):
            self.assertTrue(verifier.check_width_callback(_frame(payload)))
            self.assertFalse(verifier.check_width_callback(_frame(payload + b" ")))

    def test_rejects_other_slots_and_invalid_framing(self) -> None:
        payload = b"abc"
        test_pin = sha256(payload).hexdigest().encode("ascii")
        with patch.object(verifier, "PMOS_WIDTH_CALLBACK_SHA256", test_pin):
            for stream in (
                _frame(payload, slot=b"nmos1v|w"),
                _frame(payload, slot=b"pmos1v|fw"),
                _frame(payload, slot=b"pmos1v|l"),
                BytesIO(b"pmos1v|w|03\nabc\nEND\n"),
                BytesIO(b"pmos1v|w|0\n\nEND\n"),
                BytesIO(b"pmos1v|w|3\nab"),
                BytesIO(b"pmos1v|w|3\nabc\nOTHER\n"),
            ):
                with self.subTest(frame=stream.getvalue()):
                    self.assertFalse(verifier.check_width_callback(stream))

    def test_size_limit_exact_endpoint(self) -> None:
        limit = b"a" * 4096
        for payload, expected in ((limit, True), (limit + b"a", False)):
            with patch.object(
                verifier, "PMOS_WIDTH_CALLBACK_SHA256", sha256(payload).hexdigest().encode("ascii")
            ):
                self.assertEqual(verifier.check_width_callback(_frame(payload)), expected)

    def test_cli_refuses_wrong_interpreter_without_echo(self) -> None:
        result = run(
            [executable, getfile(verifier)],
            input=_frame(b"private payload").getvalue(),
            capture_output=True,
            check=False,
            timeout=5,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (69, b"", b""))
