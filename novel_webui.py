#!/usr/bin/env python3
"""Web UI for setup + browse novels."""

from __future__ import annotations

import argparse
import html
import json
import mimetypes
import re
import shlex
import time
from pathlib import Path
from typing import Dict, List
from urllib.parse import parse_qs, quote, unquote, urlparse
from wsgiref.simple_server import make_server

CHAPTER_FILE_RE = re.compile(r"^chapter_(\d{4})\.md$")
SUMMARY_RE = re.compile(r"\*\*剧情摘要\*\*\s*(.+?)(?:\n\n\*\*|\n---\n|$)", re.S)


def _read_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def list_novels(library_root: Path) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    if (library_root / "novel_state.json").exists() and (library_root / "novel_output").exists():
        t = _read_json(library_root / "novel_state.json").get("title", library_root.name)
        rows.append({"id": "__root__", "title": str(t)})
    for p in sorted([x for x in library_root.iterdir() if x.is_dir()]):
        if (p / "novel_state.json").exists() and (p / "novel_output").exists():
            t = _read_json(p / "novel_state.json").get("title", p.name)
            rows.append({"id": p.name, "title": str(t)})
    return rows


def extract_summary_from_chapter(raw_text: str) -> str:
    m = SUMMARY_RE.search(raw_text)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else "（未提取到摘要）"


def extract_full_content(raw_text: str) -> str:
    return raw_text.split("\n---\n", 1)[1].strip() if "\n---\n" in raw_text else raw_text.strip()


def list_chapters(project_dir: Path) -> List[Dict]:
    out = []
    for fp in sorted((project_dir / "novel_output").iterdir()):
        m = CHAPTER_FILE_RE.match(fp.name)
        if not m:
            continue
        raw = fp.read_text(encoding="utf-8")
        out.append({"chapter_no": int(m.group(1)), "summary": extract_summary_from_chapter(raw)})
    return out


def render_page(title: str, body: str) -> bytes:
    page_body = f"<div class='container'><div class='header'><div><h1 class='title'>{html.escape(title)}</h1><p class='subtitle'>Long-form Novel Studio</p></div></div>{body}</div>"
    doc = f"""<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'/>
<meta name='viewport' content='width=device-width,initial-scale=1'/><title>{html.escape(title)}</title>
<style>
:root{{--bg:#f5f7fb;--card:#ffffff;--line:#e6eaf2;--text:#1f2937;--muted:#667085;--brand:#3b82f6;--brand-weak:#eff6ff;}}
*{{box-sizing:border-box}}
body{{font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;background:linear-gradient(180deg,#f8faff 0%,#f5f7fb 45%,#f7f8fb 100%);color:var(--text);}}
.container{{max-width:1200px;margin:0 auto;padding:22px;}}
.header{{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;gap:10px;}}
.title{{font-size:28px;font-weight:750;letter-spacing:.2px;margin:0;}}
.subtitle{{margin:2px 0 0;color:var(--muted);font-size:13px;}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px 16px;margin:10px 0;box-shadow:0 4px 20px rgba(31,41,55,.04);}}
.btn{{display:inline-block;padding:8px 13px;border-radius:10px;border:1px solid var(--brand);background:var(--brand-weak);color:var(--brand);text-decoration:none;margin-right:8px;font-weight:600;font-size:13px;}}
.btn:hover{{filter:brightness(.97)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;}}
input,select,textarea{{width:100%;padding:9px 10px;border:1px solid #d8deea;border-radius:10px;background:#fff;}}
input:focus,select:focus,textarea:focus{{outline:none;border-color:#9cc1ff;box-shadow:0 0 0 3px rgba(59,130,246,.12)}}
label{{font-size:13px;color:#344054;display:block;margin:8px 0;}}
pre{{white-space:pre-wrap;background:#fbfcff;border:1px solid #edf1f7;padding:12px;border-radius:10px;line-height:1.55;}}
img{{max-width:100%;border-radius:10px;border:1px solid #dce3f1;}}
table{{width:100%;border-collapse:collapse;border:1px solid #e7ecf5;background:#fff;border-radius:10px;overflow:hidden;}}
th,td{{padding:8px 10px;border-bottom:1px solid #edf1f8;text-align:left;font-size:13px;}}
th{{background:#f8fbff;color:#3a4a62;}}
</style></head><body>{page_body}</body></html>"""
    return doc.encode("utf-8")


