# AGENTS.md — Ticket Intake Assistant (Apache Spark)

## Project
An NLP system that turns a vague request ("Spark crashes when…", "it would be nice if…")
into a high-quality Jira ticket for Apache Spark through a short chat dialogue.
Context: UCU NLP course, Assignment 1. Graded on: system understanding, working prototype,
evaluation of EVERY component, and disciplined use of a coding agent.

## Ticket types
Mapping from Jira `issuetype` (decision D1, see reports/decisions.md):

| Class | Jira types | Required fields |
|---|---|---|
| bug | Bug | summary, steps_to_reproduce, expected_behavior, actual_behavior, environment (Spark version, API language, deployment) |
| feature | New Feature, Improvement, Story | summary, motivation (user problem), proposed_behavior, acceptance_criteria |
| task | Task, Test, Documentation, Dependency upgrade | summary, goal, scope (in/out), definition_of_done |
| idea | Wish, Brainstorming | summary, problem_hypothesis, target_users, expected_impact |

All other types (incl. Sub-task) are excluded. Field definitions (required/optional, descriptions,
Spark-specific examples) live in `src/schemas/ticket_types.yaml`, the single source of truth.

## Data (done — do not rebuild without being asked)
- Raw: `data/raw/` (gitignored, never modified). Processed:
  - `data/processed/issues.parquet`: main dataset, 14,989 issues created before 2026. Non-idea classes start at 2020-01-01; idea uses all SPARK Wish history (from 2014).
  - `data/processed/drift_2026.parquet`: every issue created in 2026, all classes (3,567).
  - `data/processed/doc_chunks.jsonl`: Spark 4.3.0 docs, 2,034 chunks.
- Decisions D1–D5 are in `reports/decisions.md`. Follow them.
  - D1: the mapping in the table above.
  - D2: idea = SPARK Wish (all-time) + Brainstorming; `wish_other.jsonl` is never used.
  - D3: 2026 → drift set.
  - D4: no resampling, stratified splits, macro-F1, class weights allowed.
  - D5: PII is masked as `<EMAIL>` / `<USER>`, and URL credentials are removed.
- `data/processed/splits.json` is FROZEN. Never regenerate it.
  - Train / val / test = 70/15/15, stratified, duplicate-aware.
  - Test hash: `339455ee27a9ecde360fc82b99dc4f8475de09c2b00093744f2721b36a7e580a`.
  - Test counts: bug 806, feature 1,149, task 269, idea 24.
- Eval sets in `data/eval/` are FROZEN: classification_test, duplicates, scope_candidates, scope_labeled (manual labels by the user), simulator_candidates. See `data/eval/README.md`.
  - duplicates: a Duplicate link is undirected. The later-created issue is the query, the earlier one is gold, and the corpus is the issues created before the query.

## Components (each = separate module + its own eval)
| ID | Module | Input | Output | Model / tool |
|---|---|---|---|---|
| C1 | classifier | user text | class, Spark component, confidence | LLM few-shot; baseline TF-IDF + LogReg |
| C2 | duplicate_finder | draft summary + description | top-k earlier SPARK issues + score | BM25 + local embeddings (hybrid, RRF) |
| C3 | scope_checker | request + filled fields | verdict ∈ {already_supported, needs_development, out_of_scope, insufficient_info} + cited doc chunks | RAG over Spark docs + LLM |
| C4 | gap_detector | conversation + type schema | fields with status {confirmed, assumed, missing} | LLM structured extraction |
| C5 | question_generator | missing fields + context | ≤2 clarifying questions | LLM |
| C6 | ticket_composer | filled fields | Jira-ready markdown + JSON | LLM |

Orchestration: `src/pipeline.py`, an explicit state machine (no agent framework unless asked).
Flow: first message → C1 + C2 → loop C4→C5 (max 4 turns) → C3 (feature/task/idea only) → C6.

## CRISP-DM workflow (mandatory)
| Phase | Artifacts |
|---|---|
| 1 Business Understanding | `reports/01_business_understanding.md` |
| 2 Data Understanding | `reports/02_data_sanity.md`, `reports/02_data_understanding.md`, `notebooks/eda.ipynb` |
| 3 Data Preparation | `reports/03_data_preparation.md`, `src/data/*` |
| 4 Modeling | `reports/04_modeling.md` (one section per component) |
| 5 Evaluation | `reports/05_evaluation.md`, `eval/results/*.json` |
| 6 Deployment | `README.md`, `reports/06_deployment.md` |

Rules:
- After every task, update the report of the current phase (concise, numbers over adjectives,
  every claim references a script, notebook cell or results file).
