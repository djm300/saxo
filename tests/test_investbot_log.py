import tempfile
import unittest
from pathlib import Path

from scripts.append_investbot_log import append_run_log


class TestInvestbotLog(unittest.TestCase):
    def test_appends_sanitized_run_conclusion_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "20260820T101416416Z-review"
            run.mkdir()
            (run / "execution.json").write_text(
                '{"status":"completed","completed_at":"2026-08-20T10:18:22Z",'
                '"orders":[]}',
                encoding="utf-8",
            )
            log = root / "investbot.log"
            result = append_run_log(run, "No trade; market closed.", "Next open market.", log)
            line = log.read_text(encoding="utf-8")

            self.assertTrue(result["appended"])
            self.assertIn("2026-08-20T10:18:22Z", line)
            self.assertIn("status=completed", line)
            self.assertIn("orders=0", line)
            self.assertIn("conclusion=No trade; market closed.", line)
            with self.assertRaisesRegex(ValueError, "already contains"):
                append_run_log(run, "Duplicate", "Never", log)

    def test_rejects_sensitive_or_multiline_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "20260820T101129Z-review"
            run.mkdir()
            (run / "run-status.json").write_text(
                '{"status":"blocked","timestamp":"2026-08-20T10:11:50Z"}',
                encoding="utf-8",
            )
            log = root / "investbot.log"
            append_run_log(run, "Rate limit\nblocked research.", "Retry later.", log)
            self.assertIn("Rate limit blocked research.", log.read_text(encoding="utf-8"))
            other = root / "20260820T101200Z-review"
            other.mkdir()
            with self.assertRaisesRegex(ValueError, "sensitive-looking"):
                append_run_log(other, "Access token leaked", "Never", log)


if __name__ == "__main__":
    unittest.main()
