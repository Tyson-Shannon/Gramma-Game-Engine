"""Unit tests for target tile packing, palette creation and budget checks."""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "tools" / "gr"))

from gramma_pipeline import check_budget, generate, load_project  # noqa: E402
from gramma_pipeline.budget import gb_mapper_config, sms_mapper_config  # noqa: E402
from gramma_pipeline.generate import _emit_nes_chr  # noqa: E402
from gramma_pipeline.images import pack_tile, process_image  # noqa: E402
from gramma_pipeline.project import ImageAsset  # noqa: E402


class TilePackingTests(unittest.TestCase):
    def test_chunky_4bpp(self):
        indices = list(range(8)) * 8
        tile = pack_tile(indices, 4, "chunky")
        self.assertEqual(tile[0], 0x01)
        self.assertEqual(tile[1], 0x23)

    def test_planar_2bpp(self):
        indices = [0, 1, 2, 3, 0, 1, 2, 3] * 8
        tile = pack_tile(indices, 2, "planar")
        self.assertEqual(len(tile), 16)
        self.assertEqual(tile[0], 0b01010101)
        self.assertEqual(tile[8], 0b00110011)

    def test_planar_1bpp(self):
        tile = pack_tile([1, 0, 1, 0, 1, 0, 1, 0] * 8, 1, "planar")
        self.assertEqual(len(tile), 8)
        self.assertEqual(tile[0], 0b10101010)


class ImagePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_transparent_index_and_dedup(self):
        image = Image.new("RGBA", (16, 8), (0, 0, 0, 0))
        image.save(self.root / "sheet.png")
        asset = ImageAsset("sheet", self.root / "sheet.png",
                           kind="sprite", bpp=2)
        result = process_image(asset, "planar")
        self.assertEqual(result.unique_tiles, 1)
        self.assertEqual(result.palette[0], (0, 0, 0))
        self.assertEqual(all(tile == bytes(16) for tile in result.tiles), True)


class CHRPlacementTests(unittest.TestCase):
    def test_assets_can_share_a_tile_index_in_different_banks(self):
        class Result:
            def __init__(self, kind):
                self.kind = kind
                self.tiles = [bytes([i]) * 16 for i in range(2)]

        images = [("bg", Result("background")), ("alt", Result("sprite"))]
        placements = {
            "bg": ImageAsset("bg", Path("bg.png"), kind="background"),
            "alt": ImageAsset("alt", Path("alt.png"), chr_bank=1, chr_tile=4),
        }
        source, _, offsets = _emit_nes_chr(images, placements, 2)
        self.assertEqual(offsets, {"bg": (0, 0), "alt": (1, 4)})
        self.assertIn(".export _nes_chr_data", source)
        self.assertIn('.segment "CHARS"', source)
        self.assertEqual(source.count("    .byte "), 1024)

    def test_overlapping_tiles_are_rejected(self):
        class Result:
            kind = "sprite"
            tiles = [bytes(16)]

        placements = {
            "a": ImageAsset("a", Path("a.png"), chr_tile=4),
            "b": ImageAsset("b", Path("b.png"), chr_tile=4),
        }
        with self.assertRaisesRegex(ValueError, "overlaps"):
            _emit_nes_chr([("a", Result()), ("b", Result())], placements, 1)


class MapperConfigTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "examples" / "test-kart"
        self.project = load_project(self.root)
        self.manifest = generate(self.root, "nes")

    def errors(self):
        return check_budget(self.project, "nes", self.manifest)

    def test_example_two_bank_config_is_valid(self):
        self.assertEqual(self.project.mapper["nes"]["id"], "mmc3")
        self.assertEqual(self.project.mapper["nes"]["chr_banks"], 2)
        self.assertEqual(self.errors(), [])

    def test_larger_prg_layout_is_valid_on_mmc3(self):
        self.project.mapper["nes"] = {
            "id": "mmc3", "prg_banks": 4, "chr_banks": 2}
        self.assertEqual(self.errors(), [])

    def test_nrom_rejects_larger_prg_layout(self):
        self.project.mapper["nes"] = {"id": "nrom", "prg_banks": 4}
        self.assertTrue(any("nrom supports only two" in e
                            for e in self.errors()))

    def test_bank_counts_must_be_powers_of_two(self):
        self.project.mapper["nes"] = {"id": "mmc1", "prg_banks": 3}
        self.assertTrue(any("power of two" in e for e in self.errors()))
        self.project.mapper["nes"] = {"id": "mmc1", "chr_banks": 3}
        self.assertTrue(any("chr_banks must be a power of two" in e
                            for e in self.errors()))

    def test_nrom_rejects_multiple_chr_banks(self):
        self.project.mapper["nes"] = {"id": "nrom", "chr_banks": 2}
        self.assertTrue(any("nrom supports only one" in e
                            for e in self.errors()))

    def test_mmc1_larger_chr_layout_is_valid(self):
        self.project.mapper["nes"] = {
            "id": "mmc1", "prg_banks": 2, "chr_banks": 2}
        self.assertEqual(self.errors(), [])

    def test_mmc3_larger_chr_layout_is_valid(self):
        self.project.mapper["nes"] = {
            "id": "mmc3", "prg_banks": 2, "chr_banks": 4}
        self.assertEqual(self.errors(), [])

    def test_chr_placement_is_validated(self):
        self.project.mapper["nes"] = {"id": "mmc3", "chr_banks": 1}
        self.manifest["assets"][0]["chr_bank"] = 1
        self.assertTrue(any("chr_bank 1 is outside" in e
                            for e in self.errors()))
        self.manifest["assets"][0]["chr_bank"] = 0
        self.manifest["assets"][0]["chr_tile"] = -1
        self.assertTrue(any("chr_tile -1 must not be negative" in e
                            for e in self.errors()))

    def test_unknown_mapper_is_rejected(self):
        self.project.mapper["nes"] = {"id": "mmc2"}
        self.assertTrue(any("unknown NES mapper" in e
                            for e in self.errors()))

    def test_load_project_reads_mapper_section(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project.toml").write_text(
                '[project]\nname = "x"\n\n[mapper.nes]\n'
                'id = "mmc3"\nprg_banks = 4\nchr_banks = 2\n')
            project = load_project(root)
            self.assertEqual(project.mapper["nes"]["id"], "mmc3")
            self.assertEqual(project.mapper["nes"]["prg_banks"], 4)

    def test_load_project_reads_chr_placement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "project.toml").write_text(
                '[project]\nname = "x"\n\n[[image]]\n'
                'name = "alt"\nfile = "alt.png"\n'
                'chr_bank = 2\nchr_tile = 8\n')
            project = load_project(root)
            self.assertEqual(project.images[0].chr_bank, 2)
            self.assertEqual(project.images[0].chr_tile, 8)


class GBMapperConfigTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "examples" / "test-kart"
        self.project = load_project(self.root)

    def errors(self):
        manifest = generate(self.root, "gb", self.project)
        return check_budget(self.project, "gb", manifest)

    def test_example_mbc1_layout_is_valid(self):
        cfg = gb_mapper_config(self.project)
        self.assertEqual(cfg["id"], "mbc1")
        self.assertEqual(cfg["rom_banks"], 4)
        self.assertEqual(cfg["cart_type"], 0x01)
        self.assertEqual(self.errors(), [])

    def test_sram_changes_cart_type(self):
        self.project.mapper["gb"]["ram_banks"] = 2
        cfg = gb_mapper_config(self.project)
        self.assertEqual(cfg["cart_type"], 0x02)
        self.assertEqual(self.errors(), [])

    def test_mbc1_bank_limits_are_enforced(self):
        self.project.mapper["gb"]["rom_banks"] = 3
        self.assertTrue(any("power of two" in e for e in self.errors()))
        self.project.mapper["gb"]["rom_banks"] = 64
        self.assertTrue(any("mbc1 maximum" in e for e in self.errors()))
        self.project.mapper["gb"]["rom_banks"] = 4
        self.project.mapper["gb"]["ram_banks"] = 8
        self.assertTrue(any("mbc1 supports at most 4" in e
                            for e in self.errors()))

    def test_plain_rom_rejects_banking(self):
        self.project.mapper["gb"] = {"id": "none", "rom_banks": 4}
        self.assertTrue(any("plain ROM supports only 2" in e
                            for e in self.errors()))

    def test_unknown_mapper_is_rejected(self):
        self.project.mapper["gb"] = {"id": "mbc9"}
        self.assertTrue(any("unknown Game Boy mapper" in e
                            for e in self.errors()))


class SMSMapperConfigTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / "examples" / "test-kart"
        self.project = load_project(self.root)

    def errors(self):
        manifest = generate(self.root, "sms", self.project)
        return check_budget(self.project, "sms", manifest)

    def test_example_four_bank_layout_is_valid(self):
        cfg = sms_mapper_config(self.project)
        self.assertEqual(cfg["rom_banks"], 4)
        self.assertEqual(cfg["size_code"], 0xe)
        self.assertEqual(self.errors(), [])

    def test_size_codes_follow_sms_header_spec(self):
        expected = {2: 0xc, 4: 0xe, 8: 0xf, 16: 0x0, 32: 0x1, 64: 0x2}
        for banks, code in expected.items():
            self.project.mapper["sms"]["rom_banks"] = banks
            self.project.budgets["sms"]["rom_kb"] = banks * 16
            self.assertEqual(sms_mapper_config(self.project)["size_code"], code)
            self.assertEqual(self.errors(), [])

    def test_invalid_bank_counts_are_rejected(self):
        for banks, fragment in ((3, "power of two"), (1, "at least 2"),
                                (128, "maximum")):
            self.project.mapper["sms"]["rom_banks"] = banks
            self.assertTrue(any(fragment in e for e in self.errors()),
                            f"expected {fragment} for {banks} banks")

    def test_bank_layout_must_fit_budget(self):
        self.project.mapper["sms"]["rom_banks"] = 8
        self.assertTrue(any("need 128 KB" in e for e in self.errors()))

    def test_generated_sms_art_is_4bpp_planar(self):
        manifest = generate(self.root, "sms")
        self.assertEqual({a["bpp"] for a in manifest["assets"]}, {4, 0})
        self.assertTrue(all(a["packing"] == "planar"
                            for a in manifest["assets"]
                            if a["kind"] not in ("audio", "music")))
        self.assertEqual(check_budget(load_project(self.root), "sms",
                                      manifest), [])


class ProjectTests(unittest.TestCase):
    def test_example_generates_for_pc_and_gb(self):
        project_root = ROOT / "examples" / "test-kart"
        for target in ("pc", "gb"):
            manifest = generate(project_root, target)
            self.assertEqual(len(manifest["assets"]), 5)  # art + audio + music
            self.assertTrue((project_root / "generated" / target /
                             "meson.build").is_file())
            self.assertEqual(check_budget(load_project(project_root), target,
                                          manifest), [])

    def test_budget_rejects_unsupported_bpp(self):
        project_root = ROOT / "examples" / "test-kart"
        manifest = generate(project_root, "pc")
        errors = check_budget(load_project(project_root), "gb", manifest)
        self.assertTrue(any("4bpp is not supported" in error
                            for error in errors))


if __name__ == "__main__":
    unittest.main()
