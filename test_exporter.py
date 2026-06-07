#!/usr/bin/env -S uv run
"""Unit Tests for Exporter Module.

This module provides unit tests for the exporter.py script, focusing on
sanitization, idempotency paths, and correct file generation.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

from exporter import _sanitize_filename, export_bitlinks


class TestExporter(unittest.TestCase):
    """Test suite for the exporter functions."""

    def test_sanitize_filename(self):
        """Verify _sanitize_filename handles special characters correctly."""
        self.assertEqual(_sanitize_filename("bit.ly/123"), "bit_ly_123")
        self.assertEqual(_sanitize_filename("Éxito"), "xito")
        self.assertEqual(
            _sanitize_filename("https://bit.ly/xyz-123"),
            "https___bit_ly_xyz-123",
        )
        self.assertEqual(_sanitize_filename(""), "export")
        self.assertEqual(_sanitize_filename("---"), "---")

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    def test_export_bitlinks_json_general(self, mock_file, mock_mkdir):
        """Verify export_bitlinks writes JSON format for general exports."""
        links = [{"id": "bit.ly/123", "title": "Test"}]
        export_bitlinks(
            "GeneralGroup",
            links,
            "json",
            output_dir="mock_out",
            is_single_link=False,
        )

        mock_mkdir.assert_called_once()
        expected_path = (
            Path("mock_out").resolve() / "output" / "general" / "bitlinks.json"
        )
        mock_file.assert_called_once_with(expected_path, "w", encoding="utf-8")

        # Verify JSON dumping occurred and last_updated was injected
        written_content = "".join(
            call.args[0] for call in mock_file().write.mock_calls
        )
        data = json.loads(written_content)
        self.assertEqual(data[0]["id"], "bit.ly/123")
        self.assertIn("last_updated", data[0])

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    def test_export_bitlinks_csv_specific(self, mock_file, mock_mkdir):
        """Verify specific link exports route correctly in CSV format."""
        links = [{"id": "bit.ly/xyz", "title": "Specific Link"}]
        export_bitlinks(
            "SingleLink",
            links,
            "csv",
            output_dir="mock_out",
            is_single_link=True,
        )

        mock_mkdir.assert_called_once()
        expected_path = (
            Path("mock_out").resolve()
            / "output"
            / "specifics"
            / "bit_ly_xyz.csv"
        )
        mock_file.assert_called_once_with(
            expected_path, "w", encoding="utf-8", newline=""
        )

        # Verify CSV writing (headers and row)
        written_content = "".join(
            call.args[0] for call in mock_file().write.mock_calls
        )
        self.assertIn("id", written_content)
        self.assertIn("title", written_content)
        self.assertIn("last_updated", written_content)
        self.assertIn("bit.ly/xyz", written_content)
        self.assertIn("Specific Link", written_content)

    @patch("pathlib.Path.mkdir")
    @patch("builtins.open", new_callable=mock_open)
    def test_export_bitlinks_both_with_analytics(self, mock_file, mock_mkdir):
        """Verify export_bitlinks exports both and uses _enriched."""
        links = [{"id": "bit.ly/abc", "title": "Test", "total_clicks": 5}]
        export_bitlinks(
            "TestGroup",
            links,
            "both",
            output_dir="mock_out",
            is_single_link=False,
            has_analytics=True,
        )

        self.assertEqual(mock_file.call_count, 2)
        expected_json = (
            Path("mock_out").resolve()
            / "output"
            / "general"
            / "bitlinks_enriched.json"
        )
        expected_csv = (
            Path("mock_out").resolve()
            / "output"
            / "general"
            / "bitlinks_enriched.csv"
        )
        mock_file.assert_any_call(expected_json, "w", encoding="utf-8")
        mock_file.assert_any_call(
            expected_csv, "w", encoding="utf-8", newline=""
        )

    def test_export_bitlinks_invalid_format(self):
        """Verify export_bitlinks raises ValueError for unsupported formats."""
        links = [{"id": "bit.ly/123"}]
        with self.assertRaises(ValueError):
            export_bitlinks("Group", links, "xml", output_dir="mock_out")


if __name__ == "__main__":
    unittest.main()
