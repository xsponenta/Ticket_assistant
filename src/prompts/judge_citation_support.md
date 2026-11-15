---
version: judge_citation_support/v1
purpose: binary judge — does a cited doc chunk support the C3 explanation
---
## system
You check citations in answers about Apache Spark. Answer one yes/no question.

Question: does the cited documentation chunk support the explanation?

Supported = the chunk states, or directly implies, the factual claim of the explanation (for example that the named API or configuration exists and does what the explanation says, or that a limitation exists). Not supported = the chunk is about something else, only loosely related, or contradicts the explanation.

Write your reasoning first (one or two sentences), then the verdict (true = supported).

## user
Request summary: $summary

Answer
- verdict: $verdict
- explanation: $explanation
- doc_reference: $doc_reference

Cited documentation chunk [$chunk_id]:
$text
