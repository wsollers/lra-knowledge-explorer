import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from extract_lra_chapter import build_edges as build_seed_edges, extract_note_items  # noqa: E402
from seed_to_knowledge_json_v3_fixed6 import build_edges as build_knowledge_edges, build_node  # noqa: E402


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


class SourceVariantExtractionTest(unittest.TestCase):
    def test_source_variant_macro_extracts_metadata_and_edge(self):
        temp_root = Path.cwd() / "build" / "test-temp"
        temp_root.mkdir(parents=True, exist_ok=True)
        chapter = temp_root / "source-variant-chapter"
        notes = chapter / "notes"
        notes.mkdir(parents=True, exist_ok=True)
        (notes / "index.tex").write_text(
            "\n".join(
                [
                    r"\section{Source Variant Fixture}",
                    r"\begin{definition}[Canonical Addition]",
                    r"\label{def:canonical-addition}",
                    "Canonical addition.",
                    r"\end{definition}",
                    r"\begin{definition}[Tao Addition]",
                    r"\label{def:tao-addition}",
                    "Tao addition.",
                    r"\end{definition}",
                    r"\SourceVariantOf{def:canonical-addition}{Tao}{Analysis I, Section 4.1}{source_variant_of}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        items = extract_note_items(chapter)
        tao = next(item for item in items if item.id == "def:tao-addition")
        seed_edges = build_seed_edges(items)

        self.assertEqual(
            tao.source_variants,
            [
                {
                    "target": "def:canonical-addition",
                    "author": "Tao",
                    "book": "Analysis I, Section 4.1",
                    "kind": "source_variant_of",
                    "source_line_start": 10,
                }
            ],
        )
        self.assertEqual(
            [edge for edge in seed_edges if edge["kind"] == "source_variant_of"],
            [
                {
                    "from": "def:tao-addition",
                    "to": "def:canonical-addition",
                    "kind": "source_variant_of",
                    "source_author": "Tao",
                    "source_book": "Analysis I, Section 4.1",
                }
            ],
        )

    def test_second_pass_preserves_source_variant_lists(self):
        canonical_seed = {
            "id": "def:canonical-addition",
            "kind": "Definition",
            "title": "Canonical Addition",
            "label": "def:canonical-addition",
            "section_slug": "addition",
            "note_dir": "addition",
            "body_latex_b64": "",
            "remark_blocks": [],
            "proof_file_blocks": [],
        }
        tao_seed = {
            "id": "def:tao-addition",
            "kind": "Definition",
            "title": "Tao Addition",
            "label": "def:tao-addition",
            "section_slug": "addition",
            "note_dir": "addition",
            "body_latex_b64": "",
            "remark_blocks": [],
            "proof_file_blocks": [],
            "source_variants": [
                {
                    "target": "def:canonical-addition",
                    "author": "Tao",
                    "book": "Analysis I, Section 4.1",
                    "kind": "source_variant_of",
                }
            ],
        }
        nodes = [build_node(canonical_seed, "integers")[0], build_node(tao_seed, "integers")[0]]
        edges, warnings = build_knowledge_edges(nodes, [])

        self.assertEqual(warnings, [])
        self.assertEqual(edges[0]["kind"], "source_variant_of")
        self.assertEqual(edges[0]["source_author"], "Tao")
        by_id = {node["id"]: node for node in nodes}
        from seed_to_knowledge_json_v3_fixed6 import attach_edge_lists  # noqa: E402

        attach_edge_lists(nodes, edges)

        self.assertEqual(by_id["def:tao-addition"]["source_variant_of"][0]["target"], "def:canonical-addition")
        self.assertEqual(by_id["def:canonical-addition"]["source_variants"][0]["source"], "def:tao-addition")


if __name__ == "__main__":
    unittest.main()
