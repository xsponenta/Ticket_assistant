"""Tests for split grouping, doc chunking and the labelling CLI helpers."""

import pandas as pd

from chunk_docs import MAX_TOKENS, chunk_page, n_tokens, preprocess, split_sections
from label_cli import BM25, parse_chunks, parse_label, tokenize
from split import assign_splits, duplicate_groups


def test_duplicate_chains_form_one_group():
    groups = duplicate_groups(["A", "B", "C", "D"], [("B", "A"), ("C", "B")])
    assert groups["A"] == groups["B"] == groups["C"] != groups["D"]


def test_duplicate_pairs_share_a_split_and_ratios_hold():
    keys = [f"K-{i}" for i in range(200)]
    df = pd.DataFrame({"key": keys, "target_class": ["bug" if i % 2 else "feature" for i in range(200)],
                       "duplicate_of": [[f"K-{i - 1}"] if i % 10 == 1 else [] for i in range(200)]})
    split_of = assign_splits(df)
    assert all(split_of[f"K-{i}"] == split_of[f"K-{i - 1}"] for i in range(1, 200, 10))
    assert abs(sum(s == "train" for s in split_of.values()) - 140) <= 2


def test_preprocess_docs_page():
    raw = ("---\nlayout: global\ntitle: SELECT\nlicense: |\n  Apache\n---\n* This will become a table of contents (this text will be scraped).\n"
           "{:toc}\n\n# Overview\nSpark {{site.SPARK_VERSION_SHORT}} docs.\n<div data-lang=\"scala\" markdown=\"1\">\n"
           "{% include_example scala/org/apache/spark/examples/Foo.scala %}\n{% highlight python %}\n# not a header\n{% endhighlight %}\n</div>\n")
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
    docs = [tokenize(t) for t in ["dynamic partition pruning in joins", "kafka source offsets", "spark sql joins and hints"]]
    assert BM25(docs).top_k(tokenize("partition pruning join"), k=1)[0][0] == 0


def test_label_cli_parsers():
    assert parse_label("2") == "needs_development" and parse_label("out_of_scope") == "out_of_scope" and parse_label("x") is None
    assert parse_chunks("1, 3 sql-ref#002", ["a#000", "b#001", "c#002"]) == ["a#000", "c#002", "sql-ref#002"]
