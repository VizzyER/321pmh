#!/usr/bin/env python3
"""Web UI for browsing generated novels and chapter details.

Directory convention (library root):
- each novel project is a folder containing `novel_state.json` and `novel_output/chapter_*.md`

Routes:
- /                        : list novels
- /novel/<id>              : list chapters with summary and '详细' button
- /novel/<id>/chapter/<no> : show chapter full content
"""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse
from wsgiref.simple_server import make_server


CHAPTER_FILE_RE = re.compile(r"^chapter_(\d{4})\.md$")
SUMMARY_RE = re.compile(r"\*\*剧情摘要\*\*\s*(.+?)(?:\n\n\*\*|\n---\n|$)", re.S)


@dataclass
class NovelProject:
    novel_id: str
    project_dir: Path
    title: str


@dataclass
class ChapterRecord:
    chapter_no: int
    file_path: Path
    summary: str


def _read_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def list_novels(library_root: Path) -> List[NovelProject]:
    novels: List[NovelProject] = []

    # treat library root itself as a novel project when files are present
    root_state = library_root / "novel_state.json"
    root_output = library_root / "novel_output"
    if root_state.exists() and root_output.exists():
        try:
            root_meta = _read_json(root_state)
            root_title = str(root_meta.get("title", library_root.name)).strip() or library_root.name
        except Exception:
            root_title = library_root.name
        novels.append(NovelProject(novel_id="__root__", project_dir=library_root, title=root_title))

    for folder in sorted([p for p in library_root.iterdir() if p.is_dir()]):
        state_path = folder / "novel_state.json"
        output_dir = folder / "novel_output"
        if not state_path.exists() or not output_dir.exists():
            continue
        try:
            state = _read_json(state_path)
            title = str(state.get("title", folder.name)).strip() or folder.name
        except Exception:
            title = folder.name
        novels.append(NovelProject(novel_id=folder.name, project_dir=folder, title=title))
    return novels


def extract_summary_from_chapter(raw_text: str) -> str:
    m = SUMMARY_RE.search(raw_text)
    if not m:
        return "（未提取到摘要）"
    summary = re.sub(r"\s+", " ", m.group(1)).strip()
    return summary or "（未提取到摘要）"


def extract_full_content(raw_text: str) -> str:
    marker = "\n---\n"
    if marker in raw_text:
        return raw_text.split(marker, 1)[1].strip()
    return raw_text.strip()


def list_chapters(project_dir: Path) -> List[ChapterRecord]:
    output_dir = project_dir / "novel_output"
    rows: List[ChapterRecord] = []
    for file_path in sorted(output_dir.iterdir()):
        m = CHAPTER_FILE_RE.match(file_path.name)
        if not m:
            continue
        raw_text = file_path.read_text(encoding="utf-8")
        rows.append(
            ChapterRecord(
                chapter_no=int(m.group(1)),
                file_path=file_path,
                summary=extract_summary_from_chapter(raw_text),
            )
        )
    return rows


def render_page(title: str, body: str) -> bytes:
    doc = f"""<!doctype html>
<html lang=\"zh-CN\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\" />
<title>{html.escape(title)}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 24px; }}
a {{ text-decoration: none; color: #0b57d0; }}
.card {{ border: 1px solid #ddd; border-radius: 10px; padding: 14px; margin-bottom: 10px; }}
.btn {{ display:inline-block; margin-top:8px; padding:6px 10px; border:1px solid #0b57d0; border-radius: 8px; }}
pre {{ white-space: pre-wrap; background:#fafafa; border:1px solid #eee; padding: 12px; border-radius:8px; }}
small {{ color:#666; }}
</style>
</head>
<body>
{body}
</body>
</html>"""
    return doc.encode("utf-8")


def app_factory(library_root: Path):
    def app(environ, start_response):
        path = urlparse(environ.get("PATH_INFO", "/")).path

        if path == "/":
            novels = list_novels(library_root)
            items = "\n".join(
                f"<div class='card'><b>{html.escape(n.title)}</b><br><small>{html.escape(n.novel_id)}</small><br>"
                f"<a class='btn' href='/novel/{html.escape(n.novel_id)}'>进入小说</a></div>"
                for n in novels
            ) or "<p>暂无小说，请先运行生成器。</p>"
            payload = render_page("小说列表", f"<h1>小说列表</h1>{items}")
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [payload]

        parts = [p for p in path.split("/") if p]
        # /novel/<id>
        if len(parts) == 2 and parts[0] == "novel":
            novel_id = parts[1]
            project_dir = library_root if novel_id == "__root__" else (library_root / novel_id)
            if not project_dir.exists():
                start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
                return ["novel not found".encode("utf-8")]
            chapters = list_chapters(project_dir)
            chapter_items = []
            for ch in chapters:
                chapter_items.append(
                    f"<div class='card'><b>第{ch.chapter_no}章</b><p>{html.escape(ch.summary)}</p>"
                    f"<a class='btn' href='/novel/{html.escape(novel_id)}/chapter/{ch.chapter_no}'>详细</a></div>"
                )
            payload = render_page(
                f"{novel_id} 章节",
                f"<p><a href='/'>← 返回小说列表</a></p><h1>{html.escape(novel_id)} 章节目录</h1>" + "".join(chapter_items),
            )
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [payload]

        # /novel/<id>/chapter/<no>
        if len(parts) == 4 and parts[0] == "novel" and parts[2] == "chapter":
            novel_id = parts[1]
            try:
                chapter_no = int(parts[3])
            except ValueError:
                start_response("400 Bad Request", [("Content-Type", "text/plain; charset=utf-8")])
                return ["invalid chapter number".encode("utf-8")]
            chapter_base = library_root if novel_id == "__root__" else (library_root / novel_id)
            chapter_file = chapter_base / "novel_output" / f"chapter_{chapter_no:04d}.md"
            if not chapter_file.exists():
                start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
                return ["chapter not found".encode("utf-8")]
            raw = chapter_file.read_text(encoding="utf-8")
            detail = html.escape(extract_full_content(raw))
            payload = render_page(
                f"{novel_id} 第{chapter_no}章",
                f"<p><a href='/novel/{html.escape(novel_id)}'>← 返回章节列表</a></p>"
                f"<h1>{html.escape(novel_id)} - 第{chapter_no}章</h1><pre>{detail}</pre>",
            )
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [payload]

        start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
        return ["not found".encode("utf-8")]

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Novel browser Web UI")
    parser.add_argument("--library-root", default=".", help="小说项目根目录，默认当前目录")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    root = Path(args.library_root).resolve()
    if not root.exists():
        raise SystemExit(f"library root not found: {root}")

    app = app_factory(root)
    print(f"[OK] WebUI running at http://{args.host}:{args.port} (library_root={root})")
    with make_server(args.host, args.port, app) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
