"""Tests for human architect LOCK."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from src.overnight import lock as lock_mod


class TestOvernightLock(unittest.TestCase):
    def test_lock_blocks_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "LOCK"
            lock_path.write_text(
                json.dumps({"owner": "human-architect", "reason": "deploy"}),
                encoding="utf-8",
            )
            with mock.patch.object(lock_mod, "LOCK_PATH", lock_path):
                locked, msg = lock_mod.is_locked()
            self.assertTrue(locked)
            self.assertIn("human-architect", msg)


if __name__ == "__main__":
    unittest.main()
