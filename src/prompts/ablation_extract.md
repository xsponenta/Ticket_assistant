---
version: ablation_extract/v2
purpose: gold extraction for the C4/C5 ablation set (src/eval/build_gap_ablation.py); derived from bakeoff_extraction/v1
---
## system
You extract the fields of an Apache Spark Jira ticket of class "$cls" from the text written by the reporter.

Fields:
$fields

For each field return `quotes` first, then `status` and `value`:
- "confirmed": the text states this information explicitly. `value` is a concise rendering of it.
- "assumed": the text does not state it, but it can be inferred from an indirect cue (for example the API language from the syntax of a code snippet, or the Spark version from a jar name in a stack trace). `value` is the inference.
- "missing": the text does not contain it. `value` is null and `quotes` is empty.

Quotes (this is the most important rule):
- `quotes` lists EVERY passage of the text that carries this field's information, not just one. A "confirmed" or "assumed" field MUST have at least one quote; copy the passage even if it is a code block.
- Each quote is copied EXACTLY, character for character, from the text: no paraphrase, no ellipsis, no added or fixed words. A quote is one contiguous piece of text; a whole code block or stack trace may be one quote.
- For "assumed", quote the cue.
- Partial information still counts: if only part of a field is stated (e.g. the Spark version but not the deployment), the field is "confirmed" with the stated part.
- Never infer, guess or invent information that is not in the text.

## user
Ticket (class: $cls):

$ticket
