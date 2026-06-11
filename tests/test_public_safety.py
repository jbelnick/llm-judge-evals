from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from public_safety_scan import scan  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]


class PublicSafetyTests(unittest.TestCase):
    def test_scan_detects_runtime_banned_term(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.txt").write_text("ForbiddenClient appears here.\n", encoding="utf-8")
            findings = scan(root, ["ForbiddenClient"])
        self.assertEqual(len(findings), 1)

    def test_scan_passes_clean_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.txt").write_text("Only synthetic public data.\n", encoding="utf-8")
            findings = scan(root, ["ForbiddenClient"])
        self.assertEqual(findings, [])

    def test_repo_itself_is_clean(self) -> None:
        self.assertEqual(scan(REPO_ROOT, []), [])


if __name__ == "__main__":
    unittest.main()
