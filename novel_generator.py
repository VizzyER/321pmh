#!/usr/bin/env python3
"""Long-form novel generator with consistency memory.

This script orchestrates million-word-scale novel generation by maintaining:
- world bible
- character bible
- chapter summaries
- timeline ledger

It can call any OpenAI-compatible chat-completions endpoint.
"""

from __future__ import annotations

import argparse
import json
import os
import textwrap
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class Character:
    name: str
    profile: str
    motivations: List[str] = field(default_factory=list)
    relationships: Dict[str, str] = field(default_factory=dict)


@dataclass
class NovelState:
    title: str
    genre: str
    premise: str
    total_chapters: int
    words_per_chapter: int
    style_guide: str
    world_bible: str
    chapter_summaries: List[str] = field(default_factory=list)
    timeline_events: List[str] = field(default_factory=list)
    characters: List[Character] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["characters"] = [asdict(c) for c in self.characters]
        return data

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "NovelState":
        return NovelState(
            title=data["title"],
            genre=data["genre"],
            premise=data["premise"],
            total_chapters=data["total_chapters"],
            words_per_chapter=data["words_per_chapter"],
            style_guide=data["style_guide"],
            world_bible=data["world_bible"],
            chapter_summaries=data.get("chapter_summaries", []),
            timeline_events=data.get("timeline_events", []),
            characters=[Character(**c) for c in data.get("characters", [])],
        )


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 180) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.8) -> str:
        payload = {
            "model": self.model,
            "temperature": temperature,
            "messages": messages,
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"HTTPError from model endpoint: {e.code} {msg}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"URL error while calling model endpoint: {e}") from e

        try:
            return parsed["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"Unexpected API response format: {parsed}") from e


class NovelGenerator:
    def __init__(self, client: LLMClient, state_path: Path, output_dir: Path) -> None:
        self.client = client
        self.state_path = state_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_state(self, state: NovelState) -> None:
        self.state_path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def load_state(self) -> NovelState:
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        return NovelState.from_dict(data)

    def create_initial_state(
        self,
        title: str,
        genre: str,
        premise: str,
        total_chapters: int,
        words_per_chapter: int,
        style_guide: str,
        world_bible: str,
        characters: List[Character],
    ) -> NovelState:
        state = NovelState(
            title=title,
            genre=genre,
            premise=premise,
            total_chapters=total_chapters,
            words_per_chapter=words_per_chapter,
            style_guide=style_guide,
            world_bible=world_bible,
            characters=characters,
        )
        self.save_state(state)
        return state

    def _consistency_pack(self, state: NovelState) -> str:
        recent_summaries = "\n".join(f"- {s}" for s in state.chapter_summaries[-5:]) or "- 无"
        timeline = "\n".join(f"- {e}" for e in state.timeline_events[-15:]) or "- 无"
        characters = "\n".join(
            f"- {c.name}: {c.profile}; 动机: {', '.join(c.motivations) or '未设置'}; 关系: {c.relationships or {}}"
            for c in state.characters
        )
        if not characters:
            characters = "- 无"

        return textwrap.dedent(
            f"""
            【作品信息】
            标题：{state.title}
            类型：{state.genre}
            核心设定：{state.premise}
            风格要求：{state.style_guide}

            【世界观圣经】
            {state.world_bible}

            【角色圣经】
            {characters}

            【最近章节摘要】
            {recent_summaries}

            【关键时间线】
            {timeline}
            """
        ).strip()

    def generate_one_chapter(self, state: NovelState, chapter_no: int) -> str:
        consistency = self._consistency_pack(state)
        system = (
            "你是一位长篇小说总编剧。必须保持人物性格稳定、事件因果闭环、设定不冲突。"
            "输出中文正文，不要解释过程。"
        )
        user = textwrap.dedent(
            f"""
            {consistency}

            现在请写第 {chapter_no} 章，目标字数约 {state.words_per_chapter} 字。
            要求：
            1) 与既有剧情连续，避免重复回顾。
            2) 至少推进一条主线和一条人物关系线。
            3) 结尾给出下一章钩子。
            4) 只输出小说正文。
            """
        ).strip()
        chapter_text = self.client.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], temperature=0.85)
        return chapter_text.strip()

    def summarize_chapter(self, chapter_text: str) -> Dict[str, Any]:
        system = "你是小说连续性编辑，负责提取摘要、时间线和角色状态变化。"
        user = textwrap.dedent(
            f"""
            请阅读以下章节正文，返回 JSON，字段：
            - summary: 不超过120字
            - timeline_events: 字符串数组，最多5条
            - character_updates: 对象，键是角色名，值是该角色变化（不超过60字）

            正文：
            {chapter_text}
            """
        ).strip()
        raw = self.client.chat([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ], temperature=0.2)
        try:
            start = raw.find("{")
            end = raw.rfind("}")
            payload = raw[start : end + 1]
            return json.loads(payload)
        except Exception as e:
            raise RuntimeError(f"无法解析章节摘要 JSON：{raw}") from e

    def build_chapter_outline(self, chapter_no: int, meta: Dict[str, Any]) -> str:
        meta = _normalize_generated_meta(meta)
        summary = str(meta.get("summary", "")).strip() or "（无摘要）"
        timeline_events = meta.get("timeline_events", [])
        if not isinstance(timeline_events, list):
            timeline_events = []
        updates = meta.get("character_updates", {})
        if not isinstance(updates, dict):
            updates = {}

        event_lines = "\n".join(f"- {str(event).strip()}" for event in timeline_events[:5] if str(event).strip())
        if not event_lines:
            event_lines = "- （无）"

        update_lines = "\n".join(
            f"- {name}: {str(change).strip()}"
            for name, change in updates.items()
            if str(name).strip() and str(change).strip()
        )
        if not update_lines:
            update_lines = "- （无）"

        return textwrap.dedent(
            f"""
            ## 第{chapter_no}章细纲摘要

            **剧情摘要**
            {summary}

            **关键事件**
            {event_lines}

            **人物变化**
            {update_lines}
            """
        ).strip()

    def run(self, resume: bool = False, start_chapter: int = 1) -> None:
        state = self.load_state() if resume else self.load_state()

        for chapter_no in range(start_chapter, state.total_chapters + 1):
            chapter_file = self.output_dir / f"chapter_{chapter_no:04d}.md"
            if chapter_file.exists():
                continue

            print(f"[INFO] Generating chapter {chapter_no}/{state.total_chapters}...")
            chapter_text = self.generate_one_chapter(state, chapter_no)
            meta = self.summarize_chapter(chapter_text)
            meta = _normalize_generated_meta(meta)
            chapter_outline = self.build_chapter_outline(chapter_no, meta)
            chapter_with_outline = f"{chapter_outline}\n\n---\n\n{chapter_text.strip()}\n"
            chapter_file.write_text(chapter_with_outline, encoding="utf-8")

            summary = meta.get("summary", "")
            state.chapter_summaries.append(f"第{chapter_no}章：{summary}")
            for event in meta.get("timeline_events", [])[:5]:
                state.timeline_events.append(f"第{chapter_no}章：{event}")

            updates = meta.get("character_updates", {})
            if isinstance(updates, dict):
                for char in state.characters:
                    if char.name in updates:
                        char.profile = f"{char.profile} | 最近变化：{updates[char.name]}"

            self.save_state(state)
            time.sleep(0.1)


