import json
import tempfile
import unittest
from pathlib import Path

from novel_webui import app_factory


def make_project(project_dir: Path, title: str, chapter_text: str = "正文") -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    (project_dir / "novel_state.json").write_text(
        json.dumps({"title": title}, ensure_ascii=False),
        encoding="utf-8",
    )
    output_dir = project_dir / "novel_output"
    output_dir.mkdir()
    (output_dir / "chapter_0001.md").write_text(
        f"**剧情摘要**\n摘要\n\n---\n\n{chapter_text}\n",
        encoding="utf-8",
    )


def request(app, path: str):
    response = {}

    def start_response(status, headers):
        response["status"] = status
        response["headers"] = headers

    body = b"".join(app({"PATH_INFO": path}, start_response))
    return response["status"], body


class ProjectBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.library_root = self.base_dir / "library"
        self.library_root.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_valid_child_project_routes_return_200(self) -> None:
        make_project(self.library_root / "valid", "合法项目", "合法正文")
        app = app_factory(self.library_root)

        directory_status, directory_body = request(app, "/novel/valid")
        chapter_status, chapter_body = request(app, "/novel/valid/chapter/1")

        self.assertEqual(directory_status, "200 OK")
        self.assertIn("合法项目".encode(), request(app, "/")[1])
        self.assertEqual(chapter_status, "200 OK")
        self.assertIn("合法正文".encode(), chapter_body)
        self.assertNotEqual(directory_body, b"")

    def test_parent_directory_chapter_access_returns_404(self) -> None:
        make_project(self.base_dir, "外部项目", "外部机密正文")
        app = app_factory(self.library_root)

        status, body = request(app, "/novel/../chapter/1")

        self.assertEqual(status, "404 Not Found")
        self.assertNotIn("外部机密正文".encode(), body)

    def test_external_project_symlink_is_hidden_and_returns_404(self) -> None:
        outside = self.base_dir / "outside"
        make_project(outside, "外部符号链接项目", "符号链接外部正文")
        (self.library_root / "outside-link").symlink_to(outside, target_is_directory=True)
        app = app_factory(self.library_root)

        home_status, home_body = request(app, "/")
        directory_status, directory_body = request(app, "/novel/outside-link")
        chapter_status, chapter_body = request(app, "/novel/outside-link/chapter/1")

        self.assertEqual(home_status, "200 OK")
        self.assertNotIn(b"outside-link", home_body)
        self.assertNotIn("外部符号链接项目".encode(), home_body)
        self.assertEqual(directory_status, "404 Not Found")
        self.assertNotIn("外部符号链接项目".encode(), directory_body)
        self.assertEqual(chapter_status, "404 Not Found")
        self.assertNotIn("符号链接外部正文".encode(), chapter_body)

    def test_external_state_symlink_invalidates_project(self) -> None:
        project = self.library_root / "state-link"
        project.mkdir()
        (project / "novel_output").mkdir()
        outside_state = self.base_dir / "outside_state.json"
        outside_state.write_text(
            json.dumps({"title": "外部状态机密"}, ensure_ascii=False),
            encoding="utf-8",
        )
        (project / "novel_state.json").symlink_to(outside_state)
        app = app_factory(self.library_root)

        home_status, home_body = request(app, "/")
        directory_status, directory_body = request(app, "/novel/state-link")
        chapter_status, chapter_body = request(app, "/novel/state-link/chapter/1")

        self.assertEqual(home_status, "200 OK")
        self.assertNotIn(b"state-link", home_body)
        self.assertNotIn("外部状态机密".encode(), home_body)
        self.assertEqual(directory_status, "404 Not Found")
        self.assertNotIn("外部状态机密".encode(), directory_body)
        self.assertEqual(chapter_status, "404 Not Found")
        self.assertNotIn("外部状态机密".encode(), chapter_body)

    def test_external_output_symlink_invalidates_project(self) -> None:
        project = self.library_root / "output-link"
        project.mkdir()
        (project / "novel_state.json").write_text(
            json.dumps({"title": "输出逃逸项目"}, ensure_ascii=False),
            encoding="utf-8",
        )
        outside_output = self.base_dir / "outside_output"
        outside_output.mkdir()
        (outside_output / "chapter_0001.md").write_text(
            "**剧情摘要**\n外部输出机密\n\n---\n\n外部输出正文\n",
            encoding="utf-8",
        )
        (project / "novel_output").symlink_to(outside_output, target_is_directory=True)
        app = app_factory(self.library_root)

        home_status, home_body = request(app, "/")
        directory_status, directory_body = request(app, "/novel/output-link")
        chapter_status, chapter_body = request(app, "/novel/output-link/chapter/1")

        self.assertEqual(home_status, "200 OK")
        self.assertNotIn(b"output-link", home_body)
        self.assertNotIn("外部输出机密".encode(), home_body)
        self.assertEqual(directory_status, "404 Not Found")
        self.assertNotIn("外部输出机密".encode(), directory_body)
        self.assertEqual(chapter_status, "404 Not Found")
        self.assertNotIn("外部输出正文".encode(), chapter_body)

    def test_external_chapter_symlink_is_skipped_and_returns_404(self) -> None:
        project = self.library_root / "chapter-link"
        make_project(project, "章节逃逸项目")
        chapter_link = project / "novel_output" / "chapter_0001.md"
        chapter_link.unlink()
        outside_chapter = self.base_dir / "outside_chapter.md"
        outside_chapter.write_text(
            "**剧情摘要**\n外部章节机密\n\n---\n\n外部章节正文\n",
            encoding="utf-8",
        )
        chapter_link.symlink_to(outside_chapter)
        app = app_factory(self.library_root)

        home_status, home_body = request(app, "/")
        directory_status, directory_body = request(app, "/novel/chapter-link")
        chapter_status, chapter_body = request(app, "/novel/chapter-link/chapter/1")

        self.assertEqual(home_status, "200 OK")
        self.assertIn(b"chapter-link", home_body)
        self.assertNotIn("外部章节机密".encode(), home_body)
        self.assertEqual(directory_status, "200 OK")
        self.assertNotIn("外部章节机密".encode(), directory_body)
        self.assertEqual(chapter_status, "404 Not Found")
        self.assertNotIn("外部章节正文".encode(), chapter_body)

    def test_root_project_is_available_only_through_root_id(self) -> None:
        make_project(self.library_root, "根项目", "根项目正文")
        app = app_factory(self.library_root)

        home_status, home_body = request(app, "/")
        directory_status, _ = request(app, "/novel/__root__")
        chapter_status, chapter_body = request(app, "/novel/__root__/chapter/1")
        dot_status, _ = request(app, "/novel/.")

        self.assertEqual(home_status, "200 OK")
        self.assertIn(b"__root__", home_body)
        self.assertEqual(directory_status, "200 OK")
        self.assertEqual(chapter_status, "200 OK")
        self.assertIn("根项目正文".encode(), chapter_body)
        self.assertEqual(dot_status, "404 Not Found")


if __name__ == "__main__":
    unittest.main()
