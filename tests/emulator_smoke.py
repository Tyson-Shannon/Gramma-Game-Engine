"""Emulator smoke checks for built Gramma ROMs.

These are intentionally not part of the unittest discovery: they need built
ROMs and the optional ``pyboy``/``nes-py`` Python packages. CI runs them after
the corresponding ``gr build`` steps; the same commands work locally. The NES
check requires Python 3.13+ and ``nes-py>=9``, which uses Gymnasium and NumPy
2; older Gym-based releases are unsupported. SMS/GG uses
``tests/sms_rom_check.py`` instead because
no maintained headless SMS emulator is available in the CI image.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def _colors(frame: np.ndarray) -> int:
    pixels = frame.reshape(-1, frame.shape[-1])
    return int(len(np.unique(pixels, axis=0)))


def _diff(before: np.ndarray, after: np.ndarray) -> int:
    return int(np.count_nonzero(np.any(before != after, axis=2)))


def gb_smoke(rom: Path, expect_toggle: bool = True) -> None:
    """Verify that the GB ROM renders and B stages a visible overlay."""
    from pyboy import PyBoy

    pyboy = PyBoy(str(rom), window="null")
    try:
        for _ in range(120):
            pyboy.tick()
        before = np.array(pyboy.screen.ndarray, copy=True)[:, :, :3]
        idle_colors = _colors(before)
        if idle_colors < 4:
            raise SystemExit(f"GB idle frame has only {idle_colors} colors")

        changed = 0
        if expect_toggle:
            pyboy.button_press("B")
            for _ in range(30):
                pyboy.tick()
            pyboy.button_release("B")
            for _ in range(30):
                pyboy.tick()
            after = np.array(pyboy.screen.ndarray, copy=True)[:, :, :3]
            changed = _diff(before, after)
            if changed == 0:
                raise SystemExit("GB B button did not change the overlay")
        print(f"GB smoke OK: {idle_colors} idle colors, {changed} overlay pixels")
    finally:
        pyboy.stop(save=False)


def nes_smoke(rom: Path, warmup_frames: int = 180) -> None:
    """Verify that the NES ROM renders and B switches the sprite CHR bank."""
    from nes_py import NESEnv

    try:
        from gymnasium import Env
    except ImportError as error:
        raise SystemExit(
            "NES smoke needs nes-py>=9 (Gymnasium); run "
            "'pip install -U \"nes-py>=9\"'") from error
    if not issubclass(NESEnv, Env):
        raise SystemExit(
            "installed nes-py uses unmaintained Gym; run "
            "'pip install -U \"nes-py>=9\"' for Gymnasium/NumPy 2 support")

    env = NESEnv(str(rom))
    try:
        screen, _ = env.reset(seed=0)
        for _ in range(warmup_frames):
            screen, _, _, _, _ = env.step(0)
        before = np.array(screen, copy=True)
        idle_colors = _colors(before)
        if idle_colors < 4:
            raise SystemExit(f"NES idle frame has only {idle_colors} colors")

        # nes-py's one-frame edge can be missed while the custom NMI runs, so
        # hold B and latch gr_pad_down() instead.
        for _ in range(40):
            screen, _, _, _, _ = env.step(0x02)
        for _ in range(40):
            screen, _, _, _, _ = env.step(0)
        after = np.array(screen, copy=True)
        changed = _diff(before, after)
        if changed == 0:
            raise SystemExit("NES B button did not switch sprite art")
        print(f"NES smoke OK: {idle_colors} idle colors, {changed} sprite pixels")
    finally:
        env.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="console", required=True)

    gb = commands.add_parser("gb", help="smoke-test a .gb ROM with PyBoy")
    gb.add_argument("rom", type=Path)
    gb.add_argument("--no-toggle", action="store_true",
                    help="skip the B overlay check for fixed-layout ROMs")

    nes = commands.add_parser("nes", help="smoke-test a .nes ROM with nes-py")
    nes.add_argument("rom", type=Path)
    nes.add_argument("--warmup-frames", type=int, default=180)

    args = parser.parse_args()
    if not args.rom.is_file():
        parser.error(f"ROM not found: {args.rom}")
    if args.console == "gb":
        gb_smoke(args.rom, expect_toggle=not args.no_toggle)
    else:
        nes_smoke(args.rom, warmup_frames=args.warmup_frames)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
