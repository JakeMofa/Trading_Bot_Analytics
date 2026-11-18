"""Keep reviewed Actions runtimes and hosted OS choices stable."""

from pathlib import Path
import re
import unittest


WORKFLOWS = Path(__file__).resolve().parents[1] / "workflows"
PINS = {
    "actions/checkout": "fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09",
    "actions/setup-python": "ece7cb06caefa5fff74198d8649806c4678c61a1",
    "actions/setup-go": "924ae3a1cded613372ab5595356fb5720e22ba16",
    "actions/upload-artifact": "b7c566a772e6b6bfb58ed0dc250532a479d7789f",
}


class WorkflowRuntimePinsTest(unittest.TestCase):
    def test_supported_node24_actions_and_stable_hosted_image(self):
        files = sorted(WORKFLOWS.glob("*.yml"))
        self.assertTrue(files)
        seen = set()
        for path in files:
            source = path.read_text()
            with self.subTest(workflow=path.name):
                self.assertNotIn("runs-on: ubuntu-latest", source)
                for action, revision in re.findall(
                    r"uses:\s+(actions/(?:checkout|setup-python|setup-go|upload-artifact))@([0-9a-f]{40})",
                    source,
                ):
                    seen.add(action)
                    self.assertEqual(revision, PINS[action])
                for action in PINS:
                    self.assertNotRegex(source, rf"uses:\s+{re.escape(action)}@(?![0-9a-f]{{40}})")
        self.assertEqual(seen, set(PINS))

    def test_private_runner_selection_is_unchanged(self):
        for name in ("cd-pp.yml", "pp-controller-identity.yml", "pp-live-control.yml"):
            with self.subTest(workflow=name):
                self.assertIn(
                    "runs-on: [self-hosted, tradebot-private]",
                    (WORKFLOWS / name).read_text(),
                )


if __name__ == "__main__":
    unittest.main()
