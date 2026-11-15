"""C1 classifier: few-shot index, component mapping, baseline, prompt, LLM call wiring, test guard."""

import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

import eval_c1  # noqa: E402

from src.components import classifier as c1  # noqa: E402
from src.components.classifier_baseline import BaselineC1  # noqa: E402
from src.eval.samples import load_split  # noqa: E402
from src.prompting import load_prompt  # noqa: E402
from src.schemas.c1 import TOP_COMPONENTS, C1Output  # noqa: E402

WORDS = {
    "bug": "crash exception null pointer wrong result error fails",
    "feature": "add support new option api improve performance allow",
    "task": "upgrade dependency bump version tests documentation refactor",
    "idea": "wish would be nice maybe consider proposal someday",
}


def toy_df(n_per_class: int = 12) -> pd.DataFrame:
    rows = []
    for cls, words in WORDS.items():
        for i in range(n_per_class):
            rows.append(
                {
                    "key": f"{cls}-{i}",
                    "target_class": cls,
                    "summary": f"{words} item{i}",
                    "description_md": f"{words} details {i}",
                    "components": ["SQL"] if i % 2 else ["Mesos"],
                }
            )
    return pd.DataFrame(rows)


def test_input_modes_and_component_mapping():
    assert c1.input_text("Join fails", "desc " * 1000, "summary") == "Join fails"
    full = c1.input_text("Join fails", "x" * 2000, "full")
    assert full.startswith("Join fails\n\n") and len(full) == len("Join fails\n\n") + c1.DESC_CHARS
    assert c1.map_components(["SQL", "Mesos"]) == {"SQL", "other"} and c1.map_components([]) == {"other"}


def test_top_components_match_train_split():
    counts = Counter(c for cs in load_split("train").components for c in cs)
    assert TOP_COMPONENTS == [c for c, _ in counts.most_common(15)]


def test_few_shot_index_returns_k_per_class_from_index_only():
    df = toy_df()
    index = c1.FewShotIndex(df, "full")
    examples = index.neighbours("crash with null pointer exception", k=2)
    assert Counter(e.label for e in examples) == dict.fromkeys(c1.CLASSES, 2)
    assert {e.key for e in examples} <= set(df.key)
    assert examples[0].label == "bug"  # the most similar example comes first
    assert index.neighbours("anything", 0) == []


@pytest.mark.filterwarnings("ignore:Label not")  # toy data uses only 2 of the 16 components
def test_baseline_fits_and_predicts():
    df = toy_df()
    texts = [c1.input_text(s, d, "full") for s, d in zip(df.summary, df.description_md, strict=True)]
    model = BaselineC1.fit(texts, list(df.target_class), [c1.map_components(c) for c in df.components], 1.0, 1.0)
    out = model.predict(["upgrade dependency version bump"])[0]
    assert out["label"] == "task" and 0 < out["confidence"] <= 1 and len(out["component"]) == 3


def test_prompt_and_llm_call(monkeypatch):
    captured = {}

    def fake_complete(messages, **kwargs):
        captured.update(messages=messages, **kwargs)
        return C1Output.model_validate({"rationale": "r", "class": "bug", "component": ["SQL"], "confidence": 0.9})

    monkeypatch.setattr(c1.llm, "complete", fake_complete)
    index = c1.FewShotIndex(toy_df(), "full")
    out = c1.classify("Join crashes", "NullPointerException", mode="full", k=1, index=index, session_id="s")
    assert out.label == "bug"
    assert (
        captured["role"] == "generator" and captured["schema"] is C1Output and captured["component"] == "c1_classifier"
    )
    system, user = captured["messages"][0]["content"], captured["messages"][1]["content"]
    assert "idea:" in system and "Pandas API on Spark" in system and "$" not in system
    assert user.count("Example — class:") == 4 and user.endswith("Join crashes\n\nNullPointerException")
    no_examples = c1.build_messages(load_prompt("c1_classifier"), "ticket", [])[1]["content"]
    assert no_examples == "Ticket to classify:\nticket"


def test_c1_output_schema():
    ok = C1Output.model_validate({"rationale": "r", "class": "idea", "component": ["SQL", "other"], "confidence": 0.4})
    assert ok.label == "idea"
    with pytest.raises(ValueError):
        C1Output.model_validate({"rationale": "r", "class": "idea", "component": ["Mesos"], "confidence": 0.4})
    with pytest.raises(ValueError):
        C1Output.model_validate({"rationale": "r", "class": "idea", "component": [], "confidence": 1.5})


def test_test_split_guard(tmp_path):
    final = tmp_path / "final.json"
    eval_c1.check_test_allowed("val", False, False, final, tmp_path)  # val is always allowed
    with pytest.raises(SystemExit, match="--confirm-test"):
        eval_c1.check_test_allowed("test", False, False, final, tmp_path)
    with pytest.raises(SystemExit, match="missing"):
        eval_c1.check_test_allowed("test", True, False, eval_c1.ROOT / "eval" / "nope.json", tmp_path)
    final.write_text(json.dumps({}))
    eval_c1.check_test_allowed("test", True, False, final, tmp_path)
    (tmp_path / "c1_test_20260101T000000Z.json").write_text("{}")
    with pytest.raises(SystemExit, match="already evaluated"):
        eval_c1.check_test_allowed("test", True, False, final, tmp_path)
    eval_c1.check_test_allowed("test", True, True, final, tmp_path)  # --force


def test_worst_errors_force_key_confusions():
    gold = {"a": "idea", "b": "bug", "c": "feature", "d": "task"}
    preds = {
        "a": {"label": "feature", "confidence": 0.2},
        "b": {"label": "task", "confidence": 0.1},
        "c": {"label": "bug", "confidence": 0.99},
        "d": {"label": "task", "confidence": 0.9},
    }
    assert eval_c1.worst_errors(list(gold), gold, preds, n=2) == ["a", "b"]
