#!/usr/bin/env python3
"""Tests for timeline_events normalization in novel_generator."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from novel_generator import Character, NovelGenerator, NovelState, _normalize_timeline_events


class MockLLMClient:
    def __init__(self, summary_json: str) -> None:
        self.summary_json = summary_json
        self.calls = 0

    def chat(self, messages, temperature=0.8) -> str:
        self.calls += 1
        if self.calls == 1:
            return "章节正文"
        return self.summary_json


def _make_generator(summary_json: str, tmp: Path) -> NovelGenerator:
    state_path = tmp / "novel_state.json"
    output_dir = tmp / "novel_output"
    state = NovelState(
        title="测试",
        genre="科幻",
        premise="设定",
        total_chapters=1,
        words_per_chapter=100,
        style_guide="风格",
        world_bible="世界观",
        characters=[Character(name="主角", profile="初始")],
    )
    state_path.write_text(json.dumps(state.to_dict(), ensure_ascii=False), encoding="utf-8")
    return NovelGenerator(MockLLMClient(summary_json), state_path, output_dir)


def _extract_key_events(chapter_text: str) -> list[str]:
    section = chapter_text.split("**关键事件**", 1)[1].split("**人物变化**", 1)[0]
    return [line[2:].strip() for line in section.strip().splitlines() if line.startswith("- ")]


class NormalizeTimelineEventsTests(unittest.TestCase):
    def test_top_level_non_list_returns_empty(self) -> None:
        cases = [
            ("string", "单个字符串"),
            ("int", 42),
            ("none", None),
        ]
        for label, raw in cases:
            with self.subTest(label=label):
                self.assertEqual(_normalize_timeline_events(raw), [])

    def test_mixed_list_filters_strips_and_limits(self) -> None:
        raw = ["  alpha  ", "", "beta", 42, None, "gamma", "delta", "epsilon", "zeta", "eta"]
        self.assertEqual(
            _normalize_timeline_events(raw),
            ["alpha", "beta", "gamma", "delta", "epsilon"],
        )


class RunTimelineEventsTests(unittest.TestCase):
    def test_top_level_string_does_not_pollute_state(self) -> None:
        summary_json = json.dumps(
            {
                "summary": "摘要",
                "timeline_events": "单个字符串而非数组",
                "character_updates": {},
            },
            ensure_ascii=False,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            gen = _make_generator(summary_json, tmp)
            gen.run(resume=True, start_chapter=1)

            state = gen.load_state()
            self.assertEqual(state.timeline_events, [])

            chapter_text = (tmp / "novel_output" / "chapter_0001.md").read_text(encoding="utf-8")
            self.assertEqual(_extract_key_events(chapter_text), ["（无）"])

    def test_mixed_list_normalized_consistently_in_outline_and_state(self) -> None:
        summary_json = json.dumps(
            {
                "summary": "摘要",
                "timeline_events": ["  alpha  ", "", "beta", 42, None, "gamma", "delta", "epsilon", "zeta", "eta"],
                "character_updates": {},
            },
            ensure_ascii=False,
        )
        expected_events = ["alpha", "beta", "gamma", "delta", "epsilon"]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            gen = _make_generator(summary_json, tmp)
            gen.run(resume=True, start_chapter=1)

            state = gen.load_state()
            self.assertEqual(
                state.timeline_events,
                [f"第1章：{event}" for event in expected_events],
            )

            chapter_text = (tmp / "novel_output" / "chapter_0001.md").read_text(encoding="utf-8")
            self.assertEqual(_extract_key_events(chapter_text), expected_events)


if __name__ == "__main__":
    unittest.main()
