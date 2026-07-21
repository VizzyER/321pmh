#!/usr/bin/env python3
"""Tests for strict NovelState chapter-count validation."""

from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from novel_generator import (
    LLMClient,
    NovelGenerator,
    NovelState,
    parse_positive_int,
)


def _valid_state_kwargs(**overrides):
    base = {
        "title": "Test",
        "genre": "Sci-Fi",
        "premise": "A test premise",
        "total_chapters": 10,
        "words_per_chapter": 3500,
        "style_guide": "Third person",
        "world_bible": "A test world",
    }
    base.update(overrides)
    return base


class NovelStateValidationTests(unittest.TestCase):
    def test_valid_round_trip(self):
        state = NovelState(**_valid_state_kwargs())
        restored = NovelState.from_dict(state.to_dict())
        self.assertEqual(restored.total_chapters, 10)
        self.assertEqual(restored.words_per_chapter, 3500)
        self.assertEqual(restored.title, state.title)

    def test_total_chapters_rejects_bool(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState(**_valid_state_kwargs(total_chapters=True))
        self.assertIn("total_chapters", str(ctx.exception))

    def test_total_chapters_rejects_string(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState(**_valid_state_kwargs(total_chapters="10"))
        self.assertIn("total_chapters", str(ctx.exception))

    def test_total_chapters_rejects_float(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState(**_valid_state_kwargs(total_chapters=10.0))
        self.assertIn("total_chapters", str(ctx.exception))

    def test_total_chapters_rejects_zero(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState(**_valid_state_kwargs(total_chapters=0))
        self.assertIn("total_chapters", str(ctx.exception))

    def test_total_chapters_rejects_negative(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState(**_valid_state_kwargs(total_chapters=-3))
        self.assertIn("total_chapters", str(ctx.exception))

    def test_words_per_chapter_rejects_bool(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState(**_valid_state_kwargs(words_per_chapter=False))
        self.assertIn("words_per_chapter", str(ctx.exception))

    def test_words_per_chapter_rejects_string(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState(**_valid_state_kwargs(words_per_chapter="3500"))
        self.assertIn("words_per_chapter", str(ctx.exception))

    def test_words_per_chapter_rejects_float(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState(**_valid_state_kwargs(words_per_chapter=3500.5))
        self.assertIn("words_per_chapter", str(ctx.exception))

    def test_words_per_chapter_rejects_zero(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState(**_valid_state_kwargs(words_per_chapter=0))
        self.assertIn("words_per_chapter", str(ctx.exception))

    def test_words_per_chapter_rejects_negative(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState(**_valid_state_kwargs(words_per_chapter=-100))
        self.assertIn("words_per_chapter", str(ctx.exception))

    def test_from_dict_invalid_total_chapters_includes_field_name(self):
        data = _valid_state_kwargs()
        data["total_chapters"] = 0
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(data)
        self.assertIn("total_chapters", str(ctx.exception))

    def test_from_dict_invalid_words_per_chapter_includes_field_name(self):
        data = _valid_state_kwargs()
        data["words_per_chapter"] = "bad"
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(data)
        self.assertIn("words_per_chapter", str(ctx.exception))


class CreateInitialStateValidationTests(unittest.TestCase):
    def test_invalid_total_chapters_does_not_write_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "novel_state.json"
            client = MagicMock(spec=LLMClient)
            generator = NovelGenerator(client=client, state_path=state_path, output_dir=Path(tmp) / "out")
            with self.assertRaises(ValueError):
                generator.create_initial_state(
                    title="Test",
                    genre="Sci-Fi",
                    premise="Premise",
                    total_chapters=0,
                    words_per_chapter=3500,
                    style_guide="Style",
                    world_bible="World",
                    characters=[],
                )
            self.assertFalse(state_path.exists())

    def test_invalid_words_per_chapter_does_not_write_state_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "novel_state.json"
            client = MagicMock(spec=LLMClient)
            generator = NovelGenerator(client=client, state_path=state_path, output_dir=Path(tmp) / "out")
            with self.assertRaises(ValueError):
                generator.create_initial_state(
                    title="Test",
                    genre="Sci-Fi",
                    premise="Premise",
                    total_chapters=10,
                    words_per_chapter=-1,
                    style_guide="Style",
                    world_bible="World",
                    characters=[],
                )
            self.assertFalse(state_path.exists())


class ParsePositiveIntTests(unittest.TestCase):
    def test_accepts_valid_string_integer(self):
        self.assertEqual(parse_positive_int("3"), 3)
        self.assertEqual(parse_positive_int("3500"), 3500)

    def test_rejects_zero(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_positive_int("0")

    def test_rejects_negative(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_positive_int("-1")

    def test_rejects_non_integer_string(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_positive_int("abc")

    def test_rejects_float_string(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_positive_int("3.5")


if __name__ == "__main__":
    unittest.main()
