"""Unit tests for Tiled .tmx map import and pipeline integration."""

from __future__ import annotations

import base64
import gzip
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
import sys  # noqa: E402
sys.path.insert(0, str(ROOT / "pipeline"))

from gramma_pipeline import check_budget, generate, load_project  # noqa: E402
from gramma_pipeline.images import emit_image  # noqa: E402
from gramma_pipeline.project import MapAsset  # noqa: E402
from gramma_pipeline.tiled import (  # noqa: E402
    TiledError, parse_tmx, process_map)


DEFAULT_TILESET = """ <tileset firstgid="10" name="tiles" tilewidth="8" tileheight="8" tilecount="3" columns="1">
  <image source="sheet.png" width="8" height="24"/>
 </tileset>"""


def _write_sheet(root: Path) -> Path:
    """Three tiles: transparent, red, blue (in that GID order)."""
    path = root / "assets" / "sheet.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet = Image.new("RGBA", (8, 24), (0, 0, 0, 0))
    sheet.paste(Image.new("RGBA", (8, 8), (220, 40, 40, 255)), (0, 8))
    sheet.paste(Image.new("RGBA", (8, 8), (40, 80, 220, 255)), (0, 16))
    sheet.save(path)
    return path


def _tile_data(gids: list[int], encoding: str,
               compression: str | None = None) -> str:
    compressed = f' compression="{compression}"' if compression else ""
    if encoding == "csv":
        payload = ", ".join(str(gid) for gid in gids)
    elif encoding == "xml":
        payload = "\n".join(f'   <tile gid="{gid}"/>' for gid in gids)
    elif encoding == "base64":
        raw = struct.pack(f"<{len(gids)}I", *gids)
        if compression == "zlib":
            raw = zlib.compress(raw)
        elif compression == "gzip":
            raw = gzip.compress(raw)
        payload = base64.b64encode(raw).decode("ascii")
    else:
        raise AssertionError(encoding)
    return f'  <data encoding="{encoding}"{compressed}>{payload}</data>'


def _layer(gids: list[int], name: str = "ground", encoding: str = "csv",
           compression: str | None = None, width: int = 2,
           height: int = 2) -> str:
    return (f' <layer id="1" name="{name}" width="{width}" '
            f'height="{height}">\n'
            + _tile_data(gids, encoding, compression) + "\n </layer>")


def _map_xml(layers: list[str], tileset: str = DEFAULT_TILESET,
             width: int = 2, height: int = 2, tilewidth: int = 8,
             tileheight: int = 8, infinite: int = 0, extra: str = "") -> str:
    body = "\n".join([tileset] + layers + ([extra] if extra else []))
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<map version="1.10" orientation="orthogonal" width="{width}" '
            f'height="{height}" tilewidth="{tilewidth}" '
            f'tileheight="{tileheight}" infinite="{infinite}">\n'
            f'{body}\n</map>\n')


def _write_map(root: Path, gids: list[int], **kwargs) -> Path:
    _write_sheet(root)
    path = root / "assets" / "level.tmx"
    path.write_text(_map_xml([_layer(gids, **kwargs.pop("layer_kwargs", {}))],
                             **kwargs), encoding="utf-8")
    return path


class TiledParserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.gids = [0, 11, 12, 11]  # empty, red, blue, red

    def tearDown(self):
        self.temp.cleanup()

    def test_csv_base64_raw_zlib_and_gzip_are_equivalent(self):
        cases = [
            ("csv", None),
            ("base64", None),
            ("base64", "zlib"),
            ("base64", "gzip"),
            ("xml", None),
        ]
        for encoding, compression in cases:
            with self.subTest(encoding=encoding, compression=compression):
                path = _write_map(
                    self.root, self.gids,
                    layer_kwargs={"encoding": encoding,
                                  "compression": compression})
                parsed = parse_tmx(path)
                self.assertEqual(parsed.layer.name, "ground")
                self.assertEqual(parsed.layer.gids, self.gids)
                self.assertEqual((parsed.width, parsed.height), (2, 2))
                self.assertEqual(parsed.firstgid, 10)
                self.assertEqual(parsed.tileset_image.name, "sheet.png")

    def test_external_tsx_resolves_image_relative_to_tsx(self):
        _write_sheet(self.root)
        tiles_dir = self.root / "assets" / "tiles"
        tiles_dir.mkdir(parents=True, exist_ok=True)
        (tiles_dir / "sheet.png").write_bytes(
            (self.root / "assets" / "sheet.png").read_bytes())
        (tiles_dir / "tiles.tsx").write_text(
            '<tileset name="tiles" tilewidth="8" tileheight="8" '
            'tilecount="3" columns="1">\n'
            ' <image source="sheet.png" width="8" height="24"/>\n'
            '</tileset>\n', encoding="utf-8")
        path = self.root / "assets" / "level.tmx"
        path.write_text(_map_xml(
            [_layer(self.gids)],
            tileset=' <tileset firstgid="10" source="tiles/tiles.tsx"/>'),
            encoding="utf-8")
        parsed = parse_tmx(path)
        self.assertEqual(parsed.tileset_image, (tiles_dir / "sheet.png"))
        self.assertEqual(parsed.layer.gids, self.gids)

    def test_layer_selection_by_name(self):
        _write_sheet(self.root)
        path = self.root / "assets" / "level.tmx"
        path.write_text(_map_xml([
            _layer([0, 11, 12, 11], "ground"),
            _layer([12, 12, 0, 0], "detail"),
        ]), encoding="utf-8")
        self.assertEqual(parse_tmx(path).layer.gids, self.gids)
        selected = parse_tmx(path, "detail")
        self.assertEqual(selected.layer.name, "detail")
        self.assertEqual(selected.layer.gids, [12, 12, 0, 0])
        with self.assertRaisesRegex(TiledError, "no tile layer named 'missing'"):
            parse_tmx(path, "missing")

    def test_rejects_unsupported_maps(self):
        _write_sheet(self.root)
        path = self.root / "assets" / "level.tmx"
        cases = [
            (_map_xml([_layer(self.gids)], infinite=1), "infinite"),
            (_map_xml([_layer(self.gids)], tilewidth=16), "tilewidth must be 8"),
            (_map_xml([_layer(self.gids)], tileheight=16),
             "tileheight must be 8"),
            (_map_xml([_layer(self.gids)], tileset=DEFAULT_TILESET + "\n"
                      + DEFAULT_TILESET), "exactly one tileset"),
            (_map_xml([_layer(self.gids)], extra=' <objectgroup name="obj"/>'),
             "objectgroup layers are not supported"),
            (_map_xml([_layer(self.gids)], extra=' <imagelayer name="img"/>'),
             "imagelayer layers are not supported"),
            (_map_xml([_layer(self.gids, width=3)]), "layer is 3x2"),
            (_map_xml([_layer([0, 11, 13, 11])]), "GID 13"),
            (_map_xml([_layer([0, 0x8000000b, 12, 11])]), "flipped"),
            (_map_xml([_layer(self.gids)], tileset=(
                ' <tileset firstgid="10" name="tiles" tilewidth="8" '
                'tileheight="8">\n'
                '  <image source="sheet.png" width="8" height="24"/>\n'
                '  <tile id="0"><animation><frame tileid="1" duration="100"/>'
                '</animation></tile>\n </tileset>')), "animations"),
        ]
        for text, fragment in cases:
            with self.subTest(fragment=fragment):
                path.write_text(text, encoding="utf-8")
                with self.assertRaisesRegex(TiledError, fragment):
                    parse_tmx(path)

    def test_rejects_invalid_xml_and_missing_files(self):
        path = self.root / "assets" / "level.tmx"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<map><layer></map>", encoding="utf-8")
        with self.assertRaisesRegex(TiledError, "invalid XML"):
            parse_tmx(path)
        path.write_text('<map width="2" height="2" tilewidth="8" '
                        'tileheight="8"/>', encoding="utf-8")
        with self.assertRaisesRegex(TiledError, "expected exactly one tileset"):
            parse_tmx(path)
        with self.assertRaises(FileNotFoundError):
            parse_tmx(self.root / "assets" / "missing.tmx")


class MapConversionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_gid_remap_and_empty_tile(self):
        path = _write_map(self.root, [0, 11, 12, 11])
        asset = MapAsset("level", path, bpp=4)
        result = process_map(asset, "chunky")
        self.assertEqual(result.kind, "background")
        self.assertEqual(result.layer, "ground")
        self.assertEqual(result.firstgid, 10)
        self.assertEqual((result.width, result.height), (16, 16))
        self.assertEqual(result.tile_indices, [0, 1, 2, 1])
        self.assertEqual(result.unique_tiles, 3)
        self.assertEqual(result.palette[0], (0, 0, 0))
        self.assertEqual(result.rom_bytes, 3 * 8 * 4 + 3 * 2 + 2 * 4)

    def test_generated_c_is_c89_clean(self):
        path = _write_map(self.root, [0, 11, 12, 11])
        result = process_map(MapAsset("level", path, bpp=4), "chunky")
        source = emit_image(result)
        self.assertIn("const gr_tileset level_tileset", source)
        self.assertIn("const gr_map level_map = { 2, 2, level_map_data }",
                      source)
        directory = self.root / "generated"
        directory.mkdir()
        source_file = directory / "level.c"
        source_file.write_text(source, encoding="utf-8")
        try:
            completed = subprocess.run(
                ["gcc", "-std=c89", "-pedantic", "-Wall", "-Wextra",
                 "-fsyntax-only", f"-I{ROOT / 'core' / 'include'}",
                 str(source_file)], capture_output=True, text=True,
                check=False)
        except FileNotFoundError:
            self.skipTest("gcc not available")
        self.assertEqual(completed.returncode, 0, completed.stderr)


PROJECT_TOML = """
[project]
name = "map-test"
max_sprites = 1

[[map]]
name = "level"
file = "assets/level.tmx"
layer = "ground"
bpp = 4

[target.gb.map.level]
bpp = 2

[target.nes.map.level]
bpp = 2
"""


class PipelineMapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        _write_sheet(self.root)
        (self.root / "assets" / "level.tmx").write_text(_map_xml([
            _layer([0, 11, 12, 11], "ground"),
            _layer([12, 12, 0, 0], "detail"),
        ]), encoding="utf-8")
        (self.root / "project.toml").write_text(PROJECT_TOML, encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_generate_emits_map_for_each_target(self):
        project = load_project(self.root)
        self.assertEqual([asset.name for asset in project.maps], ["level"])

        for target in ("pc", "gb", "nes", "sms"):
            with self.subTest(target=target):
                manifest = generate(self.root, target, project)
                entry = next(a for a in manifest["assets"]
                             if a["kind"] == "map")
                self.assertEqual(entry["name"], "level")
                self.assertEqual(entry["layer"], "ground")
                self.assertEqual(entry["firstgid"], 10)
                self.assertEqual(entry["map_width"], 2)
                self.assertEqual(entry["map_height"], 2)
                self.assertEqual(entry["tile_count"], 4)
                self.assertEqual(entry["unique_tiles"], 3)
                self.assertEqual(check_budget(project, target, manifest), [])

                source = (self.root / "generated" / target /
                          "level.c").read_text()
                self.assertIn("const gr_tileset level_tileset", source)
                self.assertIn("const gr_map level_map", source)
                self.assertIn("'level.c'",
                              (self.root / "generated" / target /
                               "meson.build").read_text())
                if target == "gb":
                    self.assertTrue(source.startswith("#pragma bank 1"))
                if target == "nes":
                    self.assertIn("extern const uint8_t nes_chr_data[];",
                                  source)
                    self.assertTrue((self.root / "generated" / "nes" /
                                     "chr.s").is_file())

    def test_target_overrides_control_layer_skip_and_bpp(self):
        project = load_project(self.root)
        project.targets["pc"] = {"map": {"level": {"layer": "detail"}}}
        manifest = generate(self.root, "pc", project)
        entry = next(a for a in manifest["assets"] if a["kind"] == "map")
        self.assertEqual(entry["layer"], "detail")
        self.assertEqual(entry["bpp"], 4)

        project.targets["pc"] = {"map": {"level": {"skip": True}}}
        manifest = generate(self.root, "pc", project)
        self.assertFalse((self.root / "generated" / "pc" / "level.c").exists())
        self.assertFalse(any(a["kind"] == "map" for a in manifest["assets"]))

    def test_manifest_map_counts_toward_nametable_limit(self):
        project = load_project(self.root)
        manifest = generate(self.root, "nes", project)
        entry = next(a for a in manifest["assets"] if a["kind"] == "map")
        entry["tile_count"] = 961
        errors = check_budget(project, "nes", manifest)
        self.assertTrue(any("level: map uses 961 tiles" in error
                            for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
