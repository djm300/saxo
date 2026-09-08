import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_investment_bot import (
    ActivityReporter,
    build_codex_command,
    event_messages,
    summarize_run,
)


class TestInvestmentBotLauncher(unittest.TestCase):
    def test_reporter_prints_and_appends_sanitized_events(self):
        with tempfile.TemporaryDirectory() as directory:
            stream = io.StringIO()
            log = Path(directory) / "investbot.log"
            reporter = ActivityReporter(log, stream)
            reporter.emit("prompt", "Review every current position")
            reporter.emit("activity", "access token must never be shown")

            screen = stream.getvalue()
            persisted = log.read_text(encoding="utf-8")
            self.assertIn("PROMPT", screen)
            self.assertIn("Review every current position", screen)
            self.assertIn("[redacted sensitive output]", screen)
            self.assertIn("event=prompt", persisted)
            self.assertNotIn("access token", persisted)

    def test_codex_events_become_progress_activity_and_conclusions(self):
        self.assertEqual(
            event_messages({"type": "thread.started"}),
            [("activity", "Codex session started.")],
        )
        self.assertEqual(
            event_messages(
                {
                    "type": "item.completed",
                    "item": {"type": "reasoning", "text": "Reviewing holdings."},
                }
            ),
            [("progress", "Reviewing holdings.")],
        )
        self.assertEqual(
            event_messages(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": "No trade suggested."},
                }
            ),
            [("conclusion", "No trade suggested.")],
        )

    def test_command_is_python_launcher_contract_for_luna_json_events(self):
        command = build_codex_command(
            Path("codex"), Path("repo"), Path("credentials"), "prompt text"
        )
        self.assertIn("--json", command)
        self.assertIn("gpt-5.6-luna", command)
        self.assertIn('model_reasoning_effort="medium"', command)
        self.assertEqual(command[-1], "prompt text")

    def test_summarizes_new_run_dispositions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "20260820T120000Z-review"
            run = root / "agent" / "runs" / run_id
            run.mkdir(parents=True)
            (root / "agent" / ".current_run_id").write_text(run_id, encoding="utf-8")
            (run / "execution.json").write_text(
                json.dumps({"status": "completed", "orders": [{"side": "sell"}]}),
                encoding="utf-8",
            )
            (run / "holdings-review.json").write_text(
                json.dumps(
                    {
                        "positions": [
                            {"decision": "hold"},
                            {"decision": "trim"},
                            {"decision": "exit"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            summary = summarize_run(root, "older-run")
            self.assertIn("status=completed", summary)
            self.assertIn("orders=1", summary)
            self.assertIn("positions reviewed=3", summary)
            self.assertIn("trim=1", summary)
            self.assertIn("exit=1", summary)


if __name__ == "__main__":
    unittest.main()
