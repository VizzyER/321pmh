import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CLI_PATH = Path(__file__).resolve().parents[1] / "novel_generator.py"
MISSING_KEY_ERROR = "OPENAI_API_KEY 未设置，请通过 --api-key 或环境变量传入。"
NO_NETWORK_RUNNER = """
import runpy
import sys
import urllib.request


def fail_urlopen(*args, **kwargs):
    raise AssertionError("network access attempted")


script = sys.argv[1]
sys.argv = sys.argv[1:]
urllib.request.urlopen = fail_urlopen
runpy.run_path(script, run_name="__main__")
"""


class CliApiKeyTests(unittest.TestCase):
    def test_init_accepts_empty_api_key_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            state_path = project_dir / "state.json"
            output_dir = project_dir / "chapters"

            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    NO_NETWORK_RUNNER,
                    str(CLI_PATH),
                    "--api-key",
                    "",
                    "--state",
                    str(state_path),
                    "--output",
                    str(output_dir),
                    "init",
                    "--title",
                    "测试小说",
                    "--genre",
                    "科幻",
                    "--premise",
                    "测试设定",
                    "--total-chapters",
                    "2",
                    "--words-per-chapter",
                    "1000",
                    "--world-bible",
                    "测试世界观",
                ],
                cwd=project_dir,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(state_path.read_text(encoding="utf-8")),
                {
                    "title": "测试小说",
                    "genre": "科幻",
                    "premise": "测试设定",
                    "total_chapters": 2,
                    "words_per_chapter": 1000,
                    "style_guide": "第三人称、多线叙事、重视伏笔回收",
                    "world_bible": "测试世界观",
                    "chapter_summaries": [],
                    "timeline_events": [],
                    "characters": [],
                },
            )

    def test_run_rejects_empty_api_key_with_existing_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = subprocess.run(
                [
                    sys.executable,
                    str(CLI_PATH),
                    "--api-key",
                    "",
                    "run",
                ],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stderr, f"{MISSING_KEY_ERROR}\n")


if __name__ == "__main__":
    unittest.main()
