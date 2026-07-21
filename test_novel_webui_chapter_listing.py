import json
import tempfile
import unittest
from pathlib import Path

from novel_webui import app_factory, list_chapters


def make_project(project_dir: Path) -> Path:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "novel_state.json").write_text(
        json.dumps({"title": "测试小说"}, ensure_ascii=False),
        encoding="utf-8",
    )
    output_dir = project_dir / "novel_output"
    output_dir.mkdir()
    return output_dir


def write_chapter(output_dir: Path, chapter_no: int, summary: str) -> Path:
    chapter_file = output_dir / f"chapter_{chapter_no:04d}.md"
    chapter_file.write_text(
        f"**剧情摘要**\n{summary}\n\n---\n\n正文\n",
        encoding="utf-8",
    )
    return chapter_file


def wsgi_request(app, path: str):
    response = {}

    def start_response(status, headers):
        response["status"] = status

    body = b"".join(app({"PATH_INFO": path}, start_response))
    return response["status"], body


class ChapterListingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.temp_dir.name) / "novel"
        self.output_dir = make_project(self.project_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_four_digit_chapters_are_listed(self) -> None:
        write_chapter(self.output_dir, 1, "第一章摘要")
        write_chapter(self.output_dir, 42, "第四十二章摘要")

        chapters = list_chapters(self.project_dir)

        self.assertEqual([ch.chapter_no for ch in chapters], [1, 42])
        self.assertEqual(chapters[0].summary, "第一章摘要")
        self.assertEqual(chapters[1].summary, "第四十二章摘要")

    def test_chapter_10000_is_listed(self) -> None:
        write_chapter(self.output_dir, 10000, "第一万章摘要")

        chapters = list_chapters(self.project_dir)

        self.assertEqual([ch.chapter_no for ch in chapters], [10000])
        self.assertEqual(chapters[0].summary, "第一万章摘要")

    def test_numeric_order_places_9999_before_10000(self) -> None:
        write_chapter(self.output_dir, 10000, "第一万章")
        write_chapter(self.output_dir, 9999, "第九九九九章")
        write_chapter(self.output_dir, 10001, "第一万零一章")

        chapters = list_chapters(self.project_dir)

        self.assertEqual([ch.chapter_no for ch in chapters], [9999, 10000, 10001])

    def test_rejects_malformed_chapter_names(self) -> None:
        write_chapter(self.output_dir, 1, "合法章节")
        write_chapter(self.output_dir, 10000, "合法第一万章")
        for bad_name in (
            "chapter_1.md",
            "chapter_123.md",
            "chapter_001.md",
            "chapter_010000.md",
            "chapter_0010000.md",
            "chapter_０００１.md",
            "chapter_１００００.md",
            "chapter_0001.md\n",
        ):
            (self.output_dir / bad_name).write_text(
                "**剧情摘要**\n非法文件名\n\n---\n\n正文\n",
                encoding="utf-8",
            )

        chapters = list_chapters(self.project_dir)

        self.assertEqual([ch.chapter_no for ch in chapters], [1, 10000])
        self.assertEqual(
            [ch.file_path.name for ch in chapters],
            ["chapter_0001.md", "chapter_10000.md"],
        )

    def test_wsgi_list_page_links_chapter_10000(self) -> None:
        write_chapter(self.output_dir, 10000, "第一万章摘要")
        library_root = self.project_dir.parent
        app = app_factory(library_root)

        status, body = wsgi_request(app, f"/novel/{self.project_dir.name}")

        self.assertEqual(status, "200 OK")
        self.assertIn(b"/chapter/10000", body)
        self.assertIn("第一万章摘要".encode(), body)


if __name__ == "__main__":
    unittest.main()
