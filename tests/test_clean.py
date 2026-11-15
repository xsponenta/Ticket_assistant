"""Tests for src/data/clean.py. Inputs are real snippets from data/raw (issue key in each test name/comment);
user names and e-mail addresses were replaced with placeholders."""

from clean import clean_description, clean_summary, jira_to_markdown, mask_pii


def test_code_block_glued_to_text_becomes_fenced_block():  # SPARK-31968
    raw = 'For example: \r\n{code:java}\r\ndf.write\r\n  .partitionBy("col1", "col1")  // twice\r\n  .csv("output_dir"){code}\r\nThe above code will produce'
    out = clean_description(raw)
    assert out == (
        "For example:\n\n```java\ndf.write\n  .partitionBy(\"col1\", \"col1\")  // twice\n  .csv(\"output_dir\")\n```\n\n"
        "The above code will produce"
    )


def test_noformat_block_keeps_content_verbatim():  # SPARK-37222
    raw = "it will throw an exception:\r\n{noformat}\r\ncase class Nested(b: Boolean, n: Long)\r\n\r\nlocally {\r\n  h1. not a heading\r\n}{noformat}"
    out = clean_description(raw)
    assert "```\ncase class Nested(b: Boolean, n: Long)\n\nlocally {\n  h1. not a heading\n}\n```" in out


def test_code_language_from_parameters():
    assert "```scala\n" in jira_to_markdown("{code:title=A.scala|language=scala}val x = 1{code}")
    assert "```\nSELECT 1\n```" in jira_to_markdown("{code:none}SELECT 1{code}")


def test_heading_and_jira_numbered_list():  # SPARK-44087 / SPARK-31621
    raw = "h3. How to reproduce?\r\n # Follow the [https://kafka.apache.org/quickstart] to start the kafka broker.\r\n # Load Spark Master UI again.\r\n ** nested bullet"
    out = clean_description(raw)
    assert out.splitlines() == [
        "### How to reproduce?",
        "1. Follow the <https://kafka.apache.org/quickstart> to start the kafka broker.",
        "1. Load Spark Master UI again.",
        "  - nested bullet",
    ]


def test_bold_line_is_not_a_list():  # SPARK-31621
    assert clean_description("*Expected Behavior:* Spark Master UI should launch.") == "*Expected Behavior:* Spark Master UI should launch."


def test_links_with_text_and_bare_links():  # SPARK-37050, SPARK-38580
    raw = "as discussed [here|https://github.com/apache/spark-website/pull/361#issuecomment-945660978]. introduced by this PR [https://github.com/apache/spark/pull/28208]"
    assert clean_description(raw) == (
        "as discussed [here](https://github.com/apache/spark-website/pull/361#issuecomment-945660978). "
        "introduced by this PR <https://github.com/apache/spark/pull/28208>"
    )


def test_link_whose_text_is_the_url():  # SPARK-36024
    raw = "will be deleted on Jul 1, 2021 [https://registry.opendata.aws/landsat-8/|https://registry.opendata.aws/landsat-8/]"
    assert clean_description(raw).endswith("[https://registry.opendata.aws/landsat-8/](https://registry.opendata.aws/landsat-8/)")


def test_quote_and_bq_become_blockquotes():  # SPARK-31113, SPARK-35028
    raw = "comment:\r\n{quote}Tableau and PowerBI do not work with Spark 3.0.\r\n\r\nWhen we switch to Hive 2.3 profile{quote}\r\nbq. Each <grouping column reference> shall unambiguously reference a column."
    out = clean_description(raw)
    assert "> Tableau and PowerBI do not work with Spark 3.0.\n>\n> When we switch to Hive 2.3 profile" in out
    assert "> Each <grouping column reference> shall unambiguously reference a column." in out


def test_monospace_and_editor_artifacts():  # SPARK-55056, SPARK-30938
    raw = "the buffer must contain {{{}[0]{}}}. Then {{getBufferSizeFor(0)}} returns 0; {\\{BinaryClassificationMetrics}} fails"
    assert clean_description(raw) == "the buffer must contain `[0]`. Then `getBufferSizeFor(0)` returns 0; `BinaryClassificationMetrics` fails"


