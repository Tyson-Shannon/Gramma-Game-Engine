"""Static checks for the pinned Docker toolchain definitions."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "gr"))

from gramma_cli import cc65, gbdk, sms  # noqa: E402


class DockerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dockerfile = (ROOT / "docker" / "Dockerfile").read_text(
            encoding="utf-8")

    def test_every_toolchain_has_a_stage(self):
        for stage in ("base", "gbdk", "cc65", "sms", "dev"):
            self.assertRegex(self.dockerfile, rf"(?m)^FROM .* AS {stage}$",
                             msg=f"missing Docker stage {stage}")

    def test_pins_match_cli_and_ci(self):
        self.assertIn("GBDK_VERSION=4.6.0", self.dockerfile)
        self.assertIn("CC65_VERSION=2.19", self.dockerfile)
        self.assertIn("SDCC_VERSION=4.5.0", self.dockerfile)
        self.assertIn(f"DEVKITSMS_COMMIT={sms.DEVKITSMS_COMMIT}",
                      self.dockerfile)
        self.assertEqual(
            re.search(r"^ARG GBDK_VERSION=(.*)$", self.dockerfile,
                      re.MULTILINE).group(1), "4.6.0")
        self.assertIn("4.6.0", gbdk.RELEASE_URL)
        self.assertEqual(sms.SDCC_EXPECTED_VERSION, "4.5.0")
        self.assertIn("V${CC65_VERSION}", self.dockerfile)

    def test_downloads_are_checksum_verified(self):
        sha_args = re.findall(r"^ARG ([A-Z0-9_]+)_SHA256=([0-9a-f]{64})$",
                              self.dockerfile, re.MULTILINE)
        self.assertEqual({name for name, _ in sha_args},
                         {"GBDK", "CC65", "SDCC", "DEVKITSMS"})
        for variable, digest in sha_args:
            self.assertIn(f'echo "${{{variable}_SHA256}}  ',
                          self.dockerfile)
        self.assertIn("sha256sum -c -", self.dockerfile)

    def test_cli_discovery_environment_is_exported(self):
        for variable in ("GBDK_HOME", "CC65_HOME", "SDCC_HOME",
                         "DEVKITSMS_HOME"):
            self.assertIn(f"ENV {variable}=", self.dockerfile)
        self.assertIn("COPY --from=gbdk", self.dockerfile)
        self.assertIn("COPY --from=cc65", self.dockerfile)
        self.assertIn("COPY --from=sms", self.dockerfile)

    def test_build_helper_documents_each_image(self):
        script = ROOT / "docker" / "build.sh"
        self.assertTrue(script.is_file())
        content = script.read_text(encoding="utf-8")
        self.assertIn("set -euo pipefail", content)
        for stage in ("gbdk", "cc65", "sms", "dev"):
            self.assertIn(stage, content)
        readme = (ROOT / "docker" / "README.md").read_text(encoding="utf-8")
        self.assertIn("not** used by hosted CI", readme)
        self.assertIn("DEVKITSMS_HOME", readme)


if __name__ == "__main__":
    unittest.main()
