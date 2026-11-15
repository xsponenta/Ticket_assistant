"""Build the real pipeline components with the approved configs (heavy imports live here, not in src/pipeline.py).

- C1: BaselineC1, mode full, fitted on TRAIN with the C values of eval/c1_final_config.json (M1); cached as
  models/c1_baseline_full.joblib after the first fit.
- C2: dense DuplicateFinder over data/processed/issues.parquet with the cached embeddings; alert thresholds per mode
  from eval/c2_final_config.json (M2); dismissed candidates are removed before the alert is decided.
- C3: dense DocIndex over the doc chunks, k from eval/c3_final_config.json (M3).
- C4 / C5 / C6: the components with their approved prompts (eval/c4|c5_final_config.json; C6 c6_compose/v1).
One local embedder (models.embedder) is shared by C2 and C3.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from src import llm
from src.components.classifier import input_text, map_components
from src.components.classifier_baseline import BaselineC1
from src.components.duplicate_finder import TOP, DuplicateFinder
from src.components.gap_detector import detect
from src.components.question_generator import generate
from src.components.scope_checker import DocIndex, check, load_chunks
from src.components.ticket_composer import compose
from src.eval.samples import load_split
from src.pipeline import Components
from src.retrieval.dense import Embedder
from src.schemas.c2 import JIRA_BROWSE, C2Output, DuplicateCandidate

ROOT = Path(__file__).resolve().parents[1]
EMB_DIR = ROOT / "data" / "processed" / "embeddings"
C1_CACHE = ROOT / "models" / "c1_baseline_full.joblib"


def config(name: str) -> dict[str, Any]:
    return json.loads((ROOT / "eval" / f"{name}_final_config.json").read_text())


def load_c1() -> BaselineC1:
    if C1_CACHE.exists():
        return joblib.load(C1_CACHE)
    c = config("c1")["baseline"]["full"]
    train = load_split("train")
    model = BaselineC1.fit(
        [input_text(s, d, "full") for s, d in zip(train.summary, train.description_md, strict=True)],
        list(train.target_class),
        [map_components(list(x)) for x in train.components],
        c["C_class"],
        c["C_component"],
    )
    C1_CACHE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, C1_CACHE)
    return model


def load_components() -> Components:
    embedder_id = llm._settings().models["embedder"]
    embedder = Embedder(embedder_id)
    c1 = load_c1()

    def classify(summary: str, description: str) -> dict[str, Any]:
        text = input_text(summary, description, "full")
        classes = [(str(c), round(float(p), 3)) for c, p in c1.rank_classes([text])[0]]
        return {"classes": classes, "components": [str(c) for c in c1.predict([text])[0]["component"]]}

    issues = pd.read_parquet(ROOT / "data" / "processed" / "issues.parquet")
    finder = DuplicateFinder(issues, "dense", embedder, cache_path=EMB_DIR / f"{embedder_id.replace('/', '__')}.npy")
    thresholds = config("c2")["alert_threshold"]

    def find_duplicates(summary: str, description: str, mode: str, exclude: list[str]) -> C2Output:
        ranked, scores, _ = finder.search(summary, description, mode, depth=TOP + len(exclude))
        candidates = [
            DuplicateCandidate(
                key=str(finder.keys[i]),
                summary=finder.summaries[i],
                url=JIRA_BROWSE + str(finder.keys[i]),
                score=round(float(s), 6),
            )
            for i, s in zip(ranked, scores, strict=True)
            if str(finder.keys[i]) not in exclude
        ][:TOP]
        top_score = candidates[0].score if candidates else 0.0
        return C2Output(candidates=candidates, alert=top_score >= thresholds[mode], alert_score=top_score)

    chunks = load_chunks()
    by_id = {c["chunk_id"]: c for c in chunks}
    index = DocIndex(chunks, "dense", embedder, EMB_DIR / f"doc_chunks__{embedder_id.replace('/', '__')}.npy")
    k = config("c3")["k"]

    def check_scope(summary: str, description: str, session_id: str | None = None):
        out, retrieved = check(summary, description, k=k, index=index, session_id=session_id)
        return out, [by_id[cid] for cid in retrieved]

    return Components(
        classify=classify,
        find_duplicates=find_duplicates,
        detect_gaps=detect,
        ask=generate,
        check_scope=check_scope,
        compose=compose,
    )
