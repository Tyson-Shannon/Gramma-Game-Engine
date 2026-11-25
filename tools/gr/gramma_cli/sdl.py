"""Find or locally bootstrap SDL2 development files.

CI installs libsdl2-dev normally. On a machine where only the runtime library
is installed, `gr` downloads the small Debian header package into
~/.cache/gramma (no sudo) so `meson` can still build the simulator.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True)


def _has_pkgconfig_sdl2() -> bool:
    if shutil.which("pkg-config") is None:
        return False
    return _run(["pkg-config", "--exists", "sdl2"]).returncode == 0


def _runtime_lib_arg() -> str | None:
    for name in ("libSDL2.so", "libSDL2-2.0.so.0"):
        probe = _run(["ldconfig", "-p"])
        if name in probe.stdout:
            return (f"-l:{name}" if name.endswith(".so.0") else "-lSDL2")
    if Path("/usr/lib/x86_64-linux-gnu/libSDL2.so").is_file():
        return "-lSDL2"
    return None


def sdl_environment(repo: Path) -> tuple[dict[str, str], str | None]:
    """Return (environment, description). Environment is a copy of os.environ."""
    env = os.environ.copy()
    if _has_pkgconfig_sdl2():
        return env, "SDL2 found via pkg-config"
    if env.get("SDL2_LIBRARY"):
        return env, "SDL2 configured via SDL2_* environment variables"

    # Keep the sysroot outside the source tree: Meson rejects absolute
    # include directories that live inside the project source directory.
    cache = Path.home() / ".cache" / "gramma" / "sdl2"
    sysroot = cache / "sysroot"
    header = sysroot / "usr/include/SDL2/SDL.h"
    if not header.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        print("SDL2 headers missing; downloading libsdl2-dev into ~/.cache/gramma ...")
        result = _run(["apt-get", "download", "libsdl2-dev"])
        if result.returncode != 0:
            return env, None
        debs = list(cache.glob("libsdl2-dev*.deb")) + list(
            Path.cwd().glob("libsdl2-dev*.deb"))
        if not debs:
            return env, None
        sysroot.mkdir(parents=True, exist_ok=True)
        extract = _run(["dpkg-deb", "-x", str(debs[0]), str(sysroot)])
        if debs[0].parent == Path.cwd():
            debs[0].unlink()
        if extract.returncode != 0:
            return env, None

    if not header.is_file():
        return env, None

    env["SDL2_INCLUDE_DIR"] = str(sysroot / "usr/include")
    arch_include = sysroot / "usr/include" / next(
        (p.name for p in (sysroot / "usr/include").iterdir()
         if (p / "SDL2/_real_SDL_config.h").is_file()), "")
    env["SDL2_ARCH_INCLUDE_DIR"] = str(arch_include)
    lib_arg = _runtime_lib_arg()
    if lib_arg is None:
        return env, None
    env["SDL2_LIBRARY"] = lib_arg
    return env, f"SDL2 bootstrapped in {sysroot}"


def sdl_status(repo: Path) -> str:
    if _has_pkgconfig_sdl2():
        return "ok (pkg-config)"
    if os.environ.get("SDL2_LIBRARY"):
        return "ok (environment)"
    if _runtime_lib_arg() is None:
        return "missing runtime library"
    if (Path.home() / ".cache/gramma/sdl2/sysroot/usr/include/SDL2/SDL.h").is_file():
        return "available via ~/.cache/gramma (run gr build to activate)"
    return "headers missing (run gr build to bootstrap)"