def _normalize_summary(raw: Any) -> str:
    if isinstance(raw, str):
        summary = raw.strip()
        if summary:
            return summary
    return "（无摘要）"


def _normalize_character_updates(raw: Any) -> Dict[str, str]:
    if not isinstance(raw, dict):
        return {}

    updates: Dict[str, str] = {}
    for name, change in raw.items():
        if not isinstance(name, str) or not isinstance(change, str):
            continue
        clean_name = name.strip()
        clean_change = change.strip()
        if clean_name and clean_change:
            updates[clean_name] = clean_change
    return updates


def _normalize_generated_meta(meta: Any) -> Dict[str, Any]:
    normalized = dict(meta) if isinstance(meta, dict) else {}
    normalized["summary"] = _normalize_summary(normalized.get("summary"))
    normalized["character_updates"] = _normalize_character_updates(normalized.get("character_updates"))
    return normalized


def parse_characters(raw: str) -> List[Character]:
    """Parse character definitions.

    Format per line:
      name|profile|motivation1,motivation2|relationA:desc,relationB:desc
    """
    items: List[Character] = []
    if not raw.strip():
        return items
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|")]
        name = parts[0]
        profile = parts[1] if len(parts) > 1 else ""
        motivations = [m.strip() for m in parts[2].split(",")] if len(parts) > 2 and parts[2] else []
        relations: Dict[str, str] = {}
        if len(parts) > 3 and parts[3]:
            for seg in parts[3].split(","):
                if ":" in seg:
                    k, v = seg.split(":", 1)
                    relations[k.strip()] = v.strip()
        items.append(Character(name=name, profile=profile, motivations=motivations, relationships=relations))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Long-form novel generator with continuity memory")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--state", default="novel_state.json")
    parser.add_argument("--output", default="novel_output")

    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="initialize project state")
    init.add_argument("--title", required=True)
    init.add_argument("--genre", required=True)
    init.add_argument("--premise", required=True)
    init.add_argument("--total-chapters", type=int, default=300)
    init.add_argument("--words-per-chapter", type=int, default=3500)
    init.add_argument("--style-guide", default="第三人称、多线叙事、重视伏笔回收")
    init.add_argument("--world-bible", required=True)
    init.add_argument(
        "--characters",
        default="",
        help="多行角色定义：name|profile|mot1,mot2|other:relation",
    )

    run = sub.add_parser("run", help="generate chapters")
    run.add_argument("--start", type=int, default=1)

    args = parser.parse_args()

    if not args.api_key:
        raise SystemExit("OPENAI_API_KEY 未设置，请通过 --api-key 或环境变量传入。")

    client = LLMClient(base_url=args.base_url, api_key=args.api_key, model=args.model)
    generator = NovelGenerator(client=client, state_path=Path(args.state), output_dir=Path(args.output))

    if args.cmd == "init":
        chars = parse_characters(args.characters)
        generator.create_initial_state(
            title=args.title,
            genre=args.genre,
            premise=args.premise,
            total_chapters=args.total_chapters,
            words_per_chapter=args.words_per_chapter,
            style_guide=args.style_guide,
            world_bible=args.world_bible,
            characters=chars,
        )
        print(f"[OK] 初始化完成，状态文件：{args.state}")
    elif args.cmd == "run":
        generator.run(resume=True, start_chapter=args.start)
        print("[OK] 生成完成")


if __name__ == "__main__":
    main()
