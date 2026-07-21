#!/usr/bin/env python3
"""Tests for persisted required string field validation in NovelState.from_dict."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from novel_generator import LLMClient, NovelGenerator, NovelState

REQUIRED_STRING_FIELDS = ("title", "genre", "premise", "style_guide", "world_bible")

INVALID_TYPE_CASES = (
    ("null", None, "NoneType"),
    ("bool", True, "bool"),
    ("int", 42, "int"),
    ("float", 3.14, "float"),
    ("list", ["text"], "list"),
    ("dict", {"text": "value"}, "dict"),
)


def _valid_state_dict(**overrides):
    base = {
        "title": "Test Novel",
        "genre": "Sci-Fi",
        "premise": "A test premise",
        "total_chapters": 10,
        "words_per_chapter": 3500,
        "style_guide": "Third person",
        "world_bible": "A test world",
        "chapter_summaries": [],
        "timeline_events": [],
        "characters": [],
    }
    base.update(overrides)
    return base


class RequiredStringFieldValidationTests(unittest.TestCase):
    def test_each_missing_field_raises_required_error(self):
        for field_name in REQUIRED_STRING_FIELDS:
            with self.subTest(field=field_name):
                data = _valid_state_dict()
                del data[field_name]
                with self.assertRaises(ValueError) as ctx:
                    NovelState.from_dict(data)
                self.assertEqual(str(ctx.exception), f"{field_name} is required")

    def test_each_field_rejects_invalid_types_with_type_name(self):
        for field_name in REQUIRED_STRING_FIELDS:
            for case_name, invalid_value, type_name in INVALID_TYPE_CASES:
                with self.subTest(field=field_name, invalid_type=case_name):
                    with self.assertRaises(ValueError) as ctx:
                        NovelState.from_dict(_valid_state_dict(**{field_name: invalid_value}))
                    msg = str(ctx.exception)
                    self.assertEqual(msg, f"{field_name} must be a string, got {type_name}")
                    self.assertIn(field_name, msg)
                    self.assertIn(type_name, msg)

    def test_valid_strings_are_preserved_exactly(self):
        preserved = {
            "title": "  leading space",
            "genre": "\t tabbed",
            "premise": "",
            "style_guide": "多线叙事 🚀",
            "world_bible": " trailing space ",
        }
        state = NovelState.from_dict(_valid_state_dict(**preserved))
        self.assertEqual(state.title, preserved["title"])
        self.assertEqual(state.genre, preserved["genre"])
        self.assertEqual(state.premise, preserved["premise"])
        self.assertEqual(state.style_guide, preserved["style_guide"])
        self.assertEqual(state.world_bible, preserved["world_bible"])

    def test_valid_round_trip_preserves_required_strings(self):
        state = NovelState(
            title="  spaced title",
            genre="",
            premise="核心设定",
            total_chapters=10,
            words_per_chapter=3500,
            style_guide="\n newline",
            world_bible="世界 🌍",
        )
        restored = NovelState.from_dict(state.to_dict())
        self.assertEqual(restored.title, state.title)
        self.assertEqual(restored.genre, state.genre)
        self.assertEqual(restored.premise, state.premise)
        self.assertEqual(restored.style_guide, state.style_guide)
        self.assertEqual(restored.world_bible, state.world_bible)


class LoadStateIntegrationTests(unittest.TestCase):
    def test_load_state_rejects_missing_required_string_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "novel_state.json"
            data = _valid_state_dict()
            del data["world_bible"]
            state_path.write_text(json.dumps(data), encoding="utf-8")
            client = MagicMock(spec=LLMClient)
            generator = NovelGenerator(
                client=client,
                state_path=state_path,
                output_dir=Path(tmp) / "out",
            )
            with self.assertRaises(ValueError) as ctx:
                generator.load_state()
            self.assertEqual(str(ctx.exception), "world_bible is required")


if __name__ == "__main__":
    unittest.main()
