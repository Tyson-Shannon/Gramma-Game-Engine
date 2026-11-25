"""Conformance checks for NES mirroring and DMC asset generation.

The C side of these features is covered by tests/test_nes_depth.c and by the
nes-py ROM smoke check. This module verifies that the Python build driver makes
the same choices: mirroring bits reach the iNES header defines, DMC samples are
encoded and aligned, and non-NES targets stay portable.
"""

from __future__ import annotations

import contextlib
import io
import math
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "tools" / "gr"))

from gramma_cli.main import (  # noqa: E402
    _mapper_override, _nes_linker_config, build_parser)
from gramma_pipeline import (  # noqa: E402
    check_budget, check_budget_detailed, generate, load_project,
    nes_mapper_config)
from gramma_pipeline.audio import DMC_RATES_HZ, encode_dmc  # noqa: E402


def _write_wav(path: Path, frames: int = 1024, rate: int = 22050) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        samples = [int(12000 * math.sin(2 * math.pi * i / 32))
                   for i in range(frames)]
        wav.writeframes(b"".join(v.to_bytes(2, "little", signed=True)
                                 for v in samples))


def _write_project(root: Path, mapper: str = "nrom",
                   mirroring: str = "horizontal") -> None:
    (root / "project.toml").write_text(
        '[project]\nname = "nes-depth"\n\n'
        '[[audio]]\nname = "beep"\nfile = "beep.wav"\n'
        'sample_rate = 22050\ndmc_rate = 12\ndmc_loop = true\n\n'
        f'[mapper.nes]\nid = "{mapper}"\nmirroring = "{mirroring}"\n',
        encoding="utf-8")
    _write_wav(root / "beep.wav")