def build_text_image_svg(text: str, style: str = "电影海报") -> str:
    text = (text or "空内容").strip()
    preview = text[:180]
    hue = abs(hash(preview + style)) % 360
    safe_preview = html.escape(preview)
    safe_style = html.escape(style)
    return f"""<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720'>
<defs><linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>
<stop offset='0%' stop-color='hsl({hue},70%,35%)'/><stop offset='100%' stop-color='hsl({(hue+45)%360},68%,20%)'/>
</linearGradient></defs>
<rect width='100%' height='100%' fill='url(#bg)'/>
<rect x='56' y='56' width='1168' height='608' rx='24' fill='rgba(255,255,255,0.08)' stroke='rgba(255,255,255,0.25)'/>
<text x='88' y='120' font-size='42' fill='white' font-weight='700'>片段意境图</text>
<text x='88' y='168' font-size='24' fill='white'>风格: {safe_style}</text>
<foreignObject x='88' y='210' width='1100' height='390'>
  <div xmlns='http://www.w3.org/1999/xhtml' style='font-size:28px;line-height:1.45;color:white;font-family:Arial,sans-serif;'>
    {safe_preview}
  </div>
</foreignObject>
<text x='88' y='642' font-size='18' fill='rgba(255,255,255,0.85)'>Generated from selected chapter text</text>
</svg>"""


def generate_image_for_excerpt(project_dir: Path, chapter_no: int, excerpt: str, style: str) -> Path:
    img_dir = project_dir / "generated_images"
    img_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    fp = img_dir / f"chapter_{chapter_no:04d}_{ts}.svg"
    fp.write_text(build_text_image_svg(excerpt, style), encoding="utf-8")
    return fp


def parse_post(environ) -> Dict[str, str]:
    try:
        size = int(environ.get("CONTENT_LENGTH", "0") or "0")
    except ValueError:
        size = 0
    raw = environ["wsgi.input"].read(size).decode("utf-8", errors="ignore")
    p = parse_qs(raw)
    return {k: v[0] for k, v in p.items()}


