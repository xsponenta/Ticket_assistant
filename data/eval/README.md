# Evaluation sets (`data/eval/`)

Built by `python src/data/build_eval.py` from `data/processed/issues.parquet` (main dataset, decisions D1–D3,
text cleaned and PII-masked per D5) and the **frozen** `data/processed/splits.json` (seed 42).
All text fields are Markdown (`description_md`) and already masked (`<EMAIL>`, `<USER>`). Selections use
`random.Random(42)` over sorted keys, so rebuilding gives the same files.

| File | Rows | Source | Labels (source) |
|---|---:|---|---|
| `classification_test.jsonl` | 324 | test split | `labels.target_class` (Jira issue type → D1 mapping), `labels.components` (Jira components) |
| `duplicates.jsonl` | 248 | whole main dataset | `gold` = the earlier issue of a Jira `Duplicate` link (undirected); `null` for non-duplicate queries |
| `scope_candidates.jsonl` | 80 | test split first, then val/train | none yet — labelled manually with `src/data/label_cli.py` → `scope_labeled.jsonl` |
| `simulator_candidates.jsonl` | 60 | test split | none — candidates; the final selection is made later with an LLM |
| `gap_ablation.jsonl` (+ `gap_extractions.jsonl`, `gap_ablation_meta.json`) | 303 dev + 301 test | 58 rich val tickets (dev) + the 60 simulator candidates (test) | gold missing / present / unknown fields per item, from a generator extraction with verbatim quotes (10 extractions reviewed by the assistant; not confirmed by the user) |

## classification_test.jsonl
- Test split, at most 100 issues per class, sampled at random; all idea issues because the class is smaller.
  Per class: bug 100, feature 100, task 100, idea 24. Includes 82 issues with an empty description (summary-only tickets are a real input).
- Fields: `key, summary, description_md, has_description, created, labels{target_class, components}, meta{issuetype, resolution, split}`.
  `meta.issuetype` is the label source and `meta.resolution` is post-hoc information — **never feed `meta` to a model**.

## duplicates.jsonl
- A Jira `Duplicate` link is treated as **undirected**: of the two linked issues, the **later-created one is the query**
  and the **earlier one is gold** — a user writing a new ticket must find the existing one. Both issues must be in the
  main dataset. (182 linked pairs; in 61 of them Jira marks the *earlier* issue as the duplicate, i.e. the
  Jira direction is the opposite of the query direction used here.)
