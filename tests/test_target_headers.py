"""C89 compile checks for the opt-in per-target extension headers."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SOURCE = """#include <gramma/target/gb/system.h>
#include <gramma/target/nes/system.h>
#include <gramma/target/sms/system.h>

int main(void)
{
    gr_gb_system_caps gb;
    gr_nes_system_caps nes;
    gr_sms_system_caps sms;
    return (int)(GR_GB_TILE_BYTES + GR_NES_TILE_BYTES
                 + GR_SMS_TILE_BYTES + sizeof(gb) + sizeof(nes)
                 + sizeof(sms));
}
"""


class TargetHeaderTests(unittest.TestCase):
    def test_headers_are_c89_clean_for_every_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "caps.c"
            source.write_text(SOURCE, encoding="utf-8")
            for macro in ("PC", "GB", "NES", "SMS"):
                with self.subTest(target=macro):
                    result = subprocess.run(
                        ["gcc", "-std=c89", "-pedantic", "-Wall", "-Wextra",
                         "-fsyntax-only", f"-DGRAMMA_TARGET_{macro}",
                         "-I", str(ROOT / "core" / "include"), str(source)],
                        capture_output=True, text=True, check=False)
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_portable_header_stays_opt_in(self):
        text = (ROOT / "core" / "include" / "gramma" / "gramma.h").read_text(
            encoding="utf-8")
        self.assertNotIn("target/gb/system.h", text)
        self.assertNotIn("target/nes/system.h", text)
        self.assertNotIn("target/sms/system.h", text)


if __name__ == "__main__":
    unittest.main()