- Log every non-trivial decision in `reports/decisions.md` (date, decision, alternatives, why).
- Going back to an earlier phase is allowed; log it as an iteration in both reports.

## Engineering rules
- Python 3.13, `.venv`, `requirements.txt`, ruff (lint + format), pytest.
- ALL LLM calls go through `src/llm.py`. Never import `openai` anywhere else.
  - API: `complete(messages, role=..., component=..., session_id=None, schema=None, temperature=None, max_tokens=None)`.
  - Models come from `config.yaml` by role (generator / judge / simulator). `temperature=None` means the role default; the judge always runs at 0.
  - Behaviour: disk cache, retries with backoff, JSON output validated into pydantic models (one repair retry).
  - Every call is logged to `logs/llm_calls.jsonl`. Langfuse tracing runs only if keys are set.
  - `complete()` is thread-safe: eval scripts may parallelise with a `ThreadPoolExecutor` (4–8 workers).
  - Components always select models through `role`. Only experiment scripts (e.g. `scripts/model_bakeoff.py`) may use the `model=` / `reasoning=` overrides.
- Retrieval: `src/retrieval/` (BM25, dense with a local embedder, hybrid RRF; Jira-key masking) is shared by C2 and C3. Corpus embeddings are cached in `data/processed/embeddings/` (embedder: `models.embedder`, L3).
- Models: OpenRouter ids in `config.yaml`, chosen by the user from `scripts/list_models.py`. Never pick or change models yourself. The `embedder` is a local model and is not called through `src/llm.py`.
- Prompts live in `src/prompts/<component>.md` with a version header. Never inline prompt strings.
- Component I/O = pydantic models in `src/schemas/`. Components never import each other;
  only `pipeline.py` composes them.
- Secrets only in `.env` (never commit).
- Deterministic code gets unit tests. LLM behaviour is checked by eval scripts, not unit tests.
- Small functions, no dead code. Justify any new dependency in your final message.

## Evaluation rules
- NEVER edit a frozen eval set to improve a score. NEVER use test-split items as few-shot examples
  or for tuning (thresholds, prompts) — use train/val.
- Each component: `eval/eval_<component>.py` (with `--limit N` for smoke runs)
  → `eval/results/<component>_<timestamp>.json` (metrics, n, models, prompt versions, git commit,
  per-item outputs) → one row in `reports/05_evaluation.md`
  (date, component, metric, value, n, model, prompt version, note).
- Always show ≥3 worst examples with a hypothesis why they failed.
- Before a run with >300 LLM calls, report the estimate and wait for approval.
- Prefer deterministic metrics (grounding check, field presence, schema checks) wherever possible; use an
  LLM judge only where nothing deterministic works.
- Judge rubric: write the rubric with explicit edge cases (absence claims, partial support, paraphrase) into the
  judge prompt AND show the same rubric on screen in any calibration CLI, so the human labels against the same
  definition (lesson from C3: κ < 0 from a criterion mismatch, see decisions.md L2 update).
- LLM-as-judge: prompts in `src/prompts/judge_*.md`, binary questions where possible, otherwise an
  anchored 1–5 rubric; reasoning before score; temperature 0; judge model ≠ generator model;
  calibrate against human scores and report agreement.
- Seed 42. Report n; bootstrap 95% CI where cheap (mandatory for idea, n=24 in test).

## Agent behaviour
- Tasks touching >2 files: propose a short plan first and wait for approval.
- Before finishing: run ruff + pytest, then report briefly: what changed, how to run it,
  what I should verify manually, suggested next step.
- If data or API access fails: stop and report. Never fabricate data. Synthetic data only when
  explicitly requested, marked `synthetic: true`.
- Ambiguous requirement → ask, don't guess.

## Commands
- Setup: `source .venv/bin/activate && pip install -r requirements.txt && cp .env.example .env` (add `OPENROUTER_API_KEY`)
- Tests: `python -m pytest -q`
- Lint: `ruff check <files> && ruff format --check <files>`. Ruff is applied to new and changed files. Code written before ruff was added (`src/data/`, older tests) is not reformatted yet.
- LLM:
  - `python scripts/list_models.py`: candidate models and prices.
  - `python -m src.llm --ping`: one call per role.
  - `python -m src.llm --stats`: calls, cache hit rate, tokens and cost.
- Data pipeline: `python src/data/prepare.py` → `split.py` (frozen check) → `build_eval.py`
  → `chunk_docs.py` → `report_prep.py`
- Scope labeling (user only): `python src/data/label_cli.py`
- App (later): `streamlit run app/streamlit_app.py`
- Evals (later): `python -m eval.run_all`