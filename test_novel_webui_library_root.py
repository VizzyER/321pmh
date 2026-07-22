#!/usr/bin/env python3
"""Tests for novel_webui --library-root validation."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import novel_webui


class WebUILibraryRootTests(unittest.TestCase):
    def _run_main(self, argv: list[str]) -> MagicMock:
        mock_httpd = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_httpd
        with patch("novel_webui.make_server", return_value=mock_context) as mock_make_server:
            with patch("sys.argv", argv):
                novel_webui.main()
        return mock_make_server

    def test_missing_library_root_exits_before_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "missing-library-root"
            self.assertFalse(missing.exists())
            with patch("novel_webui.make_server") as mock_make_server:
                with patch("sys.argv", ["novel_webui.py", "--library-root", str(missing)]):
                    with self.assertRaises(SystemExit) as ctx:
                        novel_webui.main()
            self.assertIn("library root not found:", str(ctx.exception))
            mock_make_server.assert_not_called()

    def test_file_library_root_exits_before_server(self) -> None:
        with tempfile.NamedTemporaryFile() as tmp:
            with patch("novel_webui.make_server") as mock_make_server:
                with patch("sys.argv", ["novel_webui.py", "--library-root", tmp.name]):
                    with self.assertRaises(SystemExit) as ctx:
                        novel_webui.main()
            self.assertIn("library root is not a directory:", str(ctx.exception))
            mock_make_server.assert_not_called()

    def test_directory_library_root_starts_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_make_server = self._run_main(["novel_webui.py", "--library-root", tmpdir])
            mock_make_server.assert_called_once()


if __name__ == "__main__":
    unittest.main()
