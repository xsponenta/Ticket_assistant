"""Ticket Intake Assistant for Apache Spark — Streamlit UI over src/pipeline.py.

    streamlit run app/streamlit_app.py

Left: the chat. Right: ticket type and component, field status, duplicate candidates, scope verdict, final ticket.
The "Trace" expander lists every component call of the session (input, output, latency, cost).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:  # a global `streamlit` runs another Python without the project's packages
    import openai  # noqa: F401
except ModuleNotFoundError:
    st.error(
        "This Python lacks the project's packages. Start the app from the project virtualenv:\n\n"
        "`source .venv/bin/activate && python -m streamlit run app/streamlit_app.py`"
    )
    st.stop()

from src.pipeline import Pipeline  # noqa: E402
from src.schemas.c1 import COMPONENTS  # noqa: E402
from src.schemas.pipeline import SessionState  # noqa: E402
from src.schemas.ticket_fields import CLASSES, fields_for, heading  # noqa: E402

BADGES = {"confirmed": "🟢 confirmed", "assumed": "🟡 assumed", "unknown": "⚪ unknown", "missing": "🔴 missing"}
NOT_PROVIDED = "▫️ not provided"  # M6: a missing OPTIONAL field is not an error
BUSY = "Working… (first run: loading models can take about a minute)"

st.set_page_config(page_title="Spark Ticket Intake", page_icon="🐞", layout="wide")


@st.cache_resource(show_spinner=BUSY)
def get_pipeline() -> Pipeline:
    from src.pipeline_resources import load_components

    return Pipeline(load_components())


def state() -> SessionState:
    if "state" not in st.session_state:
        st.session_state.state = get_pipeline().new_session()
    return st.session_state.state


def act(fn, *args) -> None:
    """Run a pipeline action (it never raises: failures land in state.last_error) and redraw."""
    with st.spinner("Working…"):
        st.session_state.state = fn(state(), *args)
    st.rerun()


def ticket_markdown(ticket: dict) -> str:
    return f"# {ticket['title']}\n\n{ticket['body_markdown']}"


# ---------------------------------------------------------------- header

top = st.columns([6, 1])
top[0].title("🐞 Spark Ticket Intake Assistant")
if top[1].button("Restart", width="stretch"):
    st.session_state.state = get_pipeline().new_session()
    st.rerun()
pipeline, s = get_pipeline(), state()
left, right = st.columns([3, 2], gap="large")

# ---------------------------------------------------------------- chat (left)

with left:
    if not s.chat:
        st.info("Describe the problem or idea in your own words, e.g. *“Spark crashes when I join two DataFrames…”*")
    for message in s.chat:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    if s.last_error:
        st.error(f"Step **{s.last_error['step']}** failed: {s.last_error['message']}")
        if st.button("Retry", type="primary"):
            act(pipeline.retry)
    if s.stage == "intake":
        if text := st.chat_input("Describe your request…"):
            act(pipeline.start, text)
    elif s.stage == "asking":
        if text := st.chat_input("Answer the questions, or type skip"):
            act(pipeline.answer, text)

# ---------------------------------------------------------------- panel (right)

with right:
    # 1. ticket type and component
    st.subheader("1 · Ticket type")
    if s.stage == "confirm_class":
        options = [c for c, _ in s.class_candidates] + [c for c in CLASSES if c not in dict(s.class_candidates)]
        probs = dict(s.class_candidates)
        cls = st.radio(
            "Type (top 2 from the classifier first)",
            options,
            format_func=lambda c: f"{c} ({probs[c]:.0%})" if c in probs else c,
            horizontal=True,
        )
        component = st.multiselect(
            "Component",
            COMPONENTS,
            default=s.component_candidates[:1],
            help="Suggested: " + ", ".join(s.component_candidates),
        )
        if st.button("Confirm", type="primary", disabled=not component):
            act(pipeline.confirm_class, cls, component)
    elif s.ticket_class:
        st.markdown(f"**{s.ticket_class}** · {', '.join(s.component)}")
    else:
        st.caption("Waiting for your first message.")

    # 2. field status
    if s.field_states and s.ticket_class:
        st.subheader("2 · Fields")
        rows = []
        for f in fields_for(s.ticket_class):
            fs = s.field_states.get(f.name, {})
            status = fs.get("status", "missing")
            if f.name == "labels" and status == "missing":
                continue  # M6: labels only when set
            badge = NOT_PROVIDED if status == "missing" and not f.required else BADGES.get(status)
            value = " ".join(str(fs.get("value") or "").split())[:120]
            rows.append({"field": f.name, "required": "yes" if f.required else "", "status": badge, "value": value})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    # 3. duplicates (non-blocking, M2; M6: pass 1 = related issues without an alert, only pass 2 may alert)
    c2 = s.c2_pass2 or s.c2_pass1
    if c2:
        title = "Possible duplicates (full check)" if s.c2_pass2 else "Related issues you may want to check"
        st.subheader(f"3 · {title}")
        candidates = [c for c in c2["candidates"] if c["key"] not in s.dismissed]
        if s.c2_pass2 and c2["alert"] and candidates:
            st.warning("This looks very similar to an existing issue — please check before filing.")
        for c in candidates:
            row = st.columns([5, 1])
            row[0].markdown(f"[{c['key']}]({c['url']}) {c['summary']} · score {c['score']:.2f}")
            if row[1].button("Dismiss", key=f"dismiss-{c['key']}"):
                act(pipeline.dismiss, c["key"])
        if not candidates:
            st.caption("No candidates left.")

    # 4. scope (C3, M3)
    if s.c3 and s.c3.get("failed"):
        st.subheader("4 · Already supported?")
        st.caption("The documentation check failed, so we continue to the ticket (see Trace).")
    elif s.c3:
        st.subheader("4 · Already supported?")
        verdict = s.c3["verdict"].replace("_", " ")
        st.markdown(f"**{verdict}** — {s.c3['explanation']}")
        if s.c3.get("doc_reference"):
            st.markdown(f"Reference: `{s.c3['doc_reference']}`" + (" ✅ found in the docs" if s.c3["grounded"] else ""))
        cited = [c for c in s.c3["chunks"] if c["chunk_id"] in s.c3["cited_chunk_ids"]]
        for c in cited:
            st.markdown(f"- [{c['chunk_id']}]({c['url']})")
        if s.stage == "scope_decision":
            b = st.columns(2)
            if b[0].button("Stop — no ticket needed"):
                act(pipeline.scope_decision, True)
            if b[1].button("Continue to a ticket", type="primary"):
                act(pipeline.scope_decision, False)

    # 5. ticket (C6, M4)
    if s.ticket:
        st.subheader("5 · Ticket")
        assumed = [n for n, f in s.ticket["fields"].items() if f["status"] == "assumed"]
        if s.stage == "confirm_assumptions" and assumed:
            st.info("Assumptions to confirm: edit a value to correct it, or keep it, then confirm.")
            corrections = {}
            for name in assumed:
                value = s.ticket["fields"][name]["value"]
                edited = st.text_area(heading(name), value=value, key=f"assume-{name}")
                corrections[name] = edited if edited.strip() != (value or "").strip() else None
            if st.button("Confirm assumptions", type="primary"):
                act(pipeline.confirm_assumptions, corrections)
        markdown = ticket_markdown(s.ticket)
        st.markdown(f"**{s.ticket['jira_type']}** · {', '.join(s.ticket['component'])}")
        with st.container(border=True):
            st.markdown(markdown)
        st.code(markdown, language="markdown")
        d = st.columns(2)
        d[0].download_button("Download .md", markdown, file_name=f"ticket_{s.session_id}.md", mime="text/markdown")
        d[1].download_button(
            "Download .json",
            json.dumps(s.ticket, indent=1, ensure_ascii=False),
            file_name=f"ticket_{s.session_id}.json",
            mime="application/json",
        )
    if s.stage == "stopped":
        st.success("Stopped: the request looks already supported (see the documentation link above).")

    # trace (LLM tracing for the session)
    with st.expander(f"Trace · {len(s.trace)} steps · ${sum(e.cost for e in s.trace):.4f}"):
        if s.trace:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "step": e.step,
                            "component": e.component,
                            "ms": e.latency_ms,
                            "cost $": e.cost,
                            "llm calls": e.llm_calls,
                            "cached": e.cached,
                            "input": e.input_summary,
                            "output": e.error or e.output_summary,
                        }
                        for e in s.trace
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        st.caption(f"Session {s.session_id} · stage {s.stage}")
