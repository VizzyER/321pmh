#!/usr/bin/env python3
"""Long-form novel generator with setup -> outline -> volume plan -> chapter generation."""

from __future__ import annotations

import argparse
import json
import os
import random
import textwrap
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

GENRE_OPTIONS = ["科幻", "奇幻", "都市", "悬疑", "历史", "武侠", "赛博朋克", "末日", "言情", "成长"]
ROLE_OPTIONS = ["主角", "配角", "反派", "导师", "同伴", "关键线人"]
GENDER_OPTIONS = ["男", "女", "非二元"]
PERSONALITY_OPTIONS = ["冷静", "冲动", "敏感", "理性", "幽默", "偏执", "坚韧", "温柔", "果断", "神秘"]
OUTFIT_OPTIONS = ["战术风衣", "学院制服", "机能夹克", "古典长袍", "街头套装", "礼服", "旅行装", "实验服"]
ART_STYLE_OPTIONS = ["动漫", "写实", "油画", "赛博霓虹", "水彩", "像素", "黑白漫画", "电影海报"]


@dataclass
class Character:
    name: str
    profile: str
    motivations: List[str] = field(default_factory=list)
    relationships: Dict[str, str] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)
    image_path: str = ""


@dataclass
class VolumePlan:
    name: str
    outline: str
    chapter_start: int
    chapter_end: int