def test_color_tags_are_stripped():  # SPARK-37703
    raw = "which includes a fix for CVE-2021-45105{color:#172b4d}.{color}\r\n\r\nhttps://github.com/sbt/sbt/releases/tag/v1.5.8"
    assert clean_description(raw) == "which includes a fix for CVE-2021-45105.\n\nhttps://github.com/sbt/sbt/releases/tag/v1.5.8"


def test_table_header_and_image():  # SPARK-33542, SPARK-30974
    raw = "||Filename||Count||\r\n|ExternalCatalog.scala|4|\r\n\r\n!image-2020-02-27-20-07-03-701.png|thumbnail!"
    out = clean_description(raw)
    assert out.splitlines()[:3] == ["| Filename | Count |", "|---|---|", "|ExternalCatalog.scala|4|"]
    assert out.endswith("![](image-2020-02-27-20-07-03-701.png)")


def test_email_and_mailto_are_masked():  # SPARK-35396 (address replaced)
    raw = "Signed-off-by: Jane Doe [jane.doe@example.org|mailto:jane.doe@example.org]"
    assert clean_description(raw) == "Signed-off-by: Jane Doe [<EMAIL>](mailto:<EMAIL>)"


def test_jira_mentions_are_masked():  # SPARK-31879 (user names replaced)
    assert clean_description("custom locale supported.\r\n\r\ncc [~alice] [~bob_smith] [~carol.x@apache.org]\r\n") == (
        "custom locale supported.\n\ncc <USER> <USER> <USER>"
    )


def test_github_mention_masked_in_prose_but_not_in_code():  # SPARK-55552, SPARK-36875
    raw = "A reviewer (@some-reviewer) asked. {{ @Override public Row call(Row v1) }}\r\n{code:java}\r\n@since(\"3.0\")\r\n@transient val x = 1\r\n@alice\r\n{code}\r\nUse @udf(returnType) or @Override in prose."
    out = clean_description(raw)
    assert "A reviewer (<USER>) asked." in out
    assert "`@Override public Row call(Row v1)`" in out
    assert "@since(\"3.0\")\n@transient val x = 1\n@alice" in out  # code untouched
    assert "Use @udf(returnType) or @Override in prose." in out


def test_url_credentials_removed_other_uris_kept():  # SPARK-46860, SPARK-31898, SPARK-47957
    raw = (
        "401 for URL: https://username:password@domain.com/application/pysparkjob.py\r\n"
        "--driver-url spark://CoarseGrainedScheduler@driver-svc.spark-apps.svc:7078\r\n"
        'path = f"abfss://container@account.dfs.core.windows.net/path/x.xlsx"'
    )
    out = mask_pii(raw)
    assert "https://domain.com/application/pysparkjob.py" in out
    assert "spark://CoarseGrainedScheduler@driver-svc.spark-apps.svc:7078" in out
    assert "abfss://container@account.dfs.core.windows.net/path/x.xlsx" in out
    assert "<EMAIL>" not in out


def test_email_inside_code_is_masked():  # SPARK-43816 (address replaced)
    raw = '{code:json}\r\n{ "Name": "Robert", "Email": "bob@gmail.com" }\r\n{code}'
    assert '"Email": "<EMAIL>"' in clean_description(raw)


def test_whitespace_normalisation():
    raw = "﻿First  line   with spaces   \r\n\r\n\r\n\r\nSecond\tline \r\n{code}\r\n    indented  code   \r\n{code}\r\n\r\n"
    assert clean_description(raw) == "First line with spaces\n\nSecond\tline\n\n```\n    indented  code\n```"


def test_unclosed_code_block_runs_to_end():
    out = clean_description("Repro:\r\n{code:sql}\r\nSELECT * FROM t\r\nh2. still code")
    assert out == "Repro:\n\n```sql\nSELECT * FROM t\nh2. still code\n```"


def test_summary_cleaning():
    assert clean_summary("  Ping [~alice]  about   {{df.cache()}}  ") == "Ping <USER> about {{df.cache()}}"


def test_empty_inputs():
    assert clean_description(None) == "" and clean_description("  \r\n ") == "" and clean_summary(None) == ""
