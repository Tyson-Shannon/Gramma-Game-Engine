"""Locate or download SDCC + devkitSMS (no sudo, cached under ~/.cache/gramma).

SDCC comes from the Debian/Ubuntu packages because upstream does not publish a
convenient binary tarball. devkitSMS is cloned at a pinned commit so CI and
local builds use the same SMSlib and ``makesms`` behaviour.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

TOOLS_DIR = Path.home() / ".cache" / "gramma" / "tools"
SDCC_DIR = TOOLS_DIR / "sdcc"
DEVKITSMS_DIR = TOOLS_DIR / "devkitsms"
DEVKITSMS_URL = "https://github.com/sverx/devkitSMS.git"
DEVKITSMS_COMMIT = "561bc2cb9829cdf2e31ad8cd43835037c8c44a63"
SDCC_EXPECTED_VERSION = "4.5.0"


def _sdcc_layout(root: Path) -> tuple[Path, Path] | None:
    """Return (bin_dir, share_dir) for an SDCC install root."""
    candidates = [
        (root / "usr" / "bin", root / "usr" / "share" / "sdcc"),
        (root / "bin", root / "share" / "sdcc"),
        (root, root),
    ]
    for bin_dir, share_dir in candidates:
        if ((bin_dir / "sdcc").is_file() and
                (share_dir / "include" / "stdint.h").is_file()):
            return bin_dir, share_dir
    return None


def _sdcc_version(bin_dir: Path) -> str | None:
    """Read the SDCC version, or return None if the executable is unusable."""
    try:
        result = subprocess.run([str(bin_dir / "sdcc"), "--version"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True, timeout=10, check=True)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"\b(\d+\.\d+\.\d+)\b", result.stdout)
    return match.group(1) if match is not None else None


def _sdcc_label(bin_dir: Path, share_dir: Path) -> str:
    version = _sdcc_version(bin_dir)
    label = f"SDCC {version}" if version else "SDCC"
    if version is not None and version != SDCC_EXPECTED_VERSION:
        label += f" (expected {SDCC_EXPECTED_VERSION})"
    return f"{label} at {share_dir}"


def _devkitsms_layout(root: Path) -> tuple[Path, Path, Path] | None:
    """Return (crt0, smslib, peep_file) for a devkitSMS checkout."""
    crt0 = root / "crt0" / "crt0_sms.rel"
    smslib = root / "SMSlib" / "SMSlib.lib"
    gg_lib = root / "SMSlib" / "SMSlib_GG.lib"
    peep = root / "SMSlib" / "src" / "peep-rules.txt"
    makesms = root / "tools" / "makesms" / "Linux" / "makesms"
    if all(path.is_file() for path in (crt0, smslib, gg_lib, peep, makesms)):
        return crt0, smslib, peep
    return None


def find_sms() -> tuple[tuple[Path, Path], tuple[Path, Path, Path]] | None:
    sdcc_candidates: list[Path] = []
    devkitsms_candidates: list[Path] = []

    if os.environ.get("SDCC_HOME"):
        sdcc_candidates.append(Path(os.environ["SDCC_HOME"]))
    if os.environ.get("DEVKITSMS_HOME"):
        devkitsms_candidates.append(Path(os.environ["DEVKITSMS_HOME"]))
    sdcc_candidates.append(SDCC_DIR)
    devkitsms_candidates.append(DEVKITSMS_DIR)

    system_sdcc = shutil.which("sdcc")
    if system_sdcc is not None:
        sdcc_candidates.append(Path(system_sdcc).resolve().parent.parent)

    sdcc_layout = None
    for candidate in sdcc_candidates:
        sdcc_layout = _sdcc_layout(candidate)
        if sdcc_layout is not None:
            break
    if sdcc_layout is None:
        return None

    devkitsms_layout = None
    for candidate in devkitsms_candidates:
        devkitsms_layout = _devkitsms_layout(candidate)
        if devkitsms_layout is not None:
            break
    if devkitsms_layout is None:
        return None
    return sdcc_layout, devkitsms_layout


def _download_sdcc() -> bool:
    if shutil.which("apt-get") is None or shutil.which("dpkg-deb") is None:
        return False
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    print("SDCC not found; downloading toolchain (~4 MB) ...")
    try:
        subprocess.run(["apt-get", "download", "sdcc", "sdcc-libraries"],
                       cwd=TOOLS_DIR, stdout=subprocess.DEVNULL, check=True)
        debs = sorted(TOOLS_DIR.glob("sdcc*.deb"))
        if not debs:
            return False
        SDCC_DIR.mkdir(parents=True, exist_ok=True)
        for deb in debs:
            subprocess.run(["dpkg-deb", "-x", str(deb), str(SDCC_DIR)],
                           check=True)
        for deb in debs:
            deb.unlink()
    except (OSError, subprocess.CalledProcessError):
        return False
    return _sdcc_layout(SDCC_DIR) is not None


def _download_devkitsms() -> bool:
    if shutil.which("git") is None:
        return False
    TOOLS_DIR.mkdir(parents=True, exist_ok=True)
    print("devkitSMS not found; cloning pinned toolchain (~2 MB) ...")
    try:
        if DEVKITSMS_DIR.exists():
            shutil.rmtree(DEVKITSMS_DIR)
        DEVKITSMS_DIR.mkdir(parents=True)
        subprocess.run(["git", "init"], cwd=DEVKITSMS_DIR, check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run(["git", "remote", "add", "origin", DEVKITSMS_URL],
                       cwd=DEVKITSMS_DIR, check=True)
        subprocess.run(["git", "fetch", "--depth", "1", "origin",
                        DEVKITSMS_COMMIT], cwd=DEVKITSMS_DIR, check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run(["git", "checkout", "--detach", "FETCH_HEAD"],
                       cwd=DEVKITSMS_DIR, check=True, stdout=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return False
    return _devkitsms_layout(DEVKITSMS_DIR) is not None


def ensure_sms() -> tuple[
        tuple[tuple[Path, Path], tuple[Path, Path, Path]] | None, str | None]:
    """Return ((sdcc, devkitSMS), status_message). Downloads on first use."""
    found = find_sms()
    if found is not None:
        return found, (f"{_sdcc_label(*found[0])}; "
                       f"devkitSMS at {found[1][2].parents[2]}")
    if not _download_sdcc():
        return None, None
    if not _download_devkitsms():
        return None, None
    found = find_sms()
    if found is None:
        return None, None
    return found, (f"{_sdcc_label(*found[0])}; "
                   f"devkitSMS at {found[1][2].parents[2]}")


def sms_status() -> str:
    found = find_sms()
    if found is None:
        return "missing (run gr build --target sms)"
    return f"ok ({_sdcc_label(*found[0])}, {found[1][2].parents[2]})"
