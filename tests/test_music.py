"""Unit tests for the tracker score compiler and pipeline integration."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "pipeline"))

from gramma_pipeline import generate, load_project  # noqa: E402
from gramma_pipeline.music import (  # noqa: E402
    MusicError, _note_frequency, _psg_stream, compile_score, parse_score,
    process_music)


SAMPLE = """
; A tiny two-channel score.
bpm 120
fps 50
channels 2
wave triangle

pattern a
    C4:10 C3:11
    -     -
    E4:12 -
    off   off

order a
"""

PROJECT_TOML = """
[project]
name = "music-test"

[[music]]
name = "theme"
file = "assets/theme.tick"
"""


class ScoreParserTests(unittest.TestCase):
    def test_defaults_and_parsed_fields(self):
        score = parse_score("pattern a\n    C4:10\norder a\n", "mini.tick")
        self.assertEqual(score.bpm, 120)
        self.assertEqual(score.fps, 50)
        self.assertTrue(score.loop)
        self.assertEqual(score.channels, 1)
        self.assertEqual(score.wave, "square")
        self.assertEqual(len(score.rows), 1)

    def test_note_names_include_sharps_and_comment_markers(self):
        score = parse_score(
            "bpm 60 ; speed\nchannels 1\npattern p\n"
            "    A4:15 # the concert pitch\n"
            "    C#4:7\n    Db4:7\n    C-4:7\norder p\n", "notes.tick")
        midi = [row[0].midi for row in score.rows]
        self.assertEqual(midi, [69, 61, 61, 60])

    def test_note_frequency_mapping(self):
        self.assertEqual(_note_frequency(69), 440)
        self.assertEqual(_note_frequency(60), 262)
        self.assertEqual(_note_frequency(72), 523)

    def test_rejects_bad_scores(self):
        cases = [
            ("C4:10\norder p\n", "row outside a pattern"),
            ("channels 2\npattern p\n    C4:10\norder p\n", "row has 1 cell"),
            ("pattern p\n    H4:10\norder p\n", "invalid note"),
            ("pattern p\n    C4:16\norder p\n", "volume 16 exceeds 15"),
            ("pattern p\n    C9:10\norder p\n", "invalid note"),
            ("pattern p\n    C4:10\norder missing\n", "undefined pattern"),
            ("pattern p\n    C4:10\n", "missing order"),
            ("channels 5\npattern p\n    C4:10\norder p\n", "outside 1..4"),
            ("bpm 0\npattern p\n    C4:10\norder p\n", "outside 1..65535"),
            ("pattern p\n    C4:10\npattern p\n    C4:10\norder p\n",
             "duplicate pattern"),
            ("pattern p\norder p\n", "has no rows"),
            ("channels 1\nbpm 120\npattern p\n    C4:10\n"
             "channels 2\norder p\n", "before any pattern"),
            ("typo 1\npattern p\n    C4:10\norder p\n", "row outside"),
        ]
        for text, fragment in cases:
            with self.subTest(fragment=fragment):
                with self.assertRaises(MusicError) as caught:
                    parse_score(text, "bad.tick")
                self.assertIn(fragment, str(caught.exception))
        with self.assertRaises(MusicError) as caught:
            parse_score("typo 1\npattern p\n    C4:10\norder p\n", "bad.tick")
        self.assertIn("bad.tick:1:", str(caught.exception))


class MusicCompileTests(unittest.TestCase):
    def setUp(self):
        self.score = parse_score(SAMPLE, "sample.tick")

    def test_portable_notes_are_rle_with_lead_channel(self):
        result = compile_score(self.score, "theme", "sample.tick")
        self.assertEqual(result.note_count, 3)
        self.assertIn("{ 262, 2, 10, 0, GR_WAVE_TRIANGLE }", result.source_text)
        self.assertIn("{ 330, 1, 12, 0, GR_WAVE_TRIANGLE }", result.source_text)
        self.assertIn("{ 0, 1, 0, 0, GR_WAVE_TRIANGLE }", result.source_text)
        self.assertIn("NULL", result.source_text)
        self.assertEqual(result.psg_bytes, 0)
        self.assertEqual(result.frames, 24)
        self.assertEqual(result.duration_ms, 480)

    def test_psg_stream_structure(self):
        stream = _psg_stream(self.score)
        self.assertEqual(stream[0], 0x01)
        self.assertEqual(stream[-1], 0x00)
        self.assertEqual(stream.count(0x3d), len(self.score.rows))
        self.assertFalse(any(0x08 <= byte <= 0x37 for byte in stream))
        # C4 on channel 0: latch low nibble, data high nibble, volume latch/data.
        self.assertIn(0x8a, stream)  # 1000 1010 -> tone channel 0, low bits 10
        self.assertIn(0x5a, stream)  # 0101 1010 -> period high bits 0x1a
        self.assertIn(0x45, stream)  # 0100 0101 -> attenuation 15-10
        result = compile_score(self.score, "theme", "sample.tick", psg=True)
        self.assertEqual(result.psg_bytes, len(stream))
        self.assertIn("theme_psg", result.source_text)
        self.assertIn("const gr_song theme", result.source_text)
        self.assertNotIn("NULL", result.source_text)

    def test_psg_stream_loops_after_the_expected_number_of_frames(self):
        # Mirrors sms_psg_frame(): register writes are immediate, wait bytes
        # consume one frame each, and the end marker jumps to the loop marker.
        stream = _psg_stream(self.score)
        pos, loop, wait, frames = 0, None, 0, 0
        target = len(self.score.rows) * self.score.frames_per_row * 2
        while frames < target:
            if wait > 0:
                wait -= 1
                if wait > 0:
                    frames += 1
                    continue
            while True:
                byte = stream[pos]
                pos += 1
                if byte >= 0x40:
                    continue
                if byte >= 0x38:
                    wait = (byte & 0x07) + 1
                    break
                if byte == 0x01:
                    loop = pos
                elif byte == 0x00:
                    self.assertIsNotNone(loop)
                    pos = loop
                else:
                    self.fail(f"unsupported PSG byte 0x{byte:02x}")
            frames += 1
        self.assertEqual(frames, target)

    def test_one_shot_score_has_no_loop_marker(self):
        score = parse_score("loop off\npattern p\n    C4:10\norder p\n")
        self.assertEqual(_psg_stream(score)[0], 0x8a)  # first latch byte
        self.assertNotIn(0x01, _psg_stream(score))
        result = compile_score(score, "sting", "s.tick", psg=True)
        self.assertIn("false, sting_psg", result.source_text)

    def test_generated_c_is_c89_clean(self):
        for psg in (False, True):
            with self.subTest(psg=psg):
                source = compile_score(self.score, "theme", "sample.tick",
                                       psg=psg).source_text
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "theme.c"
                    path.write_text(source, encoding="utf-8")
                    command = ["gcc", "-std=c89", "-pedantic", "-Wall",
                               "-Wextra", "-fsyntax-only",
                               f"-I{ROOT / 'core' / 'include'}", str(path)]
                    try:
                        result = subprocess.run(command, capture_output=True,
                                                text=True, check=False)
                    except FileNotFoundError:
                        self.skipTest("gcc not available")
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_score_file(self):
        with self.assertRaises(FileNotFoundError):
            process_music(type("Asset", (), {
                "name": "missing", "file": Path("/no/such/score.tick")})())


class PipelineMusicTests(unittest.TestCase):
    def test_generate_emits_music_for_each_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "assets" / "theme.tick").write_text(SAMPLE, encoding="utf-8")
            (root / "project.toml").write_text(PROJECT_TOML, encoding="utf-8")
            project = load_project(root)
            self.assertEqual([asset.name for asset in project.music], ["theme"])

            pc = generate(root, "pc", project)
            pc_source = (root / "generated" / "pc" / "theme.c").read_text()
            self.assertIn("const gr_song theme", pc_source)
            self.assertIn("NULL", pc_source)
            pc_entry = next(a for a in pc["assets"] if a["kind"] == "music")
            self.assertEqual(pc_entry["psg_bytes"], 0)

            sms = generate(root, "sms", project)
            sms_source = (root / "generated" / "sms" / "theme.c").read_text()
            self.assertIn("theme_psg", sms_source)
            sms_entry = next(a for a in sms["assets"] if a["kind"] == "music")
            self.assertGreater(sms_entry["psg_bytes"], 0)
            self.assertEqual(sms_entry["notes"], 3)
            self.assertIn("'theme.c'",
                          (root / "generated" / "sms" / "meson.build").read_text())

            gb = generate(root, "gb", project)
            gb_source = (root / "generated" / "gb" / "theme.c").read_text()
            self.assertTrue(gb_source.startswith("#pragma bank 1"))

    def test_per_target_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "assets").mkdir()
            (root / "assets" / "theme.tick").write_text(SAMPLE, encoding="utf-8")
            (root / "project.toml").write_text(PROJECT_TOML, encoding="utf-8")
            project = load_project(root)
            project.targets["pc"] = {"music": {"theme": {"skip": True}}}
            manifest = generate(root, "pc", project)
            self.assertFalse((root / "generated" / "pc" / "theme.c").exists())
            self.assertFalse(any(a["kind"] == "music" for a in manifest["assets"]))


if __name__ == "__main__":
    unittest.main()
