"""C3 scope checker: split, label definitions, schema, prompt, grounding, calibration sampling, test lock."""

import random
import sys
from pathlib import Path

import pytest
from test_retrieval import FakeEncoder

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src" / "data"))

import eval_c3  # noqa: E402
from label_cli import LABELS as GUIDELINES  # noqa: E402

from src.components import scope_checker as c3  # noqa: E402
from src.eval.judge_label_cli import balanced_sample  # noqa: E402
from src.eval.judges import reference_grounded  # noqa: E402
from src.prompting import load_prompt  # noqa: E402
from src.schemas.c3 import SCOPE_LABELS, C3Output  # noqa: E402


def test_label_definitions_identical_to_guidelines():
    assert SCOPE_LABELS == dict(GUIDELINES.values())


def test_split_is_stratified_frozen_and_deterministic():
    labels = {
        f"K{i:02d}": lab
        for i, lab in enumerate(
            ["already_supported"] * 42 + ["needs_development"] * 28 + ["out_of_scope"] * 8 + ["insufficient_info"] * 2
        )
    }
    split = eval_c3.make_split(labels, dev_size=30, seed=42)
    dev_counts = {lab: sum(labels[k] == lab for k in split["dev"]) for lab in SCOPE_LABELS}
    assert dev_counts == {"already_supported": 16, "needs_development": 10, "out_of_scope": 3, "insufficient_info": 1}
    assert len(split["test"]) == 50 and not set(split["dev"]) & set(split["test"])
    assert split == eval_c3.make_split(labels, dev_size=30, seed=42)


def test_c3_output_requires_reference_when_supported():
    ok = C3Output.model_validate(
        {
            "rationale": "r",
            "verdict": "already_supported",
            "cited_chunk_ids": ["a#001"],
            "explanation": "Use X.",
            "doc_reference": "spark.sql.x",
        }
    )
    assert ok.doc_reference == "spark.sql.x"
    with pytest.raises(ValueError, match="doc_reference"):
        C3Output.model_validate({"rationale": "r", "verdict": "already_supported", "explanation": "e"})
    assert (
        C3Output.model_validate({"rationale": "r", "verdict": "needs_development", "explanation": "e"}).doc_reference
        is None
    )


def test_prompt_renders_definitions_and_chunk_ids():
    chunks = [{"chunk_id": "sql-ref#003", "url": "https://x", "text": "SELECT … DISTINCT"}]
    system, user = (m["content"] for m in c3.build_messages(load_prompt("c3_scope"), "S", "D" * 2000, chunks))
    assert all(definition in system for definition in SCOPE_LABELS.values()) and "$" not in system
    assert "[sql-ref#003] https://x" in user and "D" * 1500 in user and "D" * 1501 not in user
    assert "do NOT name an API" in system


def test_doc_index_variants_return_k_ids():
    chunks = [
        {"chunk_id": f"p#{i:03d}", "text": t, "url": "u"}
        for i, t in enumerate(
            ["dynamic partition pruning", "kafka offsets", "structured streaming triggers", "pandas udf"]
        )
    ]
    for variant in c3.VARIANTS:
        index = c3.DocIndex(chunks, variant, FakeEncoder() if variant != "bm25" else None)
        hits = index.search("partition pruning in joins", 2)
        assert len(hits) == 2 and len(set(hits)) == 2
    assert c3.DocIndex(chunks, "bm25").search("kafka offsets lost", 1) == [1]


def test_reference_grounding():
    texts = ["Set `spark.sql.adaptive.enabled` to true.", "Use DataFrame.dropDuplicates(subset) to …"]
    assert reference_grounded("spark.sql.adaptive.enabled", texts)
    assert reference_grounded("`DataFrame.dropDuplicates()`", texts)
    assert reference_grounded("spark.sql.adaptive.enabled, dropDuplicates", texts)
    assert not reference_grounded("spark.sql.files.maxPartitionBytes", texts)
    assert not reference_grounded("dropDuplicates and spark.sql.foo", texts) and not reference_grounded(None, texts)


def test_balanced_calibration_sample():
    pairs = [{"pair_id": f"p{i}", "judge_run1": i < 25} for i in range(40)]
    sample = balanced_sample(pairs, 10, random.Random(42))
    assert len(sample) == 10 and sum(p["judge_run1"] for p in sample) == 5
    few_no = [{"pair_id": f"p{i}", "judge_run1": i < 38} for i in range(40)]
    s2 = balanced_sample(few_no, 10, random.Random(42))
    assert len(s2) == 10 and sum(not p["judge_run1"] for p in s2) == 2


def test_c3_test_lock(tmp_path):
    with pytest.raises(SystemExit, match="--confirm-test"):
        eval_c3.check_test_allowed("test", False, False, tmp_path / "x.json", tmp_path, prefix="c3")