- Retrieval corpus for a query = main-dataset issues with `created < corpus_created_before` (the query's creation time),
  so the gold issue is always in the corpus.
- Exclusion: **25 pairs whose normalised summaries are identical** (lower-case, non-alphanumerics removed) — trivial matches.
- 148 duplicate queries (5 are linked to several earlier issues: `gold` = the oldest, `gold_all` = all) and
  100 non-duplicate queries (`gold: null`): issues with no Duplicate link in either direction, not resolved as
  Duplicate, created ≥ 2020-04-01, sampled at random.
- Queries come from all splits (field `split`), because duplicate retrieval is not trained on the classification data.
  Filter on `split == "test"` if a strictly held-out subset is needed (35 duplicate queries).
- Fields: `kind, query_key, query_summary, query_description_md, query_created, query_class, split, gold, gold_all, gold_summary, corpus_created_before`.

## scope_candidates.jsonl
- 80 resolved feature/idea issues with a non-empty description: fixed 25 (Fixed), declined 25 (Won't Fix / Won't Do / Later), not_a_problem_or_invalid 25 (Not A Problem / Invalid), incomplete 5 (Incomplete).
- Drawn from the test split; a bucket is topped up from val, then train, only if the test split is too small (field `split`).
- `resolution_hint` is the Jira resolution — a **hint, not a label**. Labels come from manual annotation
  (`already_supported`, `needs_development`, `out_of_scope`, `insufficient_info`) with `src/data/label_cli.py`.

## simulator_candidates.jsonl
- Test-split issues with rich descriptions: bug = at least 3 of the 4 EDA bug signals (repro, expected, actual,
  version/env; stored in `bug_signals`), other classes = at least 80 words. At most 15 per class.
  Per class (selected / eligible): bug 15/135, feature 15/227, task 15/24, idea 15/15.
- Candidates only; the final selection is made later with an LLM.

## scope_labeled.jsonl (manual, 2026-11-15)
- **What:** 80 / 80 scope candidates labelled by the user with `src/data/label_cli.py`, judged against the Spark 4.3.0 docs. 31 labels cite supporting doc chunks.
- **Labels:** already_supported 42, needs_development 28, out_of_scope 8, insufficient_info 2. Majority-class accuracy is **0.525**, the C3 reference point.
- **Agreement with the Jira resolution hint:** 0.19 (mapping in `label_cli.py`, `HINT_TO_LABEL`). It is low by design: the resolution describes the ticket *when it was filed*, the label describes Spark *today*. For example, 16 of 25 *Fixed* requests are `already_supported` now.
- **Summary:** `eval/results/scope_labels_summary_20261115.json` (`python src/data/label_cli.py --summary`).

## gap_ablation.jsonl (C4/C5, frozen 2026-11-15)
Built by `python -m src.eval.build_gap_ablation` (`--extract` → `--show 10` spot check → `--build`); `--build` refuses
to overwrite. The test items are hashed in `gap_ablation_meta.json` (`test_sha256`), checked before every test run.
- **Tickets:**
  - dev: rich val tickets chosen with the simulator-candidate rule (bug ≥ 3 of 4 `bug_signals`; other classes ≥ 80 words; seed 42, ≤ 15 per class). That gives bug / feature / task 15, idea 13 (all rich val ideas);
  - test: the 60 `simulator_candidates` (also the e2e candidates later; both uses are test-only).
- **Ticket text:** `Summary: …\n\nDescription:\n<first 4,000 characters>`.
- **Gold extraction** (`gap_extractions.jsonl`, prompt `ablation_extract/v2`, role generator, one call per ticket):
  - per class field: `quotes` (every verbatim passage that carries it), `status` (confirmed / assumed / missing) and `value`;
  - each quote is located deterministically (`src/eval/spans.py`: exact, else whitespace-flexible).
  - **Excluded from scoring:** fields marked `assumed` or with an unlocatable quote (gold uncertain): 55 field slots over 118 tickets.
- **Variants** (dev / test items):
  - `original` (58 / 60);
  - `minus_<f>` / `minus_<f>_<g>` (141 / 139): every passage of 1–2 required fields deleted;
  - `answered_<f>` (52 / 51): the assistant asks about *f*, and the user replies with the deleted text;
  - `unknown_<f>` (52 / 51): the user replies "I don't know" (3 fixed phrasings).
- **Gold:**
  - `gold_missing` = deleted fields ∪ fields missing in the original;
  - `gold_unknown` = *f* for `unknown_<f>` items;
  - `gold_present` = the other confirmed fields;
  - `excluded_fields` are not scored.
- **Rules (user decision 2026-11-15):**
  1. If deleting *f* also removes part of another field's text, that other field is **left out of scoring for this variant** (`excluded_fields`), so **no half-deleted field is ever scored**. On average 0.98 fields per item are excluded (both kinds).
  2. **Text is never deleted from the title:** a field quoted in the title is not deletable, because a real conversation always starts with a title.
  3. A deletion must leave ≥ 20 description words.
- **Limitations:**
  - gold comes from the same model family as C4 (circularity; mitigated by verbatim quotes and a review of 10 extractions; the 10 spot-check extractions (`eval/results/gap_spotcheck_20261115T164526Z.md`) were reviewed by the assistant, not confirmed by the user: no quote assigned to the wrong field; 2 doubtful values (SPARK-33121 environment says "Java API" for Scala code in a ```java fence; SPARK-52965 environment quotes a sentence about the failure));
  - a deleted field can sometimes still be inferred from what remains, so C4 is also scored with "missing + assumed" as the positive class.
