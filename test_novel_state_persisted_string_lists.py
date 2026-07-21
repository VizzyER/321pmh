#!/usr/bin/env python3
"""Tests for persisted chapter_summaries / timeline_events list validation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from novel_generator import LLMClient, NovelGenerator, NovelState


def _valid_state_dict(**overrides):
    base = {
        "title": "Test",
        "genre": "Sci-Fi",
        "premise": "A test premise",
        "total_chapters": 10,
        "words_per_chapter": 3500,
        "style_guide": "Third person",
        "world_bible": "A test world",
        "chapter_summaries": ["第1章：开端"],
        "timeline_events": ["第1章：事件A"],
        "characters": [],
    }
    base.update(overrides)
    return base


class PersistedStringListValidationTests(unittest.TestCase):
    def test_missing_fields_default_to_empty_lists(self):
        data = _valid_state_dict()
        del data["chapter_summaries"]
        del data["timeline_events"]
        state = NovelState.from_dict(data)
        self.assertEqual(state.chapter_summaries, [])
        self.assertEqual(state.timeline_events, [])

    def test_valid_round_trip_preserves_strings_exactly(self):
        summaries = ["  leading space", "", "第2章：转折"]
        events = ["\t tabbed", "第2章：事件"]
        state = NovelState(
            title="Test",
            genre="Sci-Fi",
            premise="Premise",
            total_chapters=10,
            words_per_chapter=3500,
            style_guide="Style",
            world_bible="World",
            chapter_summaries=summaries,
            timeline_events=events,
        )
        restored = NovelState.from_dict(state.to_dict())
        self.assertEqual(restored.chapter_summaries, summaries)
        self.assertEqual(restored.timeline_events, events)

    def test_chapter_summaries_rejects_null(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(chapter_summaries=None))
        self.assertIn("chapter_summaries", str(ctx.exception))

    def test_timeline_events_rejects_null(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(timeline_events=None))
        self.assertIn("timeline_events", str(ctx.exception))

    def test_chapter_summaries_rejects_string_top_level(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(chapter_summaries="not a list"))
        msg = str(ctx.exception)
        self.assertIn("chapter_summaries", msg)
        self.assertIn("str", msg)

    def test_timeline_events_rejects_mapping_top_level(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(timeline_events={"event": "bad"}))
        msg = str(ctx.exception)
        self.assertIn("timeline_events", msg)
        self.assertIn("dict", msg)

    def test_chapter_summaries_rejects_numeric_top_level(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(chapter_summaries=42))
        msg = str(ctx.exception)
        self.assertIn("chapter_summaries", msg)
        self.assertIn("int", msg)

    def test_timeline_events_rejects_numeric_top_level(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(timeline_events=3.14))
        msg = str(ctx.exception)
        self.assertIn("timeline_events", msg)
        self.assertIn("float", msg)

    def test_chapter_summaries_rejects_non_string_element_with_index(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(chapter_summaries=["ok", 7, "also ok"]))
        msg = str(ctx.exception)
        self.assertIn("chapter_summaries[1]", msg)
        self.assertIn("int", msg)

    def test_timeline_events_rejects_non_string_element_with_index(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(timeline_events=["ok", None]))
        msg = str(ctx.exception)
        self.assertIn("timeline_events[1]", msg)
        self.assertIn("NoneType", msg)


class LoadStateIntegrationTests(unittest.TestCase):
    def test_load_state_rejects_invalid_persisted_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "novel_state.json"
            state_path.write_text(
                json.dumps(_valid_state_dict(chapter_summaries=["ok", {"bad": True}])),
                encoding="utf-8",
            )
            client = MagicMock(spec=LLMClient)
            generator = NovelGenerator(
                client=client,
                state_path=state_path,
                output_dir=Path(tmp) / "out",
            )
            with self.assertRaises(ValueError) as ctx:
                generator.load_state()
            self.assertIn("chapter_summaries[1]", str(ctx.exception))
            self.assertIn("dict", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
