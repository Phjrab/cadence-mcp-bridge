"""Local tests for the fixed MOS sizing program, without a Cadence session."""

from hashlib import sha256
from typing import Literal, cast
from unittest import TestCase

from cadence_mcp_bridge.mos_wl_skill import render_mos_wl_skill


class MosWlSkillTest(TestCase):
    def test_minimal_length_only_program(self) -> None:
        program = render_mos_wl_skill("nmos1v", length_nm="250")
        self.assertEqual(program, render_mos_wl_skill("nmos1v", length_nm="250"))
        self.assertTrue(program.isascii())
        self.assertTrue(program.endswith(b'inst "nmos1v" "250n" nil list(list("l" "250n"))))\n'))
        self.assertNotIn(b"dbOpenCellView", program)
        self.assertNotIn(b"dbSave(", program)
        self.assertNotIn(b"load(", program)

    def test_width_driver_requires_explicit_selection_and_follows_length(self) -> None:
        self.assertTrue(
            render_mos_wl_skill(
                "pmos1v", length_nm="350.25", width_nm="3000", width_field="fw"
            ).endswith(
                b'inst "pmos1v" "350.25n" "3000n" list(list("l" "350.25n") list("fw" "3000n"))))\n'
            )
        )
        with self.assertRaises(ValueError):
            render_mos_wl_skill("pmos1v", width_nm="3000")
        with self.assertRaises(ValueError):
            render_mos_wl_skill("pmos1v", length_nm="350", width_field="w")
        with self.assertRaises(ValueError):
            render_mos_wl_skill(
                "pmos1v", width_nm="3000", width_field=cast('Literal["w", "fw"]', "m")
            )

    def test_invalid_or_executable_input_cannot_enter_source(self) -> None:
        for bad in (
            "",
            "0",
            "0.0",
            "-1",
            "+100",
            "1e3",
            "250n",
            "250 ",
            "２５０",
            "9" * 25,
            '250")\nexit(0)',
            cast(str, True),
        ):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                render_mos_wl_skill("nmos1v", length_nm=bad)
        with self.assertRaises(ValueError):
            render_mos_wl_skill(cast('Literal["nmos1v", "pmos1v"]', "nmos2v"), length_nm="250")
        with self.assertRaises(ValueError):
            render_mos_wl_skill("nmos1v")

    def test_lifecycle_uses_observed_hooks_and_verified_live_bytes(self) -> None:
        program = render_mos_wl_skill("nmos1v", length_nm="250").decode("ascii")
        steps = (
            "mcpMosVerifyCallbacks(mcpInst mcpCallbacks)==t",
            "PasCdfFormInit(cdfgData)",
            "mcpParam~>value=cadr(mcpStep)",
            "errset(evalstring(cadr(mcpPair)) t)",
            'dbReplaceProp(mcpInst mcpField "string" mcpNewValue)',
            "PasCdfDone(mcpInst)",
            "mcpEffective=cdfGetInstCDF(mcpInst)",
            "MCP_MOS_WL_READY_FOR_SAVE_CHECK",
        )
        offset = -1
        for step in steps:
            offset = program.index(step, offset + 1)
        self.assertEqual(program.count("evalstring("), 1)
        self.assertIn('mcpFields=list("l" "w" "fw" "as" "ad" "ps" "pd")', program)
        for name, expected in (
            ("PasCdfFormInit", "ac248a8a9ce23377cfa88f36fe9713fe800d5222e76eb1a2bf2c3347c748aa8f"),
            ("PasCdfDone", "34f50fc5aaf6011d033d5292e97dd8e8b9c0779f873450038820c7652f7f0612"),
        ):
            self.assertIn(f'=="{name}"', program)
            self.assertEqual(sha256(name.encode("ascii")).hexdigest(), expected)
