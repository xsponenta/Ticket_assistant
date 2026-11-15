"""Tests for split grouping, doc chunking and the labelling CLI helpers."""

import pandas as pd
import pytest

from chunk_docs import MAX_TOKENS, chunk_page, n_tokens, preprocess, split_sections
from label_cli import BM25, parse_chunks, parse_label, tokenize
from split import assign_splits, duplicate_groups


def test_duplicate_chains_form_one_group():
    groups = duplicate_groups(["A", "B", "C", "D"], [("B", "A"), ("C", "B")])
    assert groups["A"] == groups["B"] == groups["C"] != groups["D"]


def test_duplicate_pairs_share_a_split_and_ratios_hold():
    keys = [f"K-{i}" for i in range(200)]
    df = pd.DataFrame(
        {
            "key": keys,
            "target_class": ["bug" if i % 2 else "feature" for i in range(200)],
            "duplicate_of": [[f"K-{i - 1}"] if i % 10 == 1 else [] for i in range(200)],
        }
    )
    split_of = assign_splits(df)
    assert all(split_of[f"K-{i}"] == split_of[f"K-{i - 1}"] for i in range(1, 200, 10))
    assert abs(sum(s == "train" for s in split_of.values()) - 140) <= 2


def test_preprocess_docs_page():
    raw = (
        "---\nlayout: global\ntitle: SELECT\nlicense: |\n  Apache\n---\n* This will become a table of contents (this text will be scraped).\n"
        '{:toc}\n\n# Overview\nSpark {{site.SPARK_VERSION_SHORT}} docs.\n<div data-lang="scala" markdown="1">\n'
        "{% include_example scala/org/apache/spark/examples/Foo.scala %}\n{% highlight python %}\n# not a header\n{% endhighlight %}\n</div>\n"
    )
    title, body = preprocess(raw, "4.3.0")
    assert title == "SELECT"
    assert body == "# Overview\nSpark 4.3.0 docs.\n```python\n# not a header\n```"
    assert [s.path for s in split_sections(body)] == [["Overview"]]  # '# not a header' is inside code


def test_chunks_respect_max_tokens_and_carry_header_path():
    body = "# Guide\n\nIntro.\n\n## Part A\n\n" + ("Spark runs SQL queries fast. " * 300) + "\n\n## Part B\n\nShort."
    chunks = chunk_page("My Page", body)
    assert all(n_tokens(text) <= MAX_TOKENS for _, text in chunks)
    assert chunks[0][1].startswith("My Page > Guide")
    assert any(path == ["Guide", "Part A"] for path, _ in chunks)


def test_bm25_ranks_matching_document_first():
    docs = [
        tokenize(t) for t in ["dynamic partition pruning in joins", "kafka source offsets", "spark sql joins and hints"]
    ]
    assert BM25(docs).top_k(tokenize("partition pruning join"), k=1)[0][0] == 0


def test_label_cli_parsers():
    assert (
        parse_label("2") == "needs_development"
        and parse_label("out_of_scope") == "out_of_scope"
        and parse_label("x") is None
    )
    assert parse_chunks("1, 3 sql-ref#002", ["a#000", "b#001", "c#002"]) == ["a#000", "c#002", "sql-ref#002"]


def test_scope_label_summary():
    from label_cli import summarize

    candidates = [
        {"key": "A", "resolution_hint": "Fixed", "bucket": "fixed"},
        {"key": "B", "resolution_hint": "Won't Fix", "bucket": "declined"},
        {"key": "C", "resolution_hint": "Not A Problem", "bucket": "not_a_problem_or_invalid"},
        {"key": "D", "resolution_hint": "Incomplete", "bucket": "incomplete"},
    ]
    labelled = [
        {"key": "A", "label": "needs_development"},
        {"key": "B", "label": "needs_development"},
        {"key": "C", "label": "already_supported"},
    ]
    s = summarize(labelled, candidates)
    assert s["labelled"] == 3 and s["candidates"] == 4
    assert s["majority_label"] == "needs_development" and s["majority_class_accuracy"] == pytest.approx(2 / 3, abs=1e-3)
    assert s["agreement_with_resolution_hint"] == pytest.approx(2 / 3, abs=1e-3)
    assert s["bucket_x_label"]["declined"] == {"needs_development": 1}
    assert summarize([], candidates) == {"labelled": 0, "candidates": 4}


def test_generated_reference_tables_become_markdown_lines():
    from chunk_docs import generated_markdown

    html = (
        "<h3>Array Functions</h3><table class='table'><thead><tr><th>Function</th><th>Description</th></tr></thead>"
        "<tr><td>array_contains(array, value)</td><td>Returns true if the array contains the value.</td></tr></table>"
        "<h3>Examples</h3><table><tr><th>Query</th></tr><tr><td>SELECT 1</td></tr></table>"
    )
    assert generated_markdown("sql-ref-functions-builtin", html) == (
        "## Array Functions\n\n- `array_contains(array, value)`: Returns true if the array contains the value."
    )
    cfg = (
        "<h4>Shuffle Behavior</h4><table><tr><th>Property Name</th></tr><tr><td>spark.x</td></tr></table>"
        "<h4>Runtime SQL Configuration</h4><table><tr><th>Property Name</th><th>Default</th><th>Meaning</th>"
        "<th>Since Version</th></tr><tr><td>spark.sql.a</td><td>true</td><td>Enables A.</td><td>3.0.0</td></tr></table>"
    )
    assert generated_markdown("configuration", cfg) == (
        "## Runtime SQL Configuration\n\n- `spark.sql.a` (default: true; since 3.0.0): Enables A."
    )


def test_generated_reference_is_one_chunk_per_entry():
    from chunk_docs import entry_chunks

    body = "## Array Functions\n\n- `a(x)`: A.\n- `b(x)`: B.\n\n## Map Functions\n\n- `m(x)`: M."
    assert entry_chunks("Built-in", body) == [
        (["Array Functions"], "Built-in > Array Functions\n\n- `a(x)`: A."),
        (["Array Functions"], "Built-in > Array Functions\n\n- `b(x)`: B."),
        (["Map Functions"], "Built-in > Map Functions\n\n- `m(x)`: M."),
    ]
