# 06 · Deployment

## Running the app
- **Command:** `source .venv/bin/activate && python -m streamlit run app/streamlit_app.py`. Setup, data pipeline and evals are in [`README.md`](../README.md). Use `python -m streamlit` so the venv's Python runs the app: a global `streamlit` fails with `No module named 'openai'`.
- **Runtime requirements:**
  - Python 3.13 + `requirements.txt` (`streamlit>=1.50`);
  - `OPENROUTER_API_KEY` in `.env` (only C3–C6 call an LLM, through `src/llm.py`);
  - CPU only (local `BAAI/bge-small-en-v1.5` embedder, TF-IDF classifier);
  - `data/processed/` (issues, doc chunks) and the embedding caches in `data/processed/embeddings/` (about 28 MB: issues 23 MB, doc chunks 4.5 MB).
- **First start: about 25 s** (measured; components loaded in 23 s): C1 is fitted on train and cached as `models/c1_baseline_full.joblib`, and the embedder loads. Without embedding caches, the corpus is encoded once (several minutes on CPU). Later starts reuse the caches.

## Cost and latency per ticket
End-to-end test, 60 dialogues, uncached (`eval/results/e2e_test_20261115T181923Z.json`):
- **$0.0013 per ticket** (target ≤ $0.01);
- per user turn **p50 2.6 s, p95 6.9 s** (target ≤ 8 s);
- 2.3 typed user turns on average.

C1 and C2 add under 0.2 s and no cost. The real session in `REPORT.md` §5 cost $0.0012 for 6 LLM calls.

## Known risks and mitigations

| Risk | Evidence | Mitigation in the product |
|---|---|---|
| **C1 is unreliable on short openers** | top-1 0.43, top-2 0.60 on one-sentence openers (e2e); idea recall 0.17 (test) | The user confirms the type, from the top-2 or any of the four (M1); this raises field recovery from 0.46 to 0.95 in e2e |
| **C2 false alarms on a short first message**; self-matches inflate e2e alert rates | false alarms on test 0.19 (summary-only) / 0.25 (full); 95% self-matches of the hidden tickets in e2e | Pass 1 shows "related issues" **without an alert**; only pass 2 (full description, 0.839) may alert; both are dismissable (M2, M6) |
| **C3 has low recall** of "already supported" | accuracy 0.32, recall 0.19; precision 0.625 with 8/8 claims grounded | A stop is offered only for a **grounded** `doc_reference` (M3); a failed C3 call continues to the ticket (M7) |
| **Fact recall is measured lexically** | content-word recall 0.43 vs ≥ 0.80; it mixes paraphrase with real detail loss | Read it with the transcripts (`e2e_review_*.md`); assumed values are shown for confirmation (M4) |
| **Inference stated as fact** (C4 confirms what is only inferable) | corrected false-confirmed 0.31 on deleted fields (audit) | "Assumptions to confirm" for `assumed` fields; remaining risk documented |

## Monitoring
- **Per session:** the app's **Trace** expander lists every step (component, latency, cost, cache hit, input / output summary, errors); a failed step shows a Retry message.
- **Across sessions:** every LLM call is appended to `logs/llm_calls.jsonl` (session id `app|<session>|<step>|<n>`, model, tokens, cost, latency, cached, repair, error). `python -m src.llm --stats` summarises calls, the cache hit rate, tokens and cost.
- **Langfuse** tracing runs if its keys are set.
- **What to watch:**
  - C3 schema failures (`already_supported` without a reference);
  - repairs and failures of C4 / C6;
  - p95 latency;
  - cost per session.

## Second iteration
1. **Expert relabelling of the scope set** (80 items, at least 2 Spark experts, a written definition of "supporting chunk") and re-evaluation of C3.
2. **Judge calibration with a written rubric:** one definition with edge cases (absence claims, partial support, paraphrase) in both the judge prompt and the labelling CLI, then calibration on new pairs (κ ≥ 0.6).
3. **Paraphrase-aware fact recall:** an embedding- or NLI-based match of the gold facts, calibrated against human judgements, next to the lexical recall.
4. **LLM fallback for C1 on new vocabulary:** use the LLM classifier when the baseline is uncertain or the text is out of vocabulary (2026 drift: component top-1 dropped to 0.64). Decide this on val or a new drift slice.
