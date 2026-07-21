import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import quote, unquote_to_bytes

from novel_webui import app_factory


def write_project(project_dir: Path, title: str, summary: str, body: str, chapter_no: int = 1) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "novel_state.json").write_text(
        json.dumps({"title": title}, ensure_ascii=False),
        encoding="utf-8",
    )
    output_dir = project_dir / "novel_output"
    output_dir.mkdir(exist_ok=True)
    (output_dir / f"chapter_{chapter_no:04d}.md").write_text(
        f"**剧情摘要**\n{summary}\n\n**关键事件**\n- 测试事件\n\n---\n{body}\n",
        encoding="utf-8",
    )


class NovelWebUiEncodingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.library_root = Path(self.temp_dir.name)
        write_project(self.library_root, "根目录小说", "根目录摘要", "根目录正文")
        self.special_name = "中文+? #& 小说"
        write_project(self.library_root / self.special_name, "特殊小说", "特殊摘要", "特殊正文")
        self.ascii_name = "ascii-project"
        write_project(self.library_root / self.ascii_name, "ASCII Novel", "ASCII 摘要", "ASCII 正文")
        self.app = app_factory(self.library_root)

    def request(self, path: str):
        status_holder = {}

        def start_response(status, headers):
            status_holder["status"] = status
            status_holder["headers"] = headers

        environ = {"PATH_INFO": unquote_to_bytes(path).decode("latin-1")}
        body = b"".join(self.app(environ, start_response)).decode("utf-8")
        return status_holder["status"], body

    def test_homepage_uses_percent_encoded_project_links(self) -> None:
        status, body = self.request("/")
        self.assertEqual(status, "200 OK")
        self.assertIn(f"href='/novel/{quote(self.special_name, safe='')}'", body)
        self.assertIn(f"href='/novel/{self.ascii_name}'", body)
        self.assertIn("href='/novel/__root__'", body)

    def test_chapter_list_accepts_wsgi_latin1_path_info(self) -> None:
        encoded_name = quote(self.special_name, safe="")
        status, body = self.request(f"/novel/{encoded_name}")
        self.assertEqual(status, "200 OK")
        self.assertIn("特殊摘要", body)
        self.assertIn("中文+? #&amp; 小说 章节目录", body)
        self.assertIn(f"href='/novel/{encoded_name}/chapter/1'", body)

    def test_chapter_detail_accepts_wsgi_latin1_path_info(self) -> None:
        encoded_name = quote(self.special_name, safe="")
        status, body = self.request(f"/novel/{encoded_name}/chapter/1")
        self.assertEqual(status, "200 OK")
        self.assertIn("特殊正文", body)
        self.assertIn(f"href='/novel/{encoded_name}'", body)
        self.assertIn("中文+? #&amp; 小说 - 第1章", body)

    def test_ascii_and_root_routes_remain_compatible(self) -> None:
        ascii_status, ascii_body = self.request(f"/novel/{self.ascii_name}")
        self.assertEqual(ascii_status, "200 OK")
        self.assertIn("ASCII 摘要", ascii_body)

        root_status, root_body = self.request("/novel/__root__/chapter/1")
        self.assertEqual(root_status, "200 OK")
        self.assertIn("根目录正文", root_body)


if __name__ == "__main__":
    unittest.main()