def save_setup_from_form(root: Path, form: Dict[str, str]) -> str:
    project = form.get("project", "my_novel").strip() or "my_novel"
    project_dir = (root / project).resolve()
    if not str(project_dir).startswith(str(root.resolve())):
        raise ValueError("非法项目目录")
    project_dir.mkdir(parents=True, exist_ok=True)

    setup = {
        "base_url": form.get("base_url", "https://api.openai.com/v1"),
        "api_key": form.get("api_key", ""),
        "model": form.get("model", "gpt-4o-mini"),
        "title": form.get("title", ""),
        "title_mode": form.get("title_mode", "manual"),
        "genre": form.get("genre", "科幻"),
        "premise": form.get("premise", ""),
        "world_bible": form.get("world_bible", ""),
        "style_guide": form.get("style_guide", "第三人称、多线叙事"),
        "synopsis": form.get("synopsis", ""),
        "synopsis_mode": form.get("synopsis_mode", "manual"),
        "volumes": form.get("volumes", ""),
        "volumes_mode": form.get("volumes_mode", "manual"),
        "volume_count": int(form.get("volume_count", "4") or "4"),
        "art_style": form.get("art_style", "电影海报"),
        "character_count": int(form.get("character_count", "4") or "4"),
        "random_level": form.get("random_level", "partial"),
        "narrative_focus": form.get("narrative_focus", "剧情"),
        "conflict_level": form.get("conflict_level", "中"),
        "emotion_weight": form.get("emotion_weight", "中"),
        "characters": form.get("characters", ""),
        "reference_file": form.get("reference_file", ""),
        "review_interval": int(form.get("review_interval", "10") or "10"),
        "auto_continue_after_review": form.get("auto_continue_after_review", "") == "on",
    }
    (project_dir / "setup_draft.json").write_text(json.dumps(setup, ensure_ascii=False, indent=2), encoding="utf-8")

    gen = (Path(__file__).resolve().parent / "novel_generator.py").resolve()
    cmd_parts = [
        "python3", str(gen), "setup",
        "--base-url", setup["base_url"],
        "--api-key", setup["api_key"],
        "--model", setup["model"],
        "--title", setup["title"], "--title-mode", setup["title_mode"],
        "--genre", setup["genre"], "--premise", setup["premise"],
        "--world-bible", setup["world_bible"], "--style-guide", setup["style_guide"],
        "--synopsis", setup["synopsis"], "--synopsis-mode", setup["synopsis_mode"],
        "--volumes", setup["volumes"], "--volumes-mode", setup["volumes_mode"],
        "--volume-count", str(setup["volume_count"]),
        "--art-style", setup["art_style"], "--character-count", str(setup["character_count"]),
        "--random-level", setup["random_level"], "--narrative-focus", setup["narrative_focus"],
        "--conflict-level", setup["conflict_level"], "--emotion-weight", setup["emotion_weight"],
        "--characters", setup["characters"],
        "--reference-file", setup["reference_file"],
    ]
    cmd = f"cd {shlex.quote(str(project_dir))} && " + " ".join(shlex.quote(x) for x in cmd_parts)
    (project_dir / "setup_command.sh").write_text(cmd + "\n", encoding="utf-8")

    run_parts = [
        "python3", str(gen), "run",
        "--base-url", setup["base_url"],
        "--api-key", setup["api_key"],
        "--model", setup["model"],
        "--start", "1",
        "--review-interval", str(setup["review_interval"]),
    ]
    if setup["auto_continue_after_review"]:
        run_parts.append("--auto-continue-after-review")
    run_cmd = f"cd {shlex.quote(str(project_dir))} && " + " ".join(shlex.quote(x) for x in run_parts)
    (project_dir / "run_command.sh").write_text(run_cmd + "\n", encoding="utf-8")
    return project


