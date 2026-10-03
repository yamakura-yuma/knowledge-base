#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""fetch_metrics.detect_maintenance の検査。ネットワークは使わない。

使い方: uv run docs/test_fetch_metrics.py
"""
from __future__ import annotations

import unittest

import fetch_metrics as fm

# microsoft/graphrag の README 冒頭の告知（2026-10-04 に GitHub API で確認した文面の要旨）
GRAPHRAG = (
    "> [!WARNING]\n"
    "> This project is largely in maintenance mode, and won't be accepting new PRs "
    "implementing new features.\n"
)


class DetectMaintenance(unittest.TestCase):
    def test_graphrag_announcement(self):
        self.assertEqual(fm.detect_maintenance(GRAPHRAG), "in maintenance mode")

    def test_hyphenated_and_case(self):
        self.assertEqual(fm.detect_maintenance("This repo is In Maintenance-Mode."),
                         "In Maintenance-Mode")

    def test_maintenance_only(self):
        self.assertEqual(fm.detect_maintenance("Status: maintenance only."), "maintenance only")

    def test_plain_readme_is_none(self):
        self.assertIsNone(fm.detect_maintenance("# Tool\nFast and maintained. Maintenance is easy."))

    def test_mode_without_announcement_is_none(self):
        # 機能の説明に出る "maintenance mode" は告知ではない
        self.assertIsNone(fm.detect_maintenance("Enable the maintenance mode flag to drain traffic."))

    def test_only_head_is_read(self):
        deep = "x" * fm.README_HEAD_CHARS + " in maintenance mode"
        self.assertIsNone(fm.detect_maintenance(deep))


if __name__ == "__main__":
    unittest.main()
