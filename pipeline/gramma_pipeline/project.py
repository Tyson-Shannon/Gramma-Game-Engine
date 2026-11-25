"""project.toml loading. Uses tomllib from Python 3.11+."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImageAsset:
    name: str
    file: Path
    kind: str = "sprite"          # "sprite" or "background"
    bpp: int = 4
    frame_width: int = 16         # pixels, sprites only
    frame_height: int = 16
    # NES-only placement inside CHR-ROM. Tile indices are local to one 4 KB
    # pattern table; the second half of each 8 KB bank mirrors the first.
    chr_bank: int = 0
    chr_tile: int | None = None


@dataclass
class AudioAsset:
    name: str
    file: Path
    sample_rate: int = 22050


@dataclass
class MusicAsset:
    name: str
    file: Path


@dataclass
class Project:
    root: Path
    name: str
    default_target: str = "pc"
    max_sprites: int = 0
    images: list[ImageAsset] = field(default_factory=list)
    audio: list[AudioAsset] = field(default_factory=list)
    music: list[MusicAsset] = field(default_factory=list)
    budgets: dict[str, dict] = field(default_factory=dict)
    targets: dict[str, dict] = field(default_factory=dict)
    mapper: dict[str, dict] = field(default_factory=dict)
    grain_sources: list[Path] = field(default_factory=list)


def load_project(root: Path) -> Project:
    path = root / "project.toml"
    if not path.is_file():
        raise FileNotFoundError(f"no project.toml in {root}")
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    meta = data.get("project", {})
    project = Project(
        root=root,
        name=meta.get("name", root.name),
        default_target=meta.get("default_target", "pc"),
        max_sprites=int(meta.get("max_sprites", 0)),
        budgets=data.get("budgets", {}),
        targets=data.get("target", {}),
        mapper=data.get("mapper", {}),
    )
    for item in data.get("image", []):
        tile = item.get("chr_tile")
        project.images.append(ImageAsset(
            name=item["name"],
            file=root / item["file"],
            kind=item.get("kind", "sprite"),
            bpp=int(item.get("bpp", 4)),
            frame_width=int(item.get("frame_width", 16)),
            frame_height=int(item.get("frame_height", 16)),
            chr_bank=int(item.get("chr_bank", 0)),
            chr_tile=None if tile is None else int(tile),
        ))
    for item in data.get("audio", []):
        project.audio.append(AudioAsset(
            name=item["name"],
            file=root / item["file"],
            sample_rate=int(item.get("sample_rate", 22050)),
        ))
    for item in data.get("music", []):
        project.music.append(MusicAsset(
            name=item["name"],
            file=root / item["file"],
        ))
    grain = data.get("grain", {})
    names = grain.get("sources")
    if names is None:
        # Convention: every *.grain under src/ (or at the project root) is a
        # translation unit. Explicit [grain] sources override this.
        candidates = sorted((root / "src").glob("*.grain"))
        candidates += sorted(root.glob("*.grain"))
    else:
        candidates = [root / name for name in names]
    project.grain_sources = candidates
    return project