def app_factory(library_root: Path):
    def app(environ, start_response):
        path = urlparse(environ.get("PATH_INFO", "/")).path

        if path.startswith("/static/"):
            target = (library_root / unquote(path[len("/static/"):])).resolve()
            if not str(target).startswith(str(library_root.resolve())) or not target.exists():
                start_response("404 Not Found", [("Content-Type", "text/plain")])
                return [b"not found"]
            start_response("200 OK", [("Content-Type", mimetypes.guess_type(str(target))[0] or "application/octet-stream")])
            return [target.read_bytes()]

        if path == "/setup" and environ.get("REQUEST_METHOD") == "POST":
            try:
                project = save_setup_from_form(library_root, parse_post(environ))
            except Exception as e:
                start_response("400 Bad Request", [("Content-Type", "text/html; charset=utf-8")])
                return [render_page("设定失败", f"<div class='card'>{html.escape(str(e))}</div>")]
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [render_page("设定草稿已保存", f"<h1>设定草稿已保存</h1><div class='card'>项目：{html.escape(project)}<br/>已生成 setup_draft.json、setup_command.sh、run_command.sh。<br/>API 参数已写入命令文件，无需环境变量。</div>")]

        if path == "/setup":
            form = """
            <p><a class='btn' href='/'>← 返回首页</a></p>
            <h1>生成前设定（名称/总纲/卷纲/人物）</h1>
            <form method='post' action='/setup'><div class='grid'>
            <div class='card'>
            <label>项目目录名<input name='project' value='my_novel'/></label>
            <label>API Base URL<input name='base_url' value='https://api.openai.com/v1'/></label>
            <label>API Key<input name='api_key' type='password' value=''/></label>
            <label>Model<input name='model' value='gpt-4o-mini'/></label>
            <label>小说名称<input name='title' value=''/></label>
            <label>名称模式<select name='title_mode'><option value='manual'>手动</option><option value='ai'>AI生成</option><option value='random'>随机</option></select></label>
            <label>类别<select name='genre'><option>科幻</option><option>奇幻</option><option>都市</option><option>悬疑</option><option>历史</option><option>武侠</option><option>赛博朋克</option><option>末日</option><option>言情</option><option>成长</option></select></label>
            <label>总纲（简介）<textarea name='synopsis' rows='4'></textarea></label>
            <label>总纲模式<select name='synopsis_mode'><option value='manual'>手动</option><option value='ai'>AI生成</option><option value='random'>随机</option></select></label>
            <label>卷纲（每行: 卷名|卷纲）<textarea name='volumes' rows='5'>第一卷|主角进入冲突核心并建立同盟
第二卷|同盟破裂并揭露关键阴谋</textarea></label>
            <label>卷纲模式<select name='volumes_mode'><option value='manual'>手动</option><option value='ai'>AI生成</option><option value='random'>随机</option></select></label>
            <label>卷数（AI/随机时有效）<input name='volume_count' type='number' min='1' max='20' value='4'/></label>
            <label>参考文档路径（txt/docx）<input name='reference_file' value=''/></label>
            <label>审阅间隔（每N章）<input name='review_interval' type='number' min='0' max='200' value='10'/></label>
            <label><input type='checkbox' name='auto_continue_after_review'/> 审阅点自动继续生成（不暂停）</label>
            </div>
            <div class='card'>
            <label>核心设定<textarea name='premise' rows='4'>文明在热寂阴影下争夺最后的恒星火种。</textarea></label>
            <label>世界观<textarea name='world_bible' rows='6'>银河被九大环带分割，超光航道由古代引力井维持。</textarea></label>
            <label>写作风格<textarea name='style_guide' rows='3'>第三人称、多线叙事、重视伏笔回收</textarea></label>
            <label>角色模板（每行: name|role|gender|height|weight|outfit|personality|mot1,mot2）
            <textarea name='characters' rows='6'>林策|主角|男|181|72|机能夹克|冷静|寻找父亲,守住火种
苏岚|配角|女|168|52|战术风衣|理性|维持秩序,隐藏真相</textarea></label>
            <label>人物随机程度<select name='random_level'><option>none</option><option selected>partial</option><option>full</option></select></label>
            <label>人物数量<input name='character_count' type='number' min='1' max='30' value='4'/></label>
            <label>叙事侧重<select name='narrative_focus'><option>剧情</option><option>人物</option><option>世界观</option><option>悬疑</option></select></label>
            <label>冲突强度<select name='conflict_level'><option>低</option><option selected>中</option><option>高</option></select></label>
            <label>感情线权重<select name='emotion_weight'><option>低</option><option selected>中</option><option>高</option></select></label>
            <label>人物图风格<select name='art_style'><option>动漫</option><option>写实</option><option>油画</option><option selected>电影海报</option><option>赛博霓虹</option><option>水彩</option></select></label>
            </div></div><p><button class='btn' type='submit'>保存设定草稿</button></p></form>
            """
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [render_page("小说设定", form)]

        if path == "/":
            cards = "".join(
                f"<div class='card'><b>{html.escape(n['title'])}</b><br/><small>{html.escape(n['id'])}</small><br/>"
                f"<a class='btn' href='/novel/{quote(n['id'])}'>进入小说</a></div>" for n in list_novels(library_root)
            ) or "<p>暂无小说。</p>"
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [render_page("小说控制台", f"<h1>小说控制台</h1><p><a class='btn' href='/setup'>+ 新建设定</a></p>{cards}")]

        parts = [p for p in path.split("/") if p]
        if len(parts) == 2 and parts[0] == "novel":
            nid = unquote(parts[1])
            pdir = library_root if nid == "__root__" else (library_root / nid)
            if not pdir.exists():
                start_response("404 Not Found", [("Content-Type", "text/plain")])
                return [b"not found"]
            state = _read_json(pdir / "novel_state.json")
            chapters = list_chapters(pdir)
            vols = state.get("volumes", [])
            vol_html = "".join(
                f"<div class='card'><b>{html.escape(str(v.get('name','')))}</b>（第{v.get('chapter_start','?')}-{v.get('chapter_end','?')}章）<p>{html.escape(str(v.get('outline','')))}</p></div>"
                for v in vols
            ) or "<p>暂无卷纲</p>"
            char_html = ""
            for c in state.get("characters", []):
                img_html = ""
                if c.get("image_path"):
                    try:
                        rel = Path(c["image_path"]).resolve().relative_to(library_root.resolve())
                        img_html = f"<img src='/static/{quote(str(rel))}'/>"
                    except Exception:
                        pass
                char_html += f"<div class='card'><b>{html.escape(str(c.get('name','')))}</b><p>{html.escape(str(c.get('profile','')))}</p>{img_html}</div>"
            ch_html = "".join(
                f"<div class='card'><b>第{c['chapter_no']}章</b><p>{html.escape(c['summary'])}</p><a class='btn' href='/novel/{quote(nid)}/chapter/{c['chapter_no']}'>详细</a></div>"
                for c in chapters
            ) or "<p>暂无章节</p>"

            usage = state.get("token_usage", {}) if isinstance(state.get("token_usage", {}), dict) else {}
            by_stage = usage.get("by_stage", {}) if isinstance(usage.get("by_stage", {}), dict) else {}
            stage_rows = "".join(
                f"<tr><td>{html.escape(str(k))}</td><td>{int(v.get('prompt_tokens',0))}</td><td>{int(v.get('completion_tokens',0))}</td><td>{int(v.get('total_tokens',0))}</td></tr>"
                for k, v in by_stage.items() if isinstance(v, dict)
            )
            token_block = (
                f"<div class='card'><h2>Token 监控（估算）</h2>"
                f"<p><b>Prompt:</b> {int(usage.get('prompt_tokens',0))} | <b>Completion:</b> {int(usage.get('completion_tokens',0))} | <b>Total:</b> {int(usage.get('total_tokens',0))}</p>"
                f"<table border='1' cellpadding='6' cellspacing='0'><tr><th>阶段</th><th>Prompt</th><th>Completion</th><th>Total</th></tr>{stage_rows or '<tr><td colspan=4>暂无</td></tr>'}</table></div>"
            )
            reviews = state.get("review_checkpoints", []) if isinstance(state.get("review_checkpoints", []), list) else []
            review_html = "".join(
                f"<div class='card'><b>第{int(r.get('chapter',0))}章审阅点</b><pre>{html.escape(str(r.get('next_plot_suggestion','')))}</pre></div>"
                for r in reviews[-5:]
            ) or "<p>暂无审阅建议</p>"
            body = (
                f"<p><a class='btn' href='/'>← 返回首页</a></p><h1>{html.escape(str(state.get('title',nid)))}</h1>"
                f"<div class='card'><p><b>类别：</b>{html.escape(str(state.get('genre','')))}</p>"
                f"<p><b>总纲：</b>{html.escape(str(state.get('synopsis','')))}</p>"
                f"<p><b>核心设定：</b>{html.escape(str(state.get('premise','')))}</p>"
                f"<p><b>参考文件：</b>{html.escape(str(state.get('reference_file','')))}</p>"
                f"<p><b>参考摘要：</b>{html.escape(str(state.get('reference_summary','')))}</p></div>"
                f"{token_block}"
                f"<h2>审阅建议（每10章）</h2>{review_html}"
                f"<h2>卷名与卷纲</h2>{vol_html}"
                f"<h2>角色设定与形象</h2><div class='grid'>{char_html or '<p>暂无角色</p>'}</div>"
                f"<h2>章节摘要</h2>{ch_html}"
            )
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [render_page("小说详情", body)]

        if len(parts) == 5 and parts[0] == "novel" and parts[2] == "chapter" and parts[4] == "image" and environ.get("REQUEST_METHOD") == "POST":
            nid = unquote(parts[1])
            try:
                cno = int(parts[3])
            except ValueError:
                start_response("400 Bad Request", [("Content-Type", "text/plain")])
                return [b"invalid chapter"]
            pdir = library_root if nid == "__root__" else (library_root / nid)
            chapter_file = pdir / "novel_output" / f"chapter_{cno:04d}.md"
            if not chapter_file.exists():
                start_response("404 Not Found", [("Content-Type", "text/plain")])
                return [b"chapter not found"]
            form = parse_post(environ)
            excerpt = form.get("excerpt", "").strip()
            if not excerpt:
                start_response("400 Bad Request", [("Content-Type", "text/plain")])
                return [b"empty excerpt"]
            style = (form.get("style", "电影海报").strip() or "电影海报")[:40]
            fp = generate_image_for_excerpt(pdir, cno, excerpt[:1200], style)
            start_response("303 See Other", [("Location", f"/novel/{quote(nid)}/chapter/{cno}")])
            return [b""]

        if len(parts) == 4 and parts[0] == "novel" and parts[2] == "chapter":
            nid = unquote(parts[1])
            try:
                cno = int(parts[3])
            except ValueError:
                start_response("400 Bad Request", [("Content-Type", "text/plain")])
                return [b"invalid chapter"]
            pdir = library_root if nid == "__root__" else (library_root / nid)
            fp = pdir / "novel_output" / f"chapter_{cno:04d}.md"
            if not fp.exists():
                start_response("404 Not Found", [("Content-Type", "text/plain")])
                return [b"chapter not found"]

            image_cards = ""
            img_dir = pdir / "generated_images"
            if img_dir.exists():
                for img in sorted(img_dir.glob(f"chapter_{cno:04d}_*.svg"), reverse=True):
                    try:
                        rel = img.resolve().relative_to(library_root.resolve())
                        url = f"/static/{quote(str(rel))}"
                        image_cards += f"<div class='card'><a class='btn' href='{url}' target='_blank'>打开</a><br/><img src='{url}'/></div>"
                    except Exception:
                        continue

            chapter_text = fp.read_text(encoding='utf-8')
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [render_page("章节详情", f"""
            <p><a class='btn' href='/novel/{quote(nid)}'>← 返回章节</a></p>
            <h1>第{cno}章详细内容</h1>
            <p>你可以先在正文中选中一段文字，再点击“使用选中文本生成配图”。不满意可继续重新生成。</p>
            <p>
              <button class='btn' onclick='fillSelection()'>使用选中文本生成配图</button>
            </p>
            <form method='post' action='/novel/{quote(nid)}/chapter/{cno}/image'>
              <label>选中文本/描述词<textarea id='excerpt_input' name='excerpt' rows='4'></textarea></label>
              <label>风格<select name='style'><option>电影海报</option><option>动漫</option><option>写实</option><option>油画</option><option>赛博霓虹</option><option>水彩</option></select></label>
              <p><button class='btn' type='submit'>生成图片</button></p>
            </form>
            <pre id='chapter_content'>{html.escape(extract_full_content(chapter_text))}</pre>
            <script>
            function fillSelection() {{
              const text = (window.getSelection && window.getSelection().toString()) || '';
              const box = document.getElementById('excerpt_input');
              if (box) box.value = text || box.value;
            }}
            </script>
            <h2>已生成图片（可点击重新查看）</h2>
            <div class='grid'>{image_cards or '<p>当前章节暂无图片。</p>'}</div>
            """)]

        start_response("404 Not Found", [("Content-Type", "text/plain")])
        return [b"not found"]

    return app


def main() -> None:
    ap = argparse.ArgumentParser(description="Novel setup + browser Web UI")
    ap.add_argument("--library-root", default=".")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    root = Path(args.library_root).resolve()
    print(f"[OK] WebUI running at http://{args.host}:{args.port} (library_root={root})")
    with make_server(args.host, args.port, app_factory(root)) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
