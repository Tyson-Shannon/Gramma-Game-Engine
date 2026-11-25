"""Tiled .tmx tile layers -> packed tiles, palette and a gr_map.

v1 covers the common orthogonal, 8x8, image-based tileset case: CSV, XML and
base64 (raw/zlib/gzip) tile layers, inline or external .tsx tilesets. Flipped
tiles, object layers, tile animations and multiple tilesets are rejected with a
build error rather than silently rendered incorrectly.
"""

from __future__ import annotations

import base64
import gzip
import struct
import xml.etree.ElementTree as ET
import zlib
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from .images import ImageAsset, ImageResult, process_image
from .project import MapAsset


FLIP_MASK = 0xf0000000  # Tiled's horizontal/vertical/rotate flags in the GID


class TiledError(ValueError):
    """A .tmx/.tsx file could not be converted."""


@dataclass
class TiledLayer:
    name: str
    width: int
    height: int
    gids: list[int]


@dataclass
class TiledMap:
    file: Path
    width: int
    height: int
    firstgid: int
    tileset_image: Path
    layer: TiledLayer


@dataclass
class MapResult(ImageResult):
    layer: str
    firstgid: int


def _integer(value, label: str, filename: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise TiledError(f"{filename}: {label} must be an integer, got {value!r}")


def _decode_data(element: ET.Element, width: int, height: int,
                 filename: str) -> list[int]:
    encoding = (element.get("encoding") or "xml").lower()
    compression = (element.get("compression") or "").lower()
    expected = width * height

    if encoding == "csv":
        if compression:
            raise TiledError(f"{filename}: compressed CSV is not supported")
        text = (element.text or "").strip()
        gids = [_integer(part, "tile GID", filename)
                for part in text.split(",") if part.strip()]
    elif encoding == "xml":
        if compression:
            raise TiledError(f"{filename}: compressed XML tiles are not supported")
        gids = [_integer(tile.get("gid", 0), "tile GID", filename)
                for tile in element.findall("tile")]
    elif encoding == "base64":
        try:
            raw = base64.b64decode((element.text or "").strip(), validate=True)
        except (ValueError, TypeError):
            raise TiledError(f"{filename}: invalid base64 tile data")
        if compression == "zlib":
            try:
                raw = zlib.decompress(raw)
            except zlib.error as error:
                raise TiledError(f"{filename}: invalid zlib tile data: {error}")
        elif compression == "gzip":
            try:
                raw = gzip.decompress(raw)
            except (OSError, EOFError) as error:
                raise TiledError(f"{filename}: invalid gzip tile data: {error}")
        elif compression:
            raise TiledError(
                f"{filename}: unsupported tile compression {compression!r}")
        if len(raw) % 4:
            raise TiledError(f"{filename}: base64 tile data is not aligned")
        gids = list(struct.unpack(f"<{len(raw) // 4}I", raw))
    else:
        raise TiledError(f"{filename}: unsupported tile encoding {encoding!r}")

    if len(gids) != expected:
        raise TiledError(
            f"{filename}: layer has {len(gids)} tiles, expected "
            f"{expected} ({width}x{height})")
    return gids


def _check_tileset_features(tileset: ET.Element, filename: str) -> None:
    """Reject tileset features that have no portable Gramma representation."""

    for attribute in ("tilewidth", "tileheight"):
        if attribute in tileset.attrib:
            size = _integer(tileset.get(attribute), attribute, filename)
            if size != 8:
                raise TiledError(
                    f"{filename}: tileset {attribute} must be 8, got {size}")
    for tile in tileset.findall("tile"):
        if tile.find("animation") is not None:
            raise TiledError(f"{filename}: tile animations are not supported")


def _tileset_image(tileset: ET.Element, map_path: Path,
                   filename: str) -> Path:
    image = tileset.find("image")
    directory = map_path.parent
    source = tileset.get("source")
    if source is not None:
        # External tileset: image paths are relative to the .tsx file.
        tsx_path = (map_path.parent / source).resolve()
        if not tsx_path.is_file():
            raise TiledError(f"{filename}: missing external tileset {source!r}")
        try:
            external = ET.parse(tsx_path).getroot()
        except ET.ParseError as error:
            raise TiledError(f"{tsx_path.name}: invalid XML: {error}")
        if external.tag != "tileset":
            raise TiledError(f"{tsx_path.name}: expected a <tileset> root")
        _check_tileset_features(external, tsx_path.name)
        image = external.find("image")
        directory = tsx_path.parent
    if image is None or not image.get("source"):
        raise TiledError(
            f"{filename}: tileset needs an <image source=\"...\"> "
            "(only image-based tilesets are supported)")
    image_path = (directory / image.get("source")).resolve()
    if not image_path.is_file():
        raise TiledError(f"{filename}: missing tileset image {image.get('source')!r}")
    return image_path


def _tileset_tile_count(image_path: Path, filename: str) -> int:
    try:
        with Image.open(image_path) as image:
            width, height = image.size
    except OSError as error:
        raise TiledError(f"{filename}: cannot read tileset image: {error}")
    if width % 8 or height % 8:
        raise TiledError(
            f"{filename}: tileset image is {width}x{height}, not a multiple "
            "of 8 pixels")
    return (width // 8) * (height // 8)


def parse_tmx(path: Path, layer_name: str | None = None) -> TiledMap:
    """Parse one orthogonal tile layer and its image tileset from a .tmx file."""

    path = Path(path)
    filename = path.name
    if not path.is_file():
        raise FileNotFoundError(f"missing Tiled map: {path}")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as error:
        raise TiledError(f"{filename}: invalid XML: {error}")
    if root.tag != "map":
        raise TiledError(f"{filename}: expected a <map> root")

    orientation = root.get("orientation", "orthogonal").lower()
    if orientation != "orthogonal":
        raise TiledError(f"{filename}: only orthogonal maps are supported")
    if root.get("infinite", "0") not in ("0", "false", "False"):
        raise TiledError(f"{filename}: infinite maps are not supported")
    width = _integer(root.get("width"), "map width", filename)
    height = _integer(root.get("height"), "map height", filename)
    if width <= 0 or height <= 0 or width > 65535 or height > 65535:
        raise TiledError(f"{filename}: invalid map size {width}x{height}")
    for attribute in ("tilewidth", "tileheight"):
        tile_size = _integer(root.get(attribute, 8), attribute, filename)
        if tile_size != 8:
            raise TiledError(f"{filename}: {attribute} must be 8, got {tile_size}")

    tilesets = root.findall("tileset")
    if len(tilesets) != 1:
        raise TiledError(
            f"{filename}: expected exactly one tileset, found {len(tilesets)}")
    tileset = tilesets[0]
    _check_tileset_features(tileset, filename)
    firstgid = _integer(tileset.get("firstgid", 1), "firstgid", filename)
    if firstgid < 1:
        raise TiledError(f"{filename}: firstgid must be at least 1")
    tileset_image = _tileset_image(tileset, path, filename)

    for tag in ("objectgroup", "imagelayer", "group"):
        if root.findall(tag):
            raise TiledError(f"{filename}: {tag} layers are not supported")
    layers = root.findall("layer")
    if layer_name is not None:
        layers = [layer for layer in layers if layer.get("name") == layer_name]
        if not layers:
            raise TiledError(f"{filename}: no tile layer named {layer_name!r}")
    if not layers:
        raise TiledError(f"{filename}: map has no tile layer")
    layer = layers[0]
    layer_width = _integer(layer.get("width", width), "layer width", filename)
    layer_height = _integer(layer.get("height", height), "layer height", filename)
    if (layer_width, layer_height) != (width, height):
        raise TiledError(
            f"{filename}: layer is {layer_width}x{layer_height}, "
            f"map is {width}x{height}")
    data = layer.find("data")
    if data is None:
        raise TiledError(f"{filename}: layer has no <data>")
    gids = _decode_data(data, width, height, filename)
    if any(gid & FLIP_MASK for gid in gids):
        raise TiledError(f"{filename}: flipped/rotated tiles are not supported")
    tile_count = _tileset_tile_count(tileset_image, filename)
    for gid in gids:
        if gid and not (firstgid <= gid < firstgid + tile_count):
            raise TiledError(
                f"{filename}: GID {gid} is outside the tileset "
                f"(firstgid {firstgid}, {tile_count} tiles)")

    return TiledMap(
        file=path, width=width, height=height, firstgid=firstgid,
        tileset_image=tileset_image,
        layer=TiledLayer(layer.get("name", ""), width, height, gids),
    )


def process_map(asset: MapAsset, packing: str = "chunky",
                bpp: int | None = None, layer: str | None = None) -> MapResult:
    """Convert a TMX tile layer into the same shape as a PNG background."""

    tiled = parse_tmx(asset.file, layer or asset.layer)
    sheet = ImageAsset(
        name=asset.name, file=tiled.tileset_image, kind="background",
        bpp=asset.bpp if bpp is None else bpp,
    )
    result = process_image(sheet, packing)
    sheet_tiles = result.tile_indices

    indices: list[int] = []
    for gid in tiled.layer.gids:
        if gid == 0:
            indices.append(0)  # Tiled's empty tile is Gramma's transparent tile
            continue
        sheet_index = gid - tiled.firstgid
        if sheet_index < 0 or sheet_index >= len(sheet_tiles):
            raise TiledError(
                f"{asset.file.name}: GID {gid} is outside the tileset "
                f"(firstgid {tiled.firstgid}, {len(sheet_tiles)} tiles)")
        indices.append(sheet_tiles[sheet_index])

    return MapResult(
        name=result.name, kind="background", bpp=result.bpp,
        width=tiled.width * 8, height=tiled.height * 8,
        palette=result.palette, tiles=result.tiles, tile_indices=indices,
        packing=result.packing, source=asset.file.name,
        rom_bytes=result.rom_bytes + 2 * len(indices),
        layer=tiled.layer.name, firstgid=tiled.firstgid,
    )
