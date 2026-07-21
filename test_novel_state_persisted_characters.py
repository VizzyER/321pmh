#!/usr/bin/env python3
"""Tests for persisted characters list validation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from novel_generator import Character, LLMClient, NovelGenerator, NovelState


def _valid_state_dict(**overrides):
    base = {
        "title": "Test",
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


def _full_character_dict(**overrides):
    base = {
        "name": "林策",
        "profile": "年轻航道测绘师",
        "motivations": ["寻找失踪父亲", "守住人类火种"],
        "relationships": {"苏岚": "同盟且互相隐瞒"},
    }
    base.update(overrides)
    return base


class PersistedCharactersValidationTests(unittest.TestCase):
    def test_missing_characters_defaults_to_empty_list(self):
        data = _valid_state_dict()
        del data["characters"]
        state = NovelState.from_dict(data)
        self.assertEqual(state.characters, [])

    def test_valid_complete_character_loads(self):
        character = _full_character_dict()
        state = NovelState.from_dict(_valid_state_dict(characters=[character]))
        self.assertEqual(len(state.characters), 1)
        loaded = state.characters[0]
        self.assertEqual(loaded.name, "林策")
        self.assertEqual(loaded.profile, "年轻航道测绘师")
        self.assertEqual(loaded.motivations, ["寻找失踪父亲", "守住人类火种"])
        self.assertEqual(loaded.relationships, {"苏岚": "同盟且互相隐瞒"})

    def test_optional_fields_default_when_omitted(self):
        character = {"name": "苏岚", "profile": "环带议会特使"}
        state = NovelState.from_dict(_valid_state_dict(characters=[character]))
        loaded = state.characters[0]
        self.assertEqual(loaded.motivations, [])
        self.assertEqual(loaded.relationships, {})

    def test_empty_strings_for_required_fields_are_allowed(self):
        character = {"name": "", "profile": ""}
        state = NovelState.from_dict(_valid_state_dict(characters=[character]))
        loaded = state.characters[0]
        self.assertEqual(loaded.name, "")
        self.assertEqual(loaded.profile, "")

    def test_valid_round_trip_preserves_character_fields(self):
        state = NovelState(
            title="Test",
            genre="Sci-Fi",
            premise="Premise",
            total_chapters=10,
            words_per_chapter=3500,
            style_guide="Style",
            world_bible="World",
            characters=[
                Character(
                    name="  spaced  ",
                    profile="",
                    motivations=["  keep spaces  ", ""],
                    relationships={" ally ": " trusted "},
                )
            ],
        )
        restored = NovelState.from_dict(state.to_dict())
        self.assertEqual(len(restored.characters), 1)
        loaded = restored.characters[0]
        self.assertEqual(loaded.name, "  spaced  ")
        self.assertEqual(loaded.profile, "")
        self.assertEqual(loaded.motivations, ["  keep spaces  ", ""])
        self.assertEqual(loaded.relationships, {" ally ": " trusted "})

    def test_characters_rejects_null(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(characters=None))
        msg = str(ctx.exception)
        self.assertIn("characters", msg)
        self.assertIn("NoneType", msg)

    def test_characters_rejects_string_top_level(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(characters="not a list"))
        msg = str(ctx.exception)
        self.assertIn("characters", msg)
        self.assertIn("str", msg)

    def test_characters_rejects_tuple_top_level(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(characters=({"name": "A", "profile": "B"},)))
        msg = str(ctx.exception)
        self.assertIn("characters", msg)
        self.assertIn("tuple", msg)

    def test_characters_rejects_mapping_top_level(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(characters={"name": "bad"}))
        msg = str(ctx.exception)
        self.assertIn("characters", msg)
        self.assertIn("dict", msg)

    def test_characters_rejects_non_dict_item(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(characters=[{"name": "ok", "profile": "ok"}, "bad"]))
        msg = str(ctx.exception)
        self.assertIn("characters[1]", msg)
        self.assertIn("str", msg)

    def test_characters_rejects_missing_name(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(characters=[{"profile": "only profile"}]))
        self.assertIn("characters[0].name is required", str(ctx.exception))

    def test_characters_rejects_missing_profile(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(characters=[{"name": "only name"}]))
        self.assertIn("characters[0].profile is required", str(ctx.exception))

    def test_characters_rejects_unknown_field(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(
                _valid_state_dict(characters=[{"name": "A", "profile": "B", "extra": 1}])
            )
        msg = str(ctx.exception)
        self.assertIn("characters[0].extra", msg)
        self.assertIn("int", msg)

    def test_characters_rejects_non_string_field_name(self):
        payload = {"name": "A", "profile": "B"}
        payload[1] = "bad"
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(characters=[payload]))
        msg = str(ctx.exception)
        self.assertIn("characters[0]", msg)
        self.assertIn("field name must be a string", msg)
        self.assertIn("int", msg)

    def test_characters_rejects_mixed_unknown_keys_without_type_error(self):
        non_string_first = {42: "bad", "name": "A", "profile": "B", "extra": 1}
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(characters=[non_string_first]))
        msg = str(ctx.exception)
        self.assertIn("characters[0]", msg)
        self.assertIn("field name must be a string", msg)
        self.assertIn("int", msg)

        string_first = {"name": "A", "profile": "B", "extra": 1}
        string_first[42] = "bad"
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(_valid_state_dict(characters=[string_first]))
        msg = str(ctx.exception)
        self.assertIn("characters[0].extra", msg)
        self.assertIn("int", msg)

    def test_characters_rejects_non_string_name(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(
                _valid_state_dict(characters=[{"name": 42, "profile": "ok"}])
            )
        msg = str(ctx.exception)
        self.assertIn("characters[0].name", msg)
        self.assertIn("int", msg)

    def test_characters_rejects_non_string_profile(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(
                _valid_state_dict(characters=[{"name": "ok", "profile": None}])
            )
        msg = str(ctx.exception)
        self.assertIn("characters[0].profile", msg)
        self.assertIn("NoneType", msg)

    def test_characters_rejects_null_motivations(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(
                _valid_state_dict(
                    characters=[{"name": "A", "profile": "B", "motivations": None}]
                )
            )
        msg = str(ctx.exception)
        self.assertIn("characters[0].motivations", msg)
        self.assertIn("NoneType", msg)

    def test_characters_rejects_tuple_motivations(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(
                _valid_state_dict(
                    characters=[{"name": "A", "profile": "B", "motivations": ("x",)}]
                )
            )
        msg = str(ctx.exception)
        self.assertIn("characters[0].motivations", msg)
        self.assertIn("tuple", msg)

    def test_characters_rejects_non_string_motivation_element(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(
                _valid_state_dict(
                    characters=[
                        {
                            "name": "A",
                            "profile": "B",
                            "motivations": ["ok", 7],
                        }
                    ]
                )
            )
        msg = str(ctx.exception)
        self.assertIn("characters[0].motivations[1]", msg)
        self.assertIn("int", msg)

    def test_characters_rejects_null_relationships(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(
                _valid_state_dict(
                    characters=[{"name": "A", "profile": "B", "relationships": None}]
                )
            )
        msg = str(ctx.exception)
        self.assertIn("characters[0].relationships", msg)
        self.assertIn("NoneType", msg)

    def test_characters_rejects_list_relationships(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(
                _valid_state_dict(
                    characters=[{"name": "A", "profile": "B", "relationships": []}]
                )
            )
        msg = str(ctx.exception)
        self.assertIn("characters[0].relationships", msg)
        self.assertIn("list", msg)

    def test_characters_rejects_non_string_relationship_key(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(
                _valid_state_dict(
                    characters=[
                        {
                            "name": "A",
                            "profile": "B",
                            "relationships": {1: "desc"},
                        }
                    ]
                )
            )
        msg = str(ctx.exception)
        self.assertIn("characters[0].relationships key", msg)
        self.assertIn("int", msg)

    def test_characters_rejects_non_string_relationship_value(self):
        with self.assertRaises(ValueError) as ctx:
            NovelState.from_dict(
                _valid_state_dict(
                    characters=[
                        {
                            "name": "A",
                            "profile": "B",
                            "relationships": {"ally": 99},
                        }
                    ]
                )
            )
        msg = str(ctx.exception)
        self.assertIn("characters[0].relationships[ally]", msg)
        self.assertIn("int", msg)

    def test_loaded_containers_are_isolated_from_input_mutation(self):
        motivations = ["original"]
        relationships = {"friend": "close"}
        character_dict = {
            "name": "A",
            "profile": "B",
            "motivations": motivations,
            "relationships": relationships,
        }
        characters_list = [character_dict]
        data = _valid_state_dict(characters=characters_list)

        state = NovelState.from_dict(data)

        motivations.append("mutated")
        relationships["friend"] = "changed"
        relationships["new"] = "entry"
        character_dict["name"] = "mutated name"
        character_dict["profile"] = "mutated profile"
        characters_list.append({"name": "X", "profile": "Y"})

        loaded = state.characters[0]
        self.assertEqual(loaded.name, "A")
        self.assertEqual(loaded.profile, "B")
        self.assertEqual(loaded.motivations, ["original"])
        self.assertEqual(loaded.relationships, {"friend": "close"})
        self.assertEqual(len(state.characters), 1)


class LoadStateCharactersIntegrationTests(unittest.TestCase):
    def test_load_state_rejects_invalid_persisted_characters(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "novel_state.json"
            state_path.write_text(
                json.dumps(
                    _valid_state_dict(
                        characters=[{"name": "ok", "profile": "ok", "motivations": ["x", None]}]
                    )
                ),
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
            msg = str(ctx.exception)
            self.assertIn("characters[0].motivations[1]", msg)
            self.assertIn("NoneType", msg)


if __name__ == "__main__":
    unittest.main()
