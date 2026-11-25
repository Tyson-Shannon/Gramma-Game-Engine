"""Locate or download GBDK-2020 (no sudo, cached under ~/.cache/gramma)."""

from __future__ import annotations

import io
import os
import shutil
import tarfile
import urllib.request
from pathlib import Path

RELEASE_URL = ("https://github.com/gbdk-2020/gbdk-2020/releases/download/"
               "4.6.0/gbdk-linux64.tar.gz")
CACHE_DIR = Path.home() / ".cache" / "gramma" / "tools" / "gbdk"


def find_gbdk() -> Path | None:
    candidates = []
    if os.environ.get("GBDK_HOME"):
        candidates.append(Path(os.environ["GBDK_HOME"]))
    candidates.append(CACHE_DIR)
    for candidate in candidates:
        if (candidate / "bin" / "lcc").is_file():
            return candidate
    return None


def ensure_gbdk() -> tuple[Path | None, str | None]:
    """Return (gbdk_root, status_message). Downloads on first use."""
    found = find_gbdk()
    if found is not None:
        return found, f"GBDK-2020 found at {found}"
    CACHE_DIR.parent.mkdir(parents=True, exist_ok=True)
    print("GBDK-2020 not found; downloading compiler (~8 MB) ...")
    try:
        with urllib.request.urlopen(RELEASE_URL, timeout=180) as response:
            archive = response.read()
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            tar.extractall(CACHE_DIR.parent, filter="data")
    except (OSError, tarfile.TarError) as error:
        return None, None
    return find_gbdk(), f"GBDK-2020 installed at {CACHE_DIR}"


def gbdk_status() -> str:
    found = find_gbdk()
    return f"ok ({found})" if found else "missing (run gr build --target gb)"