class MirroringConfigTests(unittest.TestCase):
    def test_mirroring_bits_match_ines_header(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_project(root)
            project = load_project(root)
            cfg = nes_mapper_config(project)
            self.assertEqual(cfg["id"], "nrom")
            self.assertEqual(cfg["mirroring"], "horizontal")
            self.assertEqual(cfg["mirror_bit"], 0)
            self.assertEqual(cfg["id_value"], 0)
            self.assertEqual(cfg["errors"], [])

            project.mapper["nes"]["mirroring"] = "vertical"
            self.assertEqual(nes_mapper_config(project)["mirror_bit"], 1)
            project.mapper["nes"]["mirroring"] = "four-screen"
            self.assertEqual(nes_mapper_config(project)["mirror_bit"], 8)

    def test_four_screen_requires_four_nametable_nrom_board(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_project(root)
            project = load_project(root)
            project.mapper["nes"]["mirroring"] = "four-screen"
            self.assertEqual(nes_mapper_config(project)["errors"], [])
            project.mapper["nes"]["id"] = "mmc3"
            manifest = generate(root, "nes", project)
            errors = check_budget_detailed(project, "nes", manifest)
            self.assertIn("budget.mapper", [item["code"] for item in errors])
            self.assertTrue(any("four-screen mirroring requires" in
                                item["message"] for item in errors))

    def test_unknown_mirroring_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_project(root)
            project = load_project(root)
            project.mapper["nes"]["mirroring"] = "diagonal"
            cfg = nes_mapper_config(project)
            self.assertEqual(cfg["mirror_bit"], 1)  # safe fallback
            self.assertTrue(any("unknown NES mirroring" in message
                                for message in cfg["errors"]))

    def test_cli_mirroring_override_reaches_generated_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_project(root, mapper="mmc1", mirroring="vertical")
            args = build_parser().parse_args([
                "check", "--mirroring", "horizontal"])
            override = _mapper_override(args)
            self.assertEqual(override, {"nes.mirroring": "horizontal"})
            project = load_project(root)
            manifest = generate(root, "nes", project, override)
            self.assertEqual(nes_mapper_config(project)["mirror_bit"], 0)
            self.assertEqual(check_budget(project, "nes", manifest), [])

            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    build_parser().parse_args([
                        "build", "--mirroring", "diagonal"])

    def test_default_mirroring_of_shipped_example(self):
        project = load_project(ROOT / "examples" / "test-kart")
        cfg = nes_mapper_config(project)
        self.assertEqual(cfg["mirroring"], "vertical")
        self.assertEqual(cfg["mirror_bit"], 1)
        self.assertEqual(cfg["errors"], [])


class DmcEncodingTests(unittest.TestCase):
    def test_rate_table_is_ordered(self):
        self.assertEqual(len(DMC_RATES_HZ), 16)
        self.assertEqual(DMC_RATES_HZ, tuple(sorted(DMC_RATES_HZ)))

    def test_silence_needs_no_dmc_bytes(self):
        self.assertEqual(encode_dmc([0.0] * 64, 22050, 15), b"")

    def test_step_direction_and_nibble_range(self):
        data = encode_dmc([-1.0, 1.0], DMC_RATES_HZ[15], 15)
        self.assertGreaterEqual(len(data), 24)
        self.assertEqual(data[0], 0x0e)  # -8 from the center level
        self.assertEqual(data[8], 0x0f)  # +8 from the bottom level
        self.assertTrue(all(0 <= byte < 16 for byte in data))

    def test_output_is_length_register_aligned(self):
        samples = [math.sin(2 * math.pi * i / 19) for i in range(200)]
        data = encode_dmc(samples, 22050, 12)
        self.assertGreater(len(data), 16)
        self.assertEqual(len(data) % 16, 0)
        self.assertLessEqual(len(data), 16384)
        looped = encode_dmc(samples, 22050, 12, loop=True)
        self.assertEqual(looped[0], 0)
        self.assertEqual(len(looped), len(data))

    def test_rate_index_is_validated(self):
        with self.assertRaises(ValueError):
            encode_dmc([0.5], 22050, 16)
        with self.assertRaises(ValueError):
            encode_dmc([0.5], 22050, -1)

    def test_out_of_range_dmc_rate_is_a_budget_violation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_project(root)
            project = load_project(root)
            project.audio[0].dmc_rate = 16
            manifest = generate(root, "nes", project)
            errors = check_budget_detailed(project, "nes", manifest)
            self.assertIn("budget.dmc_rate", [item["code"] for item in errors])


class AssetEmissionTests(unittest.TestCase):
    def test_nes_emits_dmc_assembly_and_manifest_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_project(root)
            manifest = generate(root, "nes")
            generated = root / "generated" / "nes"
            source = (generated / "beep.c").read_text(encoding="utf-8")
            asm = (generated / "beep_dmc.s").read_text(encoding="utf-8")

            self.assertIn("static const gr_dmc beep_dmc = {\n    12, ", source)
            self.assertIn("&beep_dmc\n};", source)
            self.assertIn('.segment "DMC"', asm)
            self.assertIn(".align 64", asm)
            self.assertIn(".export _beep_dmc_data", asm)
            self.assertIn(".byte $", asm)

            audio = next(a for a in manifest["assets"]
                         if a["kind"] == "audio")
            self.assertEqual(audio["dmc_rate"], 12)
            self.assertGreater(audio["dmc_bytes"], 0)
            self.assertEqual(audio["dmc_bytes"] % 16, 0)
            self.assertEqual(manifest["totals"]["rom_bytes"],
                             audio["rom_bytes"] + audio["dmc_bytes"])
            self.assertIn(str(generated / "beep_dmc.s"),
                          manifest["artifacts"]["sources"])

    def test_other_targets_do_not_reference_missing_dmc_symbols(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_project(root)
            for target in ("pc", "gb", "sms"):
                with self.subTest(target=target):
                    manifest = generate(root, target)
                    generated = root / "generated" / target
                    source = (generated / "beep.c").read_text(encoding="utf-8")
                    self.assertNotIn("gr_dmc", source)
                    self.assertIn("NULL\n};", source)
                    self.assertFalse(list(generated.glob("*_dmc.s")))
                    audio = next(a for a in manifest["assets"]
                                 if a["kind"] == "audio")
                    self.assertEqual(audio["dmc_bytes"], 0)


class RuntimeMarkerTests(unittest.TestCase):
    """Static guards for the assembly/C halves that need a console to run."""

    def test_crt0_wires_mirroring_bits_and_ctrl_shadow(self):
        source = (ROOT / "targets" / "nes" / "src" /
                  "nes_crt0.s").read_text(encoding="utf-8")
        self.assertIn("GR_NES_MIRROR", source)
        self.assertIn("GR_MMC1_MIRROR", source)
        self.assertIn("GR_MMC3_MIRROR", source)
        self.assertIn("| $02 | GR_MIRROR", source)
        self.assertIn("lda     NES_CTRL", source)
        self.assertIn("sta     PPU_CTRL1", source)

    def test_linker_config_aligns_dmc_segment(self):
        with tempfile.TemporaryDirectory() as directory:
            share = Path(directory) / "share"
            build = Path(directory) / "build"
            (share / "cfg").mkdir(parents=True)
            build.mkdir()
            (share / "cfg" / "nes.cfg").write_text(
                "MEMORY {\n"
                "    ROM0: file = %O, start = $8000, size = $7FFA;\n"
                "    ROM2: file = %O, start = $0000, size = $2000;\n"
                "}\n"
                "SEGMENTS {\n"
                "    RODATA:   load = ROM0,            type = ro,  define   = yes;\n"
                "}\n",
                encoding="utf-8")
            for prg_banks, chr_banks in ((2, 1), (2, 2), (4, 2)):
                with self.subTest(prg=prg_banks, chr=chr_banks):
                    config = _nes_linker_config(share, build, prg_banks,
                                                chr_banks)
                    self.assertIsNotNone(config)
                    self.assertIn(
                        "DMC:      load = ROM0,", config.read_text())
                    self.assertIn("align = 64;", config.read_text())

    def test_backend_uses_nametables_attributes_and_dmc(self):
        source = (ROOT / "targets" / "nes" / "src" /
                  "nes_backend.c").read_text(encoding="utf-8")
        self.assertIn("nes_nametable_base", source)
        self.assertIn("gr_bg_attribute", source)
        self.assertIn("APU.delta_mod.address", source)
        self.assertIn("def->dmc != NULL", source)


if __name__ == "__main__":
    unittest.main()
