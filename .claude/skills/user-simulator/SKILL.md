---
name: user-simulator
description: Run or extend the simulated-user end-to-end evaluation — hidden real tickets, a vague opener with a deterministic leakage check, answer rules, honesty and role checks, two driver policies, and the caveats when reading the numbers. Use for any e2e/dialogue evaluation or when changing src/eval/simulator.py or the sim_* prompts.
---

# user-simulator

> Extracted from the end-to-end evaluation of this project (`src/eval/simulator.py`, `eval/eval_e2e.py`,
> decision E2; 2026-11-15), including what went wrong in the smoke run.

## Setup
- **Role:** `simulator` in `config.yaml` (`qwen/qwen3.5-27b`, reasoning off; a different family from the generator).
- **Hidden ticket:** `ablation.ticket_text(summary, description)` (summary + the first 4,000 characters). The gold fields come from `data/eval/gap_extractions.jsonl`.
- **Driver:** `src/pipeline_driver.run_dialogue(pipeline, opener, SimulatedUser(...), Policy(...))`. Two policies:

  | Policy | Class | Use |
  |---|---|---|
  | **auto** | C1's top-1 | measures C1's cost to the dialogue |
  | **corrects** | `Policy(confirm_class=gold)` | the intended UX |

  Both: top-1 component, dismiss nothing, continue on the scope stop, accept the assumptions.

## Opener (`make_opener`, prompt `sim_opener`)
- **Input:** written from the **summary only**: one vague first-person sentence, ≤ 20 words, with no versions, error text, code or solution.
- **Deterministic leak check (`opener_leaks`):** word count; specific tokens (`risky_tokens` minus `GENERIC_TERMS`); error text (`*Exception`, `*Error`, traceback); a content-word 4-gram shared with the **description** but not the summary.
- **On failure:** regenerate **once**, with the reasons as feedback (this also changes the cache key). If it still fails, use it and flag it.

## Answers (`SimulatedUser`, prompt `sim_user` v2)
- **Rules:**
  - answer only the last question(s), in 1–2 sentences, first person, only from the hidden ticket;
  - "I don't know" otherwise; never volunteer facts;
  - never type "skip" (a guard replaces it);
  - never mention being an AI, nor **a ticket, Jira, notes or a document**.
- **Lesson:** v1 said "the ticket notes…" in 3 of 8 smoke answers. Frame the hidden text as "WHAT YOU KNOW" ("you have not written a ticket yet").

## Behaviour checks (deterministic, reported next to every result)
- **Format and role:**
  - `sentences(answer) <= 2`;
  - `AI_RE` (AI identity) and `META_RE` ("the/my ticket|Jira|notes|description|document").
- **"Don't know" checks:**
  - **"don't know" when absent:** all targeted fields gold-absent → `DONT_KNOW_RE` matches;
  - **answers when present:** all targeted fields gold-confirmed → not `dont_know_only` (a partial answer, "I don't know the version, but I built it with Maven", is correct).
- **Simulator inventions:** `invented_tokens(answer, hidden_ticket)`. These inflate the system's "invented vs hidden ticket" rate, so attribute every invented token to the system or the simulator.

## Reading the numbers: caveats we found
- **Cache:** the second policy reuses the first's cache. Latency and cost come from **auto** only.
- **Self-matches:** hidden test tickets are in C2's corpus, so the C2 alert rate in e2e is mostly self-matches (top-1 = the hidden ticket in 95%). That is evidence of faithfulness, **not** a false-alarm rate.
- **Simulator under-recall:** it sometimes says "I don't know" when the ticket has the answer. Before blaming the system, check whether a field was asked about.
- **Lexical recall:** content-word recall has no stemming or synonyms, so report it against the concise gold value and against the verbatim quotes, and look at examples (paraphrase vs real detail loss).
- **Output:** save every transcript (`e2e_transcripts_*.jsonl`) and a review file with one dialogue per class plus the worst, for the user's manual check. `--rescore` recomputes the metrics without LLM calls.
