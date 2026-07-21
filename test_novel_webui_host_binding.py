#!/usr/bin/env python3
"""Tests for novel_webui host binding defaults."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import novel_webui


class WebUIHostBindingTests(unittest.TestCase):
    def _run_main(self, argv: list[str]) -> MagicMock:
        mock_httpd = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_httpd
        with patch("novel_webui.make_server", return_value=mock_context) as mock_make_server:
            with patch("sys.argv", argv):
                novel_webui.main()
        return mock_make_server

    def test_default_host_is_loopback(self) -> None:
        library_root = str(Path(__file__).resolve().parent)
        mock_make_server = self._run_main(["novel_webui.py", "--library-root", library_root])

        mock_make_server.assert_called_once()
        self.assertEqual(mock_make_server.call_args[0][0], "127.0.0.1")

    def test_explicit_host_override_is_honored(self) -> None:
        library_root = str(Path(__file__).resolve().parent)
        mock_make_server = self._run_main(
            ["novel_webui.py", "--library-root", library_root, "--host", "0.0.0.0"]
        )

        mock_make_server.assert_called_once()
        self.assertEqual(mock_make_server.call_args[0][0], "0.0.0.0")


if __name__ == "__main__":
    unittest.main()
