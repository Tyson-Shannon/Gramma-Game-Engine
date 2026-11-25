"""Structural verification for built SMS/GG ROMs.

There is no maintained headless Python emulator for the Master System in our CI
image, so the SMS gate checks the bytes that matter for boot and banking:
SEGA header, region/size code, checksum, and the bank 2/3 sentinels emitted by
the shipped example. Emulator-based smoke tests remain the gate for PC/GB/NES.
"""

from __future__ import annotations

import argparse
from pathlib import Path

SIZE_CODES = {2: 0xc, 4: 0xe, 8: 0xf, 16: 0x0, 32: 0x1, 64: 0x2}


def verify(rom: Path, banks: int = 4, gg: bool = False) -> None:
    if banks not in SIZE_CODES:
        raise SystemExit(f"unsupported SMS bank count: {banks}")
    data = rom.read_bytes()
    expected_size = banks * 16384
    if len(data) != expected_size:
        raise SystemExit(f"expected {expected_size} bytes, got {len(data)}")
    if data[0x7ff0:0x7ff8] != b"TMR SEGA":
        raise SystemExit("SEGA header signature missing")

    region = (7 if gg else 4) << 4 | SIZE_CODES[banks]
    if data[0x7fff] != region:
        raise SystemExit(
            f"region/size byte is 0x{data[0x7fff]:02x}, expected 0x{region:02x}")

    checksum = sum(data[:0x7ff0]) & 0xffff
    stored = int.from_bytes(data[0x7ffa:0x7ffc], "little")
    if checksum != stored:
        raise SystemExit(
            f"checksum mismatch: stored 0x{stored:04x}, "
            f"calculated 0x{checksum:04x}")

    if banks > 2 and data[0x8000] != 0x5a:
        raise SystemExit("bank 2 sentinel missing")
    if banks > 3 and data[0xc000] != 0x3c:
        raise SystemExit("bank 3 sentinel missing")
    print(f"SMS ROM check OK: {banks} banks, "
          f"{'Game Gear' if gg else 'Master System'}, "
          f"checksum 0x{checksum:04x}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--banks", type=int, default=4)
    parser.add_argument("--gg", action="store_true")
    args = parser.parse_args()
    verify(args.rom, args.banks, args.gg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
