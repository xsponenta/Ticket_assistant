## Review and recommendation (hand-written, 2026-11-15)

_This section is written by hand and inserted with `--review reports/model_selection_review.md`. The tables above are generated._

### What changed between runs
1. **Parser bug in `src/llm.py`, now fixed.**
   - The bug: valid JSON replies were rejected when a field value contained a Markdown code block, e.g. `"steps_to_reproduce": "```python …```"`. The parser extracted the inner code block instead of the JSON.
   - Effect on the first full run: extraction validity was understated (e.g. seed-2-1-turbo 30% → 100% first-try valid), and 6 of the 7 failures were caused by this bug (the seventh was a reply that wasn't a JSON object).
   - All first replies were re-parsed from the cache. The rerun cost $0.008. Regression tests were added in `tests/test_llm.py`.
2. **Simulator checks revised after reading the transcripts (v1 → v2).** The automatic checks were changed *after* reading the v1 transcripts and *before* any model was chosen. Two v1 checks measured the heuristic, not the models:
   - **Q1 "volunteered version".** In v1 it counted any Spark version in the answer to Q1 (expected vs actual behaviour). In 3 of the 5 tickets, the expected behaviour itself is a version regression ("percentile_approx regression since Spark 2.4"), so naming the version is the honest answer. Every configuration failed v1 on exactly those 3 tickets (40% pass rate for all 10), which capped all of them at 80% in character. **v2** counts only environment details that were not asked for (Python/Java/Scala versions, YARN, Kubernetes, EMR, …), not Spark versions.
   - **Q3 "admits not knowing".** The v1 phrase list missed honest answers such as "I don't have information about the number of nodes" and "I don't have those details". It also counted ticket-grounded answers as dishonest (e.g. "I ran it locally in spark-shell" when the ticket says so). **v2** accepts these phrasings, and accepts local / single-node / Docker / spark-shell answers **only if the ticket mentions them**. Invented numbers still fail.

   v2 is not lenient across the board: qwen3.5-9b still fails Q3 on SPARK-51533 because "I am running this locally" is not in its ticket. The one remaining miss for seed-2-1-turbo (as served) is a false negative of the v2 phrase list. All transcripts are in the transcripts file, with the checks each reply failed.
3. **Total bake-off spend:** $1.25 (smoke runs $0.15 + full run $1.09 + rerun $0.008).

### Findings
- **Classification does not separate the models.**
  - Macro-F1 ranges from 0.36 to 0.44, and all 95% CIs overlap.
  - No configuration ever predicted *idea* correctly: 82 of the 100 idea predictions across configs went to *feature*.
  - 18 of the 40 items are wrong for every configuration.

  This is a problem with the label definition for C1: SPARK Wish tickets read like concrete feature requests. It is not a model difference, so classification should not drive the model choice. C1 needs few-shot examples from **train** and a revised idea definition.
- **Reasoning does not pay off for these tasks.** The reasoning-minimised variants match the as-served ones on macro-F1 and extraction validity, at 4–7× lower cost (glimpse, qwen3.5-27b, seed) and with 1.3–6× lower p50 latency. One exception: glimpse with reasoning minimised produces 3 possibly-invented fields, against 1.
- **OpenRouter's reasoning metadata is unreliable.** glimpse, qwen3.5-27b and seed-2-1-turbo are listed as reasoning *off*, yet as served they produced 56k–142k reasoning tokens. Every role should set `reasoning` explicitly.
- **Grounding.** gemini-3.5-flash-lite and both DeepSeek variants: 100% grounded, 0 flags. The flags I reviewed are real inferences, not word-matching artefacts:
  - qwen3.5-9b: "inferred production cluster based on data size…";
  - glimpse@min: "Spark 3.0+ (implied by warning message)".

  The flag on seed's `expected_behavior` is a borderline paraphrase of an implicit expectation. Gemini marked that same field *missing*.
- **Simulator.** Every configuration stays in character.
  - qwen3.5-9b's one miss is real: "I am running this locally" is not in the ticket.
  - seed-2-1-turbo's miss is a heuristic false negative: "I don't have the exact cluster node count…" is honest.

### Recommendation (differs from the rule for the judge)

| Role | Recommended | Why |
|---|---|---|
| generator | `deepseek/deepseek-v4.1-flash-1017` with `reasoning: {"effort": "none"}` | The rule's pick. $0.016 per 100 calls, p50 1.0 s / p95 2.9 s, 100% first-try valid, 0 possibly-invented fields, simulator 5/5. |
| judge | `google/gemini-3.5-flash-lite` | Different provider. 100% first-try valid, 0 possibly-invented fields, 100% grounded, simulator 5/5, p95 1.9 s, $0.058 per 100 calls. The rule picked qwen3.5-9b only for the highest macro-F1, which is noise here (CI 0.32–0.55 overlaps every config); qwen3.5-9b also has the most possibly-invented fields (4). Caveat: a "lite" model. AGENTS.md requires calibrating the judge against human scores; if agreement is low, switch to a strong-tier judge (e.g. `anthropic/claude-fable-5.2`). |
| simulator | `qwen/qwen3.5-9b` (the rule's pick); alternative `qwen/qwen3.5-27b` with reasoning off | qwen3.5-9b is the cheapest ($0.0046 per 100 calls), stays in character in 93% of replies, and invented one fact in 15 replies. It is a third provider, different from both generator and judge. qwen3.5-27b with reasoning off scores 100% in character and 5/5 honesty at $0.056 per 100 calls: choose it if a simulator that never invents facts matters more than a negligible cost difference. |

### Needed before `config.yaml` can be updated
- **Per-role reasoning setting.** `config.yaml` has none, and the recommended generator needs `{"effort": "none"}`.
- **Proposal:** add `reasoning: {generator: …, judge: …, simulator: …}` to `config.yaml`, used by `src/llm.py` as the role default (like temperature).
- **Timing:** done together with L2, after confirmation.

### Confirmed decision (2026-11-15, logged as L2 in `reports/decisions.md`)

| Role | Model | Reasoning |
|---|---|---|
| generator | `deepseek/deepseek-v4.1-flash-1017` | off (`{effort: none}`) |
| judge | `google/gemini-3.5-flash-lite` | `{effort: minimal}` (mandatory reasoning; lowest effort) |
| simulator | `qwen/qwen3.5-27b` | off (`{enabled: false}`) |

- **Judge:** the rule's pick was overridden (see above). It must be calibrated against human scores before its numbers are reported.
- **Simulator:** `qwen3.5-27b` was chosen over the cheaper `qwen3.5-9b` because honesty matters more than about $0.05 per 100 calls. An invented fact would corrupt the end-to-end fact-recall and hallucination metrics, and this is also a different family from the generator.
- **Configuration:** the per-role reasoning settings are in `config.yaml` (`reasoning.<role>`), and `src/llm.py` reads them like temperature.
