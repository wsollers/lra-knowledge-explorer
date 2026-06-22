import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "extract_model_artifacts.py"


class ModelArtifactExtractionTest(unittest.TestCase):
    def test_extracts_structured_modelbox_metadata_and_components(self):
        source_root = ROOT / "tests" / "fixtures" / "model-artifact-source"
        output = source_root / "model-artifacts.actual.json"
        if output.exists():
            output.unlink()
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--source-root",
                str(source_root),
                "--output",
                str(output),
                "--macro-file",
                str(source_root / "common" / "macros.tex"),
                "--strict",
            ],
            text=True,
            capture_output=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        payload = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(payload["metadata"]["artifact_count"], 3)
        self.assertEqual(payload["metadata"]["katex_macro_count"], 5)
        self.assertEqual(payload["katex_macros"]["macros"]["\\conv"], "\\operatorname{conv}")
        self.assertEqual(payload["katex_macros"]["macros"]["\\False"], "\\mathsf{False}")
        self.assertEqual(payload["katex_macros"]["macros"]["\\colonequiv"], "\\equiv")
        self.assertEqual(payload["katex_macros"]["macros"]["\\dom"], "\\operatorname{dom}")
        self.assertIn(
            {"name": "\\ProofPlan", "reason": "contains non-KaTeX frontend token \\textbf"},
            payload["katex_macros"]["skipped"],
        )
        self.assertEqual(
            [artifact["id"] for artifact in payload["artifacts"]],
            [
                "bridge:free-sigma-algebra-evaluation",
                "bridge:consequence",
                "model:example",
            ],
        )
        artifact = next(a for a in payload["artifacts"] if a["id"] == "model:example")
        self.assertEqual(artifact["id"], "model:example")
        self.assertEqual(artifact["kind"], "model")
        self.assertEqual(artifact["layer"], "example-layer")
        self.assertEqual([c["name"] for c in artifact["components"]], ["Structure", "Syntax--Semantics Bridge"])
        self.assertEqual(artifact["components"][1]["items"][0]["command"], "bridgeclause")
        self.assertEqual(artifact["depends_on"][0]["id"], "bridge:consequence")
        self.assertEqual(artifact["depends_on"][1]["id"], "bridge:free-sigma-algebra-evaluation")
        output.unlink()


if __name__ == "__main__":
    unittest.main()
