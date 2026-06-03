import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from extract_lra_chapter import extract_note_items  # noqa: E402


class ExpositionExtractionTest(unittest.TestCase):
    def test_exposition_attaches_to_preceding_item(self):
        chapter = ROOT / "tests" / "fixtures" / "exposition-chapter"
        expected = json.loads((chapter / "expected_expositions.json").read_text(encoding="utf-8"))

        items = extract_note_items(chapter)

        self.assertEqual(len(items), 2)
        theorem = next(item for item in items if item.id == "thm:compactness-payoff")
        self.assertEqual(len(theorem.expositions), 1)

        exposition = theorem.expositions[0]
        for key, value in expected[0].items():
            self.assertEqual(exposition[key], value)
        self.assertIn("prevents values from escaping", exposition["body_preview"])


class HiddenDependencyExtractionTest(unittest.TestCase):
    def test_hidden_dependency_block_attaches_to_preceding_item(self):
        chapter = ROOT / "tests" / "fixtures" / "hidden-dependency-chapter"

        items = extract_note_items(chapter)

        point = next(item for item in items if item.id == "def:hidden-point")
        line = next(item for item in items if item.id == "def:hidden-line")

        self.assertTrue(point.no_local_dependencies)
        self.assertEqual(point.dependency_refs, [])
        self.assertEqual(point.dependency_blocks, [])

        self.assertFalse(line.no_local_dependencies)
        self.assertEqual(line.dependency_refs, ["def:hidden-point"])
        self.assertEqual(len(line.dependency_blocks), 1)
        self.assertTrue(line.dependency_blocks[0]["hidden"])
        self.assertEqual(line.dependency_blocks[0]["env_name"], "dependencies")


if __name__ == "__main__":
    unittest.main()