@dataclass
class NovelState:
    title: str
    genre: str
    premise: str
    total_chapters: int
    words_per_chapter: int
    style_guide: str
    world_bible: str
    synopsis: str = ""
    volumes: List[VolumePlan] = field(default_factory=list)
    chapter_summaries: List[str] = field(default_factory=list)
    timeline_events: List[str] = field(default_factory=list)
    characters: List[Character] = field(default_factory=list)
    setup_notes: str = ""
    art_style: str = ""
    token_usage: Dict[str, Any] = field(default_factory=dict)
    reference_file: str = ""
    reference_summary: str = ""
    review_checkpoints: List[Dict[str, Any]] = field(default_factory=list)
    pending_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            **asdict(self),
            "characters": [asdict(c) for c in self.characters],
            "volumes": [asdict(v) for v in self.volumes],
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "NovelState":
        return NovelState(
            title=data.get("title", ""),
            genre=data.get("genre", ""),
            premise=data.get("premise", ""),
            total_chapters=data.get("total_chapters", 100),
            words_per_chapter=data.get("words_per_chapter", 3000),
            style_guide=data.get("style_guide", ""),
            world_bible=data.get("world_bible", ""),
            synopsis=data.get("synopsis", ""),
            volumes=[VolumePlan(**v) for v in data.get("volumes", [])],
            chapter_summaries=data.get("chapter_summaries", []),
            timeline_events=data.get("timeline_events", []),
            characters=[Character(**c) for c in data.get("characters", [])],
            setup_notes=data.get("setup_notes", ""),
            art_style=data.get("art_style", ""),
            token_usage=data.get("token_usage", {}),
            reference_file=data.get("reference_file", ""),
            reference_summary=data.get("reference_summary", ""),
            review_checkpoints=data.get("review_checkpoints", []),
            pending_review=data.get("pending_review", False),
        )


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 180) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.8) -> str:
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps({"model": self.model, "temperature": temperature, "messages": messages}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            parsed = json.loads(resp.read().decode("utf-8"))
        return parsed["choices"][0]["message"]["content"]


class NovelGenerator:
    def __init__(self, client: Optional[LLMClient], state_path: Path, output_dir: Path, assets_dir: Path) -> None:
        self.client = client
        self.state_path = state_path
        self.setup_path = state_path.with_name("novel_setup.json")
        self.output_dir = output_dir
        self.assets_dir = assets_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def save_state(self, state: NovelState) -> None:
        self.state_path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        # lightweight heuristic for Chinese/English mixed text
        return max(1, len((text or "").strip()) // 4)

    def _track_tokens(self, state: NovelState, stage: str, prompt_text: str, completion_text: str) -> None:
        usage = state.token_usage or {}
        usage.setdefault("prompt_tokens", 0)
        usage.setdefault("completion_tokens", 0)
        usage.setdefault("total_tokens", 0)
        usage.setdefault("by_stage", {})
        usage["by_stage"].setdefault(stage, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})

        p = self._estimate_tokens(prompt_text)
        c = self._estimate_tokens(completion_text)
        t = p + c
        usage["prompt_tokens"] += p
        usage["completion_tokens"] += c
        usage["total_tokens"] += t
        usage["by_stage"][stage]["prompt_tokens"] += p
        usage["by_stage"][stage]["completion_tokens"] += c
        usage["by_stage"][stage]["total_tokens"] += t
        state.token_usage = usage

    def load_state(self) -> NovelState:
        return NovelState.from_dict(json.loads(self.state_path.read_text(encoding="utf-8")))

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
        setup_notes: str = "",
        art_style: str = "",
        synopsis: str = "",
        volumes: Optional[List[VolumePlan]] = None,
        reference_file: str = "",
        reference_summary: str = "",
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
            setup_notes=setup_notes,
            art_style=art_style,
            synopsis=synopsis,
            volumes=volumes or [],
            reference_file=reference_file,
            reference_summary=reference_summary,
        )
        self.save_state(state)
        return state

    def _read_reference_text(self, reference_file: str) -> str:
        path = Path(reference_file)
        if not path.exists() or not path.is_file():
            return ""
        suffix = path.suffix.lower()
        try:
            if suffix == ".txt":
                return path.read_text(encoding="utf-8", errors="ignore")
            if suffix == ".docx":
                with zipfile.ZipFile(path, "r") as zf:
                    with zf.open("word/document.xml") as fp:
                        xml_data = fp.read()
                root = ET.fromstring(xml_data)
                texts = [el.text for el in root.iter() if el.tag.endswith("}t") and el.text]
                return "\n".join(texts)
        except Exception:
            return ""
        return ""

    def _fast_local_reference_summary(self, content: str, max_chars: int = 4000) -> str:
        content = (content or "").strip()
        if not content:
            return ""
        head = content[: max_chars // 2]
        tail = content[-max_chars // 2 :] if len(content) > max_chars else ""
        merged = (head + "\n...\n" + tail).strip() if tail else head
        lines = [ln.strip() for ln in merged.splitlines() if ln.strip()]
        bullet = "\n".join(f"- {ln[:120]}" for ln in lines[:18])
        return f"参考文本快速摘要（本地提炼）:\n{bullet}"

    def _consistency_pack(self, state: NovelState) -> str:
        summaries = "\n".join(f"- {s}" for s in state.chapter_summaries[-5:]) or "- 无"
        timeline = "\n".join(f"- {e}" for e in state.timeline_events[-15:]) or "- 无"
        chars = "\n".join(
            f"- {c.name}: {c.profile}; 设定:{c.details}; 动机:{', '.join(c.motivations) or '未设置'}"
            for c in state.characters
        ) or "- 无"
        volume_lines = "\n".join(
            f"- {v.name}（第{v.chapter_start}-{v.chapter_end}章）: {v.outline}" for v in state.volumes
        ) or "- 无"
        return textwrap.dedent(
            f"""
            【作品信息】
            标题：{state.title}
            类型：{state.genre}
            核心设定：{state.premise}
            总纲：{state.synopsis or '无'}
            风格要求：{state.style_guide}
            设定补充：{state.setup_notes or '无'}
            参考风格摘要：{state.reference_summary or '无'}

            【分卷大纲】
            {volume_lines}

            【世界观圣经】
            {state.world_bible}

            【角色圣经】
            {chars}

            【最近章节摘要】
            {summaries}

            【关键时间线】
            {timeline}
            """
        ).strip()

    def _mock_chapter(self, state: NovelState, chapter_no: int) -> str:
        volume_hint = next((v for v in state.volumes if v.chapter_start <= chapter_no <= v.chapter_end), None)
        vline = f"当前卷《{volume_hint.name}》：{volume_hint.outline}" if volume_hint else "当前卷推进主线冲突。"
        return textwrap.dedent(
            f"""
            第{chapter_no}章

            夜色压在城墙上，主角小队围绕“{state.premise}”展开新一轮调查。{vline}
            在行动中，队伍内部出现分歧：一方主张立即追击线索，另一方强调先验证情报真伪。
            主角在权衡后选择承担风险，推动剧情进入下一阶段，同时暴露了新的代价与悬念。
            章节结尾抛出新的信息差：看似可靠的盟友可能隐瞒了关键事实。
            """
        ).strip()

    def _random_title(self, genre: str) -> str:
        a = ["星海", "暗潮", "长夜", "边境", "群星", "裂隙", "旧城", "终焰", "迷航", "深渊"]
        b = ["回响", "纪元", "余烬", "之门", "契约", "档案", "迷局", "旅人", "誓约", "风暴"]
        return f"{random.choice(a)}{random.choice(b)}·{genre}"

    def _random_synopsis(self, state: NovelState) -> str:
        return f"在{state.genre}背景下，主角群围绕“{state.premise}”展开长期对抗，历经背叛、同盟与真相揭示，最终改变世界秩序。"

    def _ai_generate_json(self, prompt: str) -> Dict[str, Any]:
        if not self.client:
            return {}
        raw = self.client.chat([
            {"role": "system", "content": "你是小说策划编辑，仅输出 JSON。"},
            {"role": "user", "content": prompt},
        ], temperature=0.5)
        try:
            return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        except Exception:
            return {}

    def ensure_outline(self, state: NovelState) -> NovelState:
        setup = {}
        if self.setup_path.exists():
            setup = json.loads(self.setup_path.read_text(encoding="utf-8"))
        title_mode = setup.get("title_mode", "manual")
        synopsis_mode = setup.get("synopsis_mode", "manual")
        volumes_mode = setup.get("volumes_mode", "manual")

        if title_mode != "manual" or not state.title.strip():
            if title_mode == "ai" and self.client:
                prompt = f"根据类型{state.genre}和设定{state.premise}生成小说名，返回{{\"title\":\"...\"}}"
                payload = self._ai_generate_json(prompt)
                state.title = payload.get("title", "") or self._random_title(state.genre)
                self._track_tokens(state, "title_generation", prompt, json.dumps(payload, ensure_ascii=False))
            else:
                state.title = self._random_title(state.genre)

        if synopsis_mode != "manual" or not state.synopsis.strip():
            if synopsis_mode == "ai" and self.client:
                prompt = f"根据标题《{state.title}》和设定{state.premise}生成小说总纲简介(200字内)，返回{{\"synopsis\":\"...\"}}"
                payload = self._ai_generate_json(prompt)
                state.synopsis = payload.get("synopsis", "") or self._random_synopsis(state)
                self._track_tokens(state, "synopsis_generation", prompt, json.dumps(payload, ensure_ascii=False))
            else:
                state.synopsis = self._random_synopsis(state)

        if volumes_mode != "manual" or not state.volumes:
            if volumes_mode == "ai" and self.client:
                prompt = (
                    f"给小说《{state.title}》生成分卷规划，共{setup.get('volume_count', 4)}卷，返回"
                    "{\"volumes\":[{\"name\":\"\",\"outline\":\"\"},...]}"
                )
                payload = self._ai_generate_json(prompt)
                raw = payload.get("volumes", []) if isinstance(payload.get("volumes", []), list) else []
                self._track_tokens(state, "volume_generation", prompt, json.dumps(payload, ensure_ascii=False))
            else:
                raw = []
            if not raw:
                count = int(setup.get("volume_count", 4))
                raw = [{"name": f"第{i+1}卷", "outline": f"围绕核心冲突“{state.premise}”推进，完成阶段性反转。"} for i in range(count)]
            state.volumes = build_volume_plan(state.total_chapters, raw)

        self.save_state(state)
        return state

    def generate_one_chapter(self, state: NovelState, chapter_no: int) -> str:
        if not self.client:
            return self._mock_chapter(state, chapter_no)
        prompt = textwrap.dedent(
            f"""
            {self._consistency_pack(state)}

            写第{chapter_no}章，约{state.words_per_chapter}字。
            要求：推进主线和关系线，结尾留下钩子，只输出正文。
            """
        ).strip()
        completion = self.client.chat([
            {"role": "system", "content": "你是长篇小说总编剧，需严格连续性。"},
            {"role": "user", "content": prompt},
        ], temperature=0.85).strip()
        self._track_tokens(state, "chapter_generation", prompt, completion)
        return completion

    def summarize_chapter(self, chapter_text: str) -> Dict[str, Any]:
        if not self.client:
            short = (chapter_text or "").replace("\n", " ").strip()
            return {
                "summary": (short[:120] + "...") if len(short) > 120 else short,
                "timeline_events": ["小队推进主线调查", "主角做出高风险决策", "章节结尾留下新悬念"],
                "character_updates": {"主角": "从谨慎转向主动出击"},
            }
        prompt = f"返回 JSON：summary,timeline_events(<=5),character_updates。正文：{chapter_text}"
        raw = self.client.chat([
            {"role": "system", "content": "你是连续性编辑，仅输出 JSON。"},
            {"role": "user", "content": prompt},
        ], temperature=0.2)
        # state will be tracked in run loop where state is accessible
        try:
            return json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
        except Exception:
            return {"summary": "", "timeline_events": [], "character_updates": {}}

    def build_chapter_outline(self, chapter_no: int, meta: Dict[str, Any]) -> str:
        summary = str(meta.get("summary", "")).strip() or "（无摘要）"
        events = meta.get("timeline_events", []) if isinstance(meta.get("timeline_events"), list) else []
        updates = meta.get("character_updates", {}) if isinstance(meta.get("character_updates"), dict) else {}
        event_lines = "\n".join(f"- {e}" for e in events[:5]) or "- （无）"
        update_lines = "\n".join(f"- {k}: {v}" for k, v in updates.items()) or "- （无）"
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

    def run(self, start_chapter: int = 1) -> None:
        self.run_with_controls(start_chapter=start_chapter, review_interval=10, auto_continue_after_review=False)

    def run_with_controls(self, start_chapter: int = 1, review_interval: int = 10, auto_continue_after_review: bool = False) -> None:
        state = self.ensure_outline(self.load_state())
        for chapter_no in range(start_chapter, state.total_chapters + 1):
            f = self.output_dir / f"chapter_{chapter_no:04d}.md"
            if f.exists():
                continue
            chapter = self.generate_one_chapter(state, chapter_no)
            meta = self.summarize_chapter(chapter)
            self._track_tokens(state, "chapter_summary", chapter, json.dumps(meta, ensure_ascii=False))
            f.write_text(f"{self.build_chapter_outline(chapter_no, meta)}\n\n---\n\n{chapter}\n", encoding="utf-8")
            state.chapter_summaries.append(f"第{chapter_no}章：{meta.get('summary','')}")
            for e in (meta.get("timeline_events") or [])[:5]:
                state.timeline_events.append(f"第{chapter_no}章：{e}")

            if review_interval > 0 and chapter_no % review_interval == 0:
                suggestion = self._build_next_plot_suggestion(state, chapter_no)
                state.review_checkpoints.append({
                    "chapter": chapter_no,
                    "next_plot_suggestion": suggestion,
                    "created_at": int(time.time()),
                })
                state.pending_review = True
                review_file = self.state_path.with_name(f"review_after_chapter_{chapter_no:04d}.md")
                review_file.write_text(
                    f"# 第{chapter_no}章后审阅建议\n\n{suggestion}\n\n是否继续生成由你决定。",
                    encoding="utf-8",
                )
                self.save_state(state)
                if not auto_continue_after_review:
                    print(f"[REVIEW] 已生成审阅建议：{review_file}，请审阅后再执行 run --start {chapter_no+1}")
                    return
                state.pending_review = False
            self.save_state(state)
            time.sleep(0.1)

    def _build_next_plot_suggestion(self, state: NovelState, chapter_no: int) -> str:
        recent = "\n".join(state.chapter_summaries[-8:])
        prompt = textwrap.dedent(
            f"""
            当前到第{chapter_no}章。
            小说总纲：{state.synopsis}
            最近摘要：{recent}
            请给出接下来10章的剧情建议（分点），用于人类审阅决定是否继续生成。
            """
        ).strip()
        if self.client:
            try:
                out = self.client.chat([
                    {"role": "system", "content": "你是长篇小说策划编辑。"},
                    {"role": "user", "content": prompt},
                ], temperature=0.5)
                self._track_tokens(state, "review_suggestion", prompt, out)
                return out.strip()
            except Exception:
                pass
        return "\n".join([
            "1) 强化主角目标与代价；",
            "2) 推进一条卷内核心冲突并完成阶段反转；",
            "3) 为下一卷埋设新的信息差与悬念。",
        ])


def maybe_int(raw: str, default: int) -> int:
    try:
        return int(raw)
    except Exception:
        return default


def parse_character_line(line: str) -> Dict[str, Any]:
    p = [x.strip() for x in line.split("|")]
    return {
        "name": p[0] if len(p) > 0 else "",
        "role": p[1] if len(p) > 1 else "",
        "gender": p[2] if len(p) > 2 else "",
        "height_cm": maybe_int(p[3], 170) if len(p) > 3 else 170,
        "weight_kg": maybe_int(p[4], 60) if len(p) > 4 else 60,
        "outfit": p[5] if len(p) > 5 else "",
        "personality": p[6] if len(p) > 6 else "",
        "motivations": [m.strip() for m in (p[7] if len(p) > 7 else "").split(",") if m.strip()],
    }


def random_character(index: int) -> Dict[str, Any]:
    sur = ["林", "苏", "周", "顾", "程", "白", "夏", "沈", "陈", "许"]
    names = ["策", "岚", "曜", "宁", "澜", "舟", "棠", "凛", "弦", "芜"]
    return {
        "name": random.choice(sur) + random.choice(names) + str(index),
        "role": random.choice(ROLE_OPTIONS),
        "gender": random.choice(GENDER_OPTIONS),
        "height_cm": random.randint(155, 192),
        "weight_kg": random.randint(45, 90),
        "outfit": random.choice(OUTFIT_OPTIONS),
        "personality": random.choice(PERSONALITY_OPTIONS),
        "motivations": ["寻找真相", "守护重要之人"],
    }


def blend_character(seed: Dict[str, Any], level: str, index: int) -> Dict[str, Any]:
    base = random_character(index)
    if level == "full":
        return base
    if level == "none":
        return {**base, **{k: v for k, v in seed.items() if v not in ("", [], None)}}
    merged = base.copy()
    for k, v in seed.items():
        if v not in ("", [], None) and random.random() < 0.6:
            merged[k] = v
    return merged


def render_character_svg(char: Dict[str, Any], art_style: str, out_path: Path) -> None:
    hue = abs(hash(char.get("name", "x") + art_style)) % 360
    svg = f"""<svg xmlns='http://www.w3.org/2000/svg' width='768' height='1024'>
<rect width='100%' height='100%' fill='hsl({hue},65%,35%)'/>
<text x='48' y='100' font-size='46' fill='white'>{char.get('name','')}</text>
<text x='48' y='152' font-size='24' fill='white'>定位: {char.get('role','')}</text>
<text x='48' y='190' font-size='24' fill='white'>性别: {char.get('gender','')}</text>
<text x='48' y='228' font-size='24' fill='white'>身高/体重: {char.get('height_cm','')}cm / {char.get('weight_kg','')}kg</text>
<text x='48' y='266' font-size='24' fill='white'>服装: {char.get('outfit','')}</text>
<text x='48' y='304' font-size='24' fill='white'>性格: {char.get('personality','')}</text>
<text x='48' y='342' font-size='24' fill='white'>风格: {art_style}</text>
</svg>"""
    out_path.write_text(svg, encoding="utf-8")


def build_volume_plan(total_chapters: int, raw_volumes: List[Dict[str, Any]]) -> List[VolumePlan]:
    if not raw_volumes:
        raw_volumes = [{"name": "第一卷", "outline": "主线开局"}]
    n = len(raw_volumes)
    base = total_chapters // n
    rem = total_chapters % n
    plans: List[VolumePlan] = []
    start = 1
    for i, rv in enumerate(raw_volumes):
        size = base + (1 if i < rem else 0)
        end = start + max(size - 1, 0)
        plans.append(VolumePlan(name=str(rv.get("name", f"第{i+1}卷")), outline=str(rv.get("outline", "")), chapter_start=start, chapter_end=end))
        start = end + 1
    return plans


def parse_volumes(raw: str) -> List[Dict[str, str]]:
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = [p.strip() for p in line.split("|", 1)]
        rows.append({"name": parts[0], "outline": parts[1] if len(parts) > 1 else ""})
    return rows


def setup_novel(args: argparse.Namespace, generator: NovelGenerator) -> None:
    random.seed(args.seed)

    if args.title_mode == "manual" and not args.title:
        raise SystemExit("title_mode=manual 时必须提供 --title")

    title = args.title or ""
    if args.title_mode == "random":
        title = generator._random_title(args.genre)
    elif args.title_mode == "ai":
        if generator.client:
            payload = generator._ai_generate_json(f"请生成{args.genre}小说名，返回{{\"title\":\"...\"}}")
            title = payload.get("title", "") or generator._random_title(args.genre)
        else:
            title = generator._random_title(args.genre)

    raw_characters = [parse_character_line(line) for line in args.characters.splitlines() if line.strip()]
    while len(raw_characters) < args.character_count:
        raw_characters.append({})

    image_dir = generator.assets_dir / "character_images"
    image_dir.mkdir(parents=True, exist_ok=True)
    selected: List[Character] = []
    for i in range(args.character_count):
        c = blend_character(raw_characters[i], args.random_level, i + 1)
        img = image_dir / f"{i+1:02d}_{c['name']}.svg"
        render_character_svg(c, args.art_style, img)
        selected.append(
            Character(
                name=c["name"],
                profile=f"{c['role']}，{c['gender']}，{c['height_cm']}cm/{c['weight_kg']}kg，常穿{c['outfit']}，性格{c['personality']}",
                motivations=c.get("motivations", []),
                details={k: c[k] for k in ["role", "gender", "height_cm", "weight_kg", "outfit", "personality"]},
                image_path=str(img),
            )
        )

    ref_text = generator._read_reference_text(args.reference_file) if args.reference_file else ""
    if ref_text and len(ref_text) > 12000:
        ref_summary = generator._fast_local_reference_summary(ref_text)
    elif ref_text:
        ref_summary = generator._fast_local_reference_summary(ref_text)
    else:
        ref_summary = ""

    state = generator.create_initial_state(
        title=title,
        genre=args.genre,
        premise=args.premise,
        total_chapters=args.total_chapters,
        words_per_chapter=args.words_per_chapter,
        style_guide=args.style_guide,
        world_bible=args.world_bible,
        characters=selected,
        setup_notes=(
            f"叙事侧重:{args.narrative_focus}; 冲突强度:{args.conflict_level}; 感情权重:{args.emotion_weight}; "
            f"标题模式:{args.title_mode}; 总纲模式:{args.synopsis_mode}; 卷纲模式:{args.volumes_mode}"
        ),
        art_style=args.art_style,
        synopsis=args.synopsis if args.synopsis_mode == "manual" else "",
        volumes=build_volume_plan(args.total_chapters, parse_volumes(args.volumes)) if args.volumes_mode == "manual" else [],
        reference_file=args.reference_file,
        reference_summary=ref_summary,
    )

    setup_json = {
        "title_mode": args.title_mode,
        "synopsis_mode": args.synopsis_mode,
        "volumes_mode": args.volumes_mode,
        "volume_count": args.volume_count,
        "title": state.title,
        "synopsis": args.synopsis,
        "volumes": parse_volumes(args.volumes),
        "genre": args.genre,
        "premise": args.premise,
        "art_style": args.art_style,
        "random_level": args.random_level,
        "character_count": args.character_count,
        "narrative_focus": args.narrative_focus,
        "conflict_level": args.conflict_level,
        "emotion_weight": args.emotion_weight,
        "characters": [asdict(c) for c in selected],
        "reference_file": args.reference_file,
        "reference_summary": ref_summary,
    }
    generator.setup_path.write_text(json.dumps(setup_json, ensure_ascii=False, indent=2), encoding="utf-8")
    generator.save_state(generator.ensure_outline(state))
    print(f"[OK] 设定完成：{generator.setup_path} / {generator.state_path}")


def parse_characters(raw: str) -> List[Character]:
    out: List[Character] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        p = [x.strip() for x in line.split("|")]
        out.append(Character(name=p[0], profile=p[1] if len(p) > 1 else "", motivations=(p[2].split(",") if len(p) > 2 else [])))
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Long-form novel generator")
    parser.add_argument("--base-url", default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--api-key", default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--state", default="novel_state.json")
    parser.add_argument("--output", default="novel_output")
    parser.add_argument("--assets", default="assets")
    sub = parser.add_subparsers(dest="cmd", required=True)

    setup = sub.add_parser("setup", help="生成前设定")
    setup.add_argument("--base-url", dest="setup_base_url", default=None)
    setup.add_argument("--api-key", dest="setup_api_key", default=None)
    setup.add_argument("--model", dest="setup_model", default=None)
    setup.add_argument("--state", dest="setup_state", default=None)
    setup.add_argument("--output", dest="setup_output", default=None)
    setup.add_argument("--assets", dest="setup_assets", default=None)
    setup.add_argument("--title", default="")
    setup.add_argument("--title-mode", choices=["manual", "ai", "random"], default="manual")
    setup.add_argument("--genre", default="科幻", choices=GENRE_OPTIONS)
    setup.add_argument("--premise", required=True)
    setup.add_argument("--world-bible", required=True)
    setup.add_argument("--synopsis", default="")
    setup.add_argument("--synopsis-mode", choices=["manual", "ai", "random"], default="manual")
    setup.add_argument("--volumes", default="", help="每行: 卷名|卷纲")
    setup.add_argument("--volumes-mode", choices=["manual", "ai", "random"], default="manual")
    setup.add_argument("--volume-count", type=int, default=4)
    setup.add_argument("--total-chapters", type=int, default=300)
    setup.add_argument("--words-per-chapter", type=int, default=3500)
    setup.add_argument("--style-guide", default="第三人称、多线叙事、重视伏笔回收")
    setup.add_argument("--art-style", default="电影海报", choices=ART_STYLE_OPTIONS)
    setup.add_argument("--character-count", type=int, default=4)
    setup.add_argument("--random-level", choices=["none", "partial", "full"], default="partial")
    setup.add_argument("--narrative-focus", choices=["剧情", "人物", "世界观", "悬疑"], default="剧情")
    setup.add_argument("--conflict-level", choices=["低", "中", "高"], default="中")
    setup.add_argument("--emotion-weight", choices=["低", "中", "高"], default="中")
    setup.add_argument("--seed", type=int, default=42)
    setup.add_argument("--characters", default="", help="每行: name|role|gender|height|weight|outfit|personality|mot1,mot2")
    setup.add_argument("--reference-file", default="", help="参考文档路径，支持 txt/docx")

    init = sub.add_parser("init", help="兼容旧初始化")
    init.add_argument("--title", required=True)
    init.add_argument("--genre", required=True)
    init.add_argument("--premise", required=True)
    init.add_argument("--total-chapters", type=int, default=300)
    init.add_argument("--words-per-chapter", type=int, default=3500)
    init.add_argument("--style-guide", default="第三人称、多线叙事、重视伏笔回收")
    init.add_argument("--world-bible", required=True)
    init.add_argument("--characters", default="")

    run = sub.add_parser("run", help="生成章节")
    run.add_argument("--base-url", dest="run_base_url", default=None)
    run.add_argument("--api-key", dest="run_api_key", default=None)
    run.add_argument("--model", dest="run_model", default=None)
    run.add_argument("--state", dest="run_state", default=None)
    run.add_argument("--output", dest="run_output", default=None)
    run.add_argument("--assets", dest="run_assets", default=None)
    run.add_argument("--start", type=int, default=1)
    run.add_argument("--review-interval", type=int, default=10, help="每多少章触发一次审阅建议，0 表示关闭")
    run.add_argument("--auto-continue-after-review", action="store_true", help="触发审阅后自动继续生成")

    args = parser.parse_args()
    active_base_url = args.base_url
    active_api_key = args.api_key
    active_model = args.model
    active_state = args.state
    active_output = args.output
    active_assets = args.assets
    if args.cmd == "setup":
        active_base_url = args.setup_base_url or active_base_url
        active_api_key = args.setup_api_key if args.setup_api_key is not None else active_api_key
        active_model = args.setup_model or active_model
        active_state = args.setup_state or active_state
        active_output = args.setup_output or active_output
        active_assets = args.setup_assets or active_assets
    elif args.cmd == "run":
        active_base_url = args.run_base_url or active_base_url
        active_api_key = args.run_api_key if args.run_api_key is not None else active_api_key
        active_model = args.run_model or active_model
        active_state = args.run_state or active_state
        active_output = args.run_output or active_output
        active_assets = args.run_assets or active_assets

    client = LLMClient(active_base_url, active_api_key, active_model) if active_api_key else None
    gen = NovelGenerator(client, Path(active_state), Path(active_output), Path(active_assets))

    if args.cmd == "setup":
        setup_novel(args, gen)
    elif args.cmd == "init":
        gen.create_initial_state(args.title, args.genre, args.premise, args.total_chapters, args.words_per_chapter, args.style_guide, args.world_bible, parse_characters(args.characters))
        print(f"[OK] 初始化完成：{args.state}")
    elif args.cmd == "run":
        gen.run_with_controls(
            start_chapter=args.start,
            review_interval=args.review_interval,
            auto_continue_after_review=args.auto_continue_after_review,
        )
        print("[OK] 生成完成")


if __name__ == "__main__":
    main()
