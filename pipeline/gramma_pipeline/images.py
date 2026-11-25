"""PNG -> packed 8x8 tiles, RGB555 palette and (optionally) a tile map."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from PIL import Image

from .project import ImageAsset


@dataclass
class ImageResult:
    name: str
    kind: str
    bpp: int
    width: int
    height: int
    palette: list[tuple[int, int, int]]
    tiles: list[bytes]           # packed, unique tiles
    tile_indices: list[int]      # original tile order (for backgrounds)
    packing: str
    source: str
    rom_bytes: int

    @property
    def unique_tiles(self) -> int:
        return len(self.tiles)


def _ident(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def _build_palette(image: Image.Image, max_colors: int):
    """Reserve index 0 for transparent pixels, then take the commonest colors."""
    get_pixels = getattr(image, "get_flattened_data", image.getdata)
    pixels = list(get_pixels())
    counts = Counter(px[:3] for px in pixels if px[3] >= 128)
    chosen = [color for color, _ in counts.most_common(max_colors - 1)]
    palette = [(0, 0, 0)] + chosen

    index_of = {color: i + 1 for i, color in enumerate(chosen)}

    def nearest(color: tuple[int, int, int]) -> int:
        if color in index_of:
            return index_of[color]
        best, best_distance = 1, 1 << 60
        for i, candidate in enumerate(chosen, start=1):
            distance = sum((a - b) ** 2 for a, b in zip(color, candidate))
            if distance < best_distance:
                best, best_distance = i, distance
        return best if chosen else 0

    return palette, nearest


def _pack_tile_chunky(indices: list[int], bpp: int) -> bytes:
    """MSB-first interleaved rows: 2 pixels/byte at 4bpp, etc. (PC, GBA)."""
    out = bytearray()
    per_byte = 8 // bpp
    for y in range(8):
        for group in range(per_byte):
            byte = 0
            for bit in range(per_byte):
                value = indices[y * 8 + group * per_byte + bit] & ((1 << bpp) - 1)
                byte |= value << (8 - bpp - bit * bpp)
            out.append(byte)
    return bytes(out)


def _pack_tile_planar(indices: list[int], bpp: int) -> bytes:
    """One bit-plane at a time: the GB/NES/SMS CHR layout."""
    out = bytearray()
    for plane in range(bpp):
        for y in range(8):
            byte = 0
            for x in range(8):
                bit = (indices[y * 8 + x] >> plane) & 1
                byte |= bit << (7 - x)
            out.append(byte)
    return bytes(out)


def pack_tile(indices: list[int], bpp: int, packing: str = "chunky") -> bytes:
    if packing == "planar":
        return _pack_tile_planar(indices, bpp)
    return _pack_tile_chunky(indices, bpp)


def process_image(asset: ImageAsset, packing: str = "chunky") -> ImageResult:
    if asset.kind not in ("sprite", "background"):
        raise ValueError(f"{asset.name}: kind must be sprite or background")
    if asset.bpp not in (1, 2, 4, 8):
        raise ValueError(f"{asset.name}: bpp must be 1, 2, 4 or 8")
    if not asset.file.is_file():
        raise FileNotFoundError(f"missing image: {asset.file}")

    image = Image.open(asset.file).convert("RGBA")
    width, height = image.size
    if width % 8 or height % 8:
        raise ValueError(
            f"{asset.name}: {width}x{height} is not a multiple of 8 pixels")

    palette, nearest = _build_palette(image, 1 << asset.bpp)
    data = image.load()
    indices: list[int] = []
    for y in range(height):
        for x in range(width):
            r, g, b, a = data[x, y]
            indices.append(0 if a < 128 else nearest((r, g, b)))

    unique: dict[bytes, int] = {}
    tiles: list[bytes] = []
    tile_indices: list[int] = []
    for ty in range(0, height, 8):
        for tx in range(0, width, 8):
            raw = [indices[(ty + dy) * width + tx + dx]
                   for dy in range(8) for dx in range(8)]
            packed = pack_tile(raw, asset.bpp, packing)
            if packed not in unique:
                unique[packed] = len(tiles)
                tiles.append(packed)
            tile_indices.append(unique[packed])

    rom_bytes = len(tiles) * 8 * asset.bpp + len(palette) * 2
    return ImageResult(
        name=asset.name, kind=asset.kind, bpp=asset.bpp,
        width=width, height=height, palette=palette, tiles=tiles,
        tile_indices=tile_indices, packing=packing,
        source=asset.file.name, rom_bytes=rom_bytes,
    )


def _hex_rows(values: list[int], per_row: int = 16) -> str:
    rows = []
    for start in range(0, len(values), per_row):
        rows.append("    " + ", ".join(f"0x{v:02x}" for v in values[start:start + per_row]))
    return ",\n".join(rows)


def emit_image(result: ImageResult, tile_expr: str | None = None) -> str:
    """Emit one asset.

    *tile_expr* lets a target point the tileset at a shared CHR bank (NES)
    instead of emitting a private RODATA copy of the tile bytes.
    """
    ident = _ident(result.name)
    palette = []
    for r, g, b in result.palette:
        palette.append(f"    GR_RGB({r >> 3}, {g >> 3}, {b >> 3})")
    tile_bytes = [byte for tile in result.tiles for byte in tile]
    lines = [
        "/* Generated by the Gramma asset pipeline. DO NOT EDIT. */",
        "#include <gramma/gramma.h>",
        "",
        f"static const gr_color {ident}_palette[{len(result.palette)}] = {{",
        ",\n".join(palette),
        "};",
        "",
    ]
    if tile_expr is None:
        lines += [
            f"static const uint8_t {ident}_tiles[{len(tile_bytes)}] = {{",
            _hex_rows(tile_bytes),
            "};",
            "",
        ]
        tile_expr = f"{ident}_tiles"
    lines += [
        f"const gr_tileset {ident}_tileset = {{",
        f"    {len(result.tiles)}, {result.bpp}, {tile_expr}, "
        f"{ident}_palette, {len(result.palette)}",
        "};",
    ]

    if result.kind == "background":
        map_w = result.width // 8
        map_h = result.height // 8
        values = [value & 0xffff for value in result.tile_indices]
        rows = []
        for start in range(0, len(values), map_w):
            rows.append("    " + ", ".join(f"{v}" for v in values[start:start + map_w]))
        lines += [
            "",
            f"static const uint16_t {ident}_map_data[{len(values)}] = {{",
            ",\n".join(rows),
            "};",
            "",
            f"const gr_map {ident}_map = {{ {map_w}, {map_h}, {ident}_map_data }};",
        ]
    return "\n".join(lines) + "\n"
