import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_to_prove import build_items, published_items  # noqa: E402


def proof_file(title: str, body: str) -> str:
    return rf"""
\begin{{theorem*}}[{title}]
Statement.
\end{{theorem*}}

\begin{{proof}}[Professional Standard Proof]
\LRAProofBodyStart
{body}
\end{{proof}}

\begin{{proof}}[Detailed Learning Proof]
\LRAProofBodyStart
{body}
\end{{proof}}
"""


class BuildToProveCompletionTest(unittest.TestCase):
    def minimal_knowledge(self) -> dict:
        return {
            "metadata": {"toc": []},
            "edges": [],
            "nodes": [
                {
                    "id": "thm:source-complete",
                    "kind": "Theorem",
                    "name": "Source Complete",
                    "has_proof_file": True,
                    "proof_sketch_source": "todo_stub_skipped",
                    "volume": 3,
                    "volume_roman": "iii",
                    "book_dir": "volume-iii/book-analysis-i",
                    "chapter": "bounding",
                    "proof_source": "proofs/p-source.tex",
                    "statement_display": "Source statement.",
                },
                {
                    "id": "thm:vault-complete",
                    "kind": "Theorem",
                    "name": "Vault Complete",
                    "has_proof_file": True,
                    "proof_sketch_source": "todo_stub_skipped",
                    "volume": 3,
                    "volume_roman": "iii",
                    "book_dir": "volume-iii/book-analysis-i",
                    "chapter": "bounding",
                    "proof_source": "proofs/p-vault.tex",
                    "statement_display": "Vault statement.",
                },
                {
                    "id": "thm:still-open",
                    "kind": "Theorem",
                    "name": "Still Open",
                    "has_proof_file": True,
                    "proof_sketch_source": "todo_stub_skipped",
                    "volume": 3,
                    "volume_roman": "iii",
                    "book_dir": "volume-iii/book-analysis-i",
                    "chapter": "bounding",
                    "proof_source": "proofs/p-open.tex",
                    "statement_display": "Open statement.",
                },
            ],
        }

    def test_marks_completed_from_proof_file_and_accepted_vault_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            volume = root / "lra-volume-iii"
            proof_dir = volume / "volume-iii" / "book-analysis-i" / "bounding" / "proofs"
            proof_dir.mkdir(parents=True)
            (proof_dir / "p-source.tex").write_text(proof_file("Source Complete", "A complete proof."), encoding="utf-8")
            (proof_dir / "p-vault.tex").write_text(proof_file("Vault Complete", "TODO: fill this proof."), encoding="utf-8")
            (proof_dir / "p-open.tex").write_text(proof_file("Still Open", "TODO: fill this proof."), encoding="utf-8")

            vault_record = root / "lra-proof-vault" / "volume-iii" / "book-analysis-i" / "bounding" / "thm-vault-complete"
            vault_record.mkdir(parents=True)
            (vault_record / "metadata.yaml").write_text(
                """
theorem_id: thm:vault-complete
attempts:
- attempt_id: proof-1
  review_status: reviewed-correct
  text_review_status: accepted
""".lstrip(),
                encoding="utf-8",
            )

            items = build_items(self.minimal_knowledge(), root, root / "lra-proof-vault")
            by_id = {item["id"]: item for item in items}

            self.assertEqual(by_id["thm:source-complete"]["status"], "completed")
            self.assertEqual(by_id["thm:source-complete"]["completion_sources"], ["proof_file"])
            self.assertEqual(by_id["thm:vault-complete"]["status"], "completed")
            self.assertEqual(by_id["thm:vault-complete"]["completion_sources"], ["proof_vault"])
            self.assertEqual(by_id["thm:still-open"]["status"], "open")
            self.assertNotIn("completion_sources", by_id["thm:still-open"])

    def test_published_items_exclude_completed_by_default(self):
        items = [
            {"id": "thm:done", "status": "completed"},
            {"id": "thm:todo", "status": "open"},
        ]

        self.assertEqual([item["id"] for item in published_items(items)], ["thm:todo"])
        self.assertEqual([item["id"] for item in published_items(items, include_completed=True)], ["thm:done", "thm:todo"])


if __name__ == "__main__":
    unittest.main()
