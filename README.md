# Ticket Intake Assistant for Apache Spark

A chat assistant that turns a vague request ("Spark crashes when…", "it would be nice if…") into a high-quality
Apache Spark Jira ticket (bug, feature, task or idea). UCU NLP course, Assignment 1, built with CRISP-DM
(`reports/01`–`06`).

```
first message → C1 type + component (you confirm) → C2 possible duplicates (dismissable)
→ C4 which fields are missing ↔ C5 at most 2 questions per turn (max 4 turns, "skip" to stop)
→ C3 is it already supported? (feature/task/idea; a stop is offered only with a doc reference)
→ C2 full duplicate check → C6 Jira-ready ticket → you confirm or correct the assumptions → copy / download
```

| | Component | How |
|---|---|---|
| C1 | classifier | TF-IDF + logistic regression (baseline beat the LLM on val; decision M1) |
| C2 | duplicate finder | dense retrieval, `BAAI/bge-small-en-v1.5`, over 14,989 SPARK issues (M2) |
| C3 | scope checker | RAG over the Spark 4.3.0 docs + LLM, docs-grounded and precision-oriented (M3) |
| C4 | gap detector | LLM: every field confirmed / assumed / missing / unknown (M4) |
| C5 | question generator | LLM: ≤ 2 targeted questions |
| C6 | ticket composer | LLM writes the text; code assembles the ticket and enforces the rules |

The orchestration is an explicit state machine (`src/pipeline.py`), with no agent framework. Results and decisions are
in `reports/04_modeling.md`, `reports/05_evaluation.md` and `reports/decisions.md`.

## Setup
```bash
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add OPENROUTER_API_KEY (LLM calls go through OpenRouter, src/llm.py)
python -m src.llm --ping        # one call per role
```
Models per role are in `config.yaml` (generator `deepseek/deepseek-v4.1-flash-1017`, judge
`google/gemini-3.5-flash-lite`, simulator `qwen/qwen3.5-27b`; local embedder `BAAI/bge-small-en-v1.5`).

## Data (needed once; raw data is not in the repo)
```bash
python src/data/check_jira.py && python src/data/fetch_jira.py && python src/data/fetch_docs.py
python src/data/fetch_doc_tables.py         # rendered SQL function / config reference tables
python src/data/prepare.py && python src/data/split.py && python src/data/build_eval.py
python src/data/chunk_docs.py && python src/data/report_prep.py
```
`data/processed/splits.json` and `data/eval/` are frozen and tracked.

## Run the app
```bash
source .venv/bin/activate
python -m streamlit run app/streamlit_app.py   # `python -m` uses the venv even if a global `streamlit` is on PATH
```
- Run from the project's `.venv`: a global `streamlit` uses another Python and fails with `No module named 'openai'`.
- **First start: about 1 minute.** C1 is fitted on the train split and cached in `models/`; the local embedder loads, and issue and doc embeddings are encoded once and cached in `data/processed/embeddings/`.
- **Layout:**
  - left: the chat;
  - right: ticket type and component (confirm), field status, possible duplicates (Jira links, Dismiss), scope verdict (doc links; Stop / Continue when the request is already supported), and the final ticket (assumptions to confirm, copy, `.md` / `.json` download).
- **Trace:** the "Trace" expander lists every component call of the session, with input, output, latency and cost.
- **Failures:** a failed step shows a message and a Retry button; the session is kept.
- **Restart** starts a new session.

Headless use (for scripted dialogues): `src/pipeline_driver.run_dialogue(pipeline, first_message, answer_fn, Policy())`.

## Evaluation
Each component has its own eval with a `--limit N` smoke mode. Test splits are evaluated once, with an approved
`eval/<c>_final_config.json` and `--confirm-test`. Results go to `eval/results/`; one row per run goes to
`reports/05_evaluation.md`.

| Component | Command |
|---|---|
| C1 | `python eval/eval_c1.py --split val` |
| C2 | `python eval/eval_c2.py --stage variants` |
| C3 | `python eval/eval_c3.py --stage retrieval` / `--stage verdict` / `--stage compare` |
| C4 | `python eval/eval_c4.py --split dev` |
| C5 | `python eval/eval_c5.py --split dev --mode oracle` / `--mode chained` |
| C6 | `python eval/eval_c6.py --split dev` |

Human labelling tools:
- `src/data/label_cli.py` (scope labels);
- `python -m src.eval.judge_label_cli` (C3 judge calibration);
- `python -m src.eval.c4_audit_cli` (C4 leak audit).

The C4/C5/C6 ablation set is built with `python -m src.eval.build_gap_ablation`.

```bash
python -m pytest -q                  # unit tests (no LLM calls)
ruff check <files> && ruff format --check <files>
python -m src.llm --stats            # calls, cache hit rate, tokens, cost
```

## Layout
```
app/streamlit_app.py      UI
src/pipeline.py           state machine (+ pipeline_resources.py: real components, pipeline_driver.py: headless)
src/components/           C1–C6
src/prompts/              versioned prompts (one per component / judge)
src/schemas/              pydantic I/O; ticket_types.yaml = classes and fields (single source of truth)
src/retrieval/            BM25 / dense / hybrid (shared by C2, C3)
src/llm.py                the only LLM client (cache, retries, structured output, call log, Langfuse if configured)
src/data/, src/eval/      data preparation; eval helpers and labelling CLIs
eval/                     eval scripts, final configs, results/
reports/                  CRISP-DM reports and decisions.md
```
