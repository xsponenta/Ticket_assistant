"""C2 duplicate finder: time mask, never the query itself, output schema, alert threshold rule, test lock."""

import sys
from pathlib import Path

import pandas as pd
import pytest
from test_retrieval import FakeEncoder

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

import eval_c2  # noqa: E402

from src.components.duplicate_finder import DuplicateFinder, issue_text  # noqa: E402


def corpus() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "key": ["SPARK-1", "SPARK-2", "SPARK-3", "SPARK-4"],
            "summary": ["Join fails with NPE", "Join fails with null pointer", "Upgrade netty", "Join NPE again"],
            "description_md": ["NullPointerException in join", "NPE when joining, see SPARK-9", "", "same NPE"],
            "created": pd.to_datetime(["2021-01-01", "2022-01-01", "2023-01-01", "2024-01-01"], utc=True),
        }
    )


@pytest.mark.parametrize("variant", ["bm25", "dense", "hybrid"])
def test_only_earlier_issues_and_never_the_query(variant):
    finder = DuplicateFinder(corpus(), variant, FakeEncoder() if variant != "bm25" else None)
    out = finder.find(
        "Join fails with NPE",
        "NullPointerException in join",
        "full",
        created_before=pd.Timestamp("2023-06-01", tz="UTC"),
        exclude_key="SPARK-1",
    )
    keys = [c.key for c in out.candidates]
    assert "SPARK-1" not in keys and "SPARK-4" not in keys  # itself / created later
    assert set(keys) <= {"SPARK-2", "SPARK-3"}
    assert out.candidates[0].url == f"https://issues.apache.org/jira/browse/{out.candidates[0].key}"


def test_issue_text_masks_keys_and_modes():
    assert issue_text("Fix SPARK-12", "See HIVE-3 for details", "full") == "Fix <ISSUE>\n\nSee <ISSUE> for details"
    assert issue_text("Fix SPARK-12", "long description", "summary") == "Fix <ISSUE>"
    assert issue_text("Fix SPARK-12", "", "full", mask_keys=False) == "Fix SPARK-12"


def test_alert_flag_uses_threshold():
    finder = DuplicateFinder(corpus(), "dense", FakeEncoder(), alert_threshold=0.0)
    assert finder.find("Join fails with NPE").alert is True
    finder.alert_threshold = 2.0
    assert finder.find("Join fails with NPE").alert is False


def test_threshold_rule_caps_false_alarms():
    recs = [{"kind": "duplicate", "alert_score": s, "rank": 1} for s in (0.9, 0.8, 0.7, 0.4)]
    recs += [{"kind": "non_duplicate", "alert_score": s, "rank": None} for s in (0.75, 0.3, 0.2, 0.1, 0.05)]
    t = eval_c2.choose_threshold(recs, max_false_alarm=0.20)
    m = eval_c2.alert_metrics(recs, t)
    assert t == 0.4 and m["false_alarm_rate"] == 0.2 and m["alert_recall"] == 1.0  # one more false alarm would be 0.4
    assert eval_c2.alert_metrics(recs, 0.3)["false_alarm_rate"] == 0.4


def test_ranking_metrics():
    recs = [{"kind": "duplicate", "rank": r, "alert_score": 0.5, "ms": 1.0} for r in (1, 3, None, 12)]
    m = eval_c2.ranking_metrics(recs)
    assert m["recall@1"] == 0.25 and m["recall@5"] == 0.5 and m["recall@10"] == 0.5
    assert m["mrr"] == pytest.approx((1 + 1 / 3 + 0 + 1 / 12) / 4, abs=1e-4) and m["not_in_top100"] == 1


def test_c2_test_lock(tmp_path):
    with pytest.raises(SystemExit, match="--confirm-test"):
        eval_c2.check_test_allowed("test", False, False, tmp_path / "x.json", tmp_path, prefix="c2")
    (tmp_path / "final.json").write_text("{}")
    (tmp_path / "c2_test_20260101T000000Z.json").write_text("{}")
    with pytest.raises(SystemExit, match="already evaluated"):
        eval_c2.check_test_allowed("test", True, False, tmp_path / "final.json", tmp_path, prefix="c2")
