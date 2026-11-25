"""Locate or download cc65 (no sudo, cached under ~/.cache/gramma).

The Debian/Ubuntu package is used because the upstream GitHub release has no
binary assets. It is unpacked with ``dpkg-deb -x`` into the same cache layout
as the other Gramma toolchains.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

CACHE_DIR = Path.home() / ".cache" / "gramma" / "tools" / "cc65"


def _layout(root: Path) -> tuple[Path, Path] | None:
    """Return (bin_dir, share_dir) for a cc65 install root."""
    candidates = [
        (root / "usr" / "bin", root / "usr" / "share" / "cc65"),
        (root / "bin", root / "share" / "cc65"),
        (root, root),
    ]
    for bin_dir, share_dir in candidates:
        if (bin_dir / "cl65").is_file() and (share_dir / "cfg" / "nes.cfg").is_file():
            return bin_dir, share_dir
    return None


def find_cc65() -> tuple[Path, Path] | None:
    candidates: list[Path] = []
    if os.environ.get("CC65_HOME"):
        candidates.append(Path(os.environ["CC65_HOME"]))
    candidates.append(CACHE_DIR)
    system_cl65 = shutil.which("cl65")
    if system_cl65 is not None:
        candidates.append(Path(system_cl65).resolve().parent.parent)
    for candidate in candidates:
        layout = _layout(candidate)
        if layout is not None:
            return layout
    return None


def ensure_cc65() -> tuple[tuple[Path, Path] | None, str | None]:
    """Return ((bin_dir, share_dir), status_message). Downloads on first use."""
    found = find_cc65()
    if found is not None:
        return found, f"cc65 found at {found[1]}"
    if shutil.which("dpkg-deb") is None or shutil.which("apt-get") is None:
        return None, None

    CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
    print("cc65 not found; downloading toolchain (~2 MB) ...")
    try:
        subprocess.run(["apt-get", "download", "cc65"], cwd=CACHE_DIR.parent,
                       stdout=subprocess.DEVNULL, check=True)
        debs = sorted(CACHE_DIR.parent.glob("cc65_*.deb"))
        if not debs:
            return None, None
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["dpkg-deb", "-x", str(debs[-1]), str(CACHE_DIR)],
                       check=True)
    except (OSError, subprocess.CalledProcessError):
        return None, None
    found = find_cc65()
    if found is None:
        return None, None
    return found, f"cc65 installed at {found[1]}"


def cc65_status() -> str:
    found = find_cc65()
    return f"ok ({found[1]})" if found else "missing (run gr build --target nes)"
