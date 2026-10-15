"""Retrieval/answer evaluation.

Runs a reproducible dataset through the *real* pipeline in an isolated data
directory, so evaluation never mixes with the user's own library.

Ground truth is constructed by construction, not by assumption: every question
declares one or more ``relevant_passages`` -- verbatim substrings of the source
document. A retrieved chunk is judged relevant when it contains one of those
substrings. That gives an exact, auditable label for synthetic text and avoids
the usual failure mode of hand-labelled retrieval benchmarks.

Honest scope, stated up front and repeated in every result file:

* The dataset is small and synthetic. Results describe *this* pipeline on
  *this* dataset; they do not generalise to arbitrary real-world corpora.
* Precision@k is reported over the requested ``k``, not over the number of
  chunks in the collection, so it is sensitive to ``k``.
* No answer-quality score is claimed for the generative provider, and no
  "accuracy" percentage is reported for answers. Answer quality is only
  measured as answer *rate* (did the system decline vs. answer) plus citation
  hit rate (did a citation point at a passage containing the ground truth).
"""

from __future__ import annotations

import json
import logging
import shutil
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..core.config import PROJECT_ROOT, Settings
from ..schemas.models import AnswerMode
from .container import ServiceContainer
from .pipeline import PipelineRunner, persist_upload, stage_seed
from .qa import QAService

logger = logging.getLogger(__name__)

DEFAULT_DATASET = "synthetic_galaxy"
DATASET_DIR = PROJECT_ROOT / "eval" / "datasets"
RESULT_DIR = PROJECT_ROOT / "eval" / "results"

METHODOLOGY = (
    "Each dataset document is ingested through the production pipeline (upload -> "
    "extract -> chunk -> embed -> index) with default configuration. For every "
    "question the retriever returns the top-k chunks; a chunk counts as relevant "
    "when it contains one of the question's declared ground-truth substrings. "
    "Recall@k is the share of the question's ground-truth passages that are "
    "contained in at least one retrieved chunk (passage coverage, so it cannot "
    "exceed 1). Precision@k is the share of the k returned slots that are relevant "
    "chunks. MRR uses the rank of the first relevant chunk. Citation hit rate counts "
    "questions where at least one returned citation contains a ground-truth "
    "substring. Latency is measured around the answering call."
)

LIMITATIONS = [
    "The dataset is synthetic and small; numbers are specific to this dataset and configuration.",
    "Ground truth is substring containment, which is exact but shallow: a chunk can be "
    "topically relevant and still be marked irrelevant if it paraphrases the source.",
    "Precision@k is computed against the requested k, so a larger k mechanically lowers it.",
    "No comparative claim is made against any commercial system: no such comparison was run.",
    "Retrieval quality for the default hashing embedder is lexical; enabling the optional "
    "neural embedder changes the numbers and should be re-measured rather than assumed.",
]


def load_dataset(name: str = DEFAULT_DATASET) -> Dict:
    path = DATASET_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Evaluation dataset not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def available_datasets() -> List[str]:
    if not DATASET_DIR.exists():
        return []
    return sorted(path.stem for path in DATASET_DIR.glob("*.json"))


# ---------------------------------------------------------------------------
# Ingesting the dataset into an isolated collection
# ---------------------------------------------------------------------------


def _eval_settings(base: Settings, top_k: int) -> Settings:
    """Settings clone pointing at a throwaway data directory."""
    settings = Settings()
    settings.data_dir = base.data_dir / "eval_run"
    settings.ensure_dirs()
    settings.top_k = top_k
    settings.embedding_provider = base.embedding_provider
    settings.embedding_dim = base.embedding_dim
    settings.embedding_model = base.embedding_model
    settings.answer_provider = base.answer_provider
    settings.chunk_size = base.chunk_size
    settings.chunk_overlap = base.chunk_overlap
    settings.dense_weight = base.dense_weight
    settings.lexical_weight = base.lexical_weight
    settings.min_relevance = base.min_relevance
    return settings


def _ingest_dataset_documents(container: ServiceContainer, dataset: Dict) -> Dict[str, str]:
    """Ingest every dataset document. Returns {dataset_document_id: real_id}."""
    mapping: Dict[str, str] = {}
    for document in dataset["documents"]:
        data = document["text"].encode("utf-8")
        record = persist_upload(container, document["filename"], data, ".txt")
        container.db.create_document(record)
        container.db.reset_stages(record["id"], stage_seed())
        PipelineRunner(container).run(record["id"])

        row = container.db.get_document(record["id"])
        if row is None or row["status"] != "ready":
            raise RuntimeError(
                f"Evaluation document '{document['filename']}' failed to index: "
                f"{row['error'] if row else 'missing'}"
            )
        mapping[document["id"]] = record["id"]
    return mapping


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------


def _chunk_is_relevant(text: str, passages: Sequence[str]) -> bool:
    lowered = (text or "").lower()
    return any(passage.lower() in lowered for passage in passages)


def _covered_passages(chunks: Sequence, passages: Sequence[str]) -> int:
    """How many ground-truth passages are contained in at least one retrieved chunk.

    Recall is measured over *passages*, not over chunks: a single passage can be
    satisfied by several overlapping chunks, and counting chunks would let recall
    exceed 1.0.
    """
    covered = 0
    for passage in passages:
        needle = passage.lower()
        if any(needle in (getattr(chunk, "text", "") or "").lower() for chunk in chunks):
            covered += 1
    return covered


def _reciprocal_rank(flags: Sequence[bool]) -> float:
    for index, flag in enumerate(flags, start=1):
        if flag:
            return 1.0 / index
    return 0.0


def run_evaluation(
    base_settings: Settings,
    dataset_name: str = DEFAULT_DATASET,
    top_k: int = 5,
    limit: Optional[int] = None,
    save: bool = True,
) -> Dict:
    """Execute the evaluation and return a machine-readable result dict."""
    dataset = load_dataset(dataset_name)
    questions = dataset["questions"][:limit] if limit else dataset["questions"]
    if not questions:
        raise ValueError("The dataset contains no questions.")

    settings = _eval_settings(base_settings, top_k)
    # Start from a clean slate so a rerun cannot benefit from stale vectors.
    if settings.data_dir.exists():
        shutil.rmtree(settings.data_dir, ignore_errors=True)
    settings.ensure_dirs()

    container = ServiceContainer(settings)
    started = time.perf_counter()
    try:
        mapping = _ingest_dataset_documents(container, dataset)
        qa = QAService(container)

        cases: List[Dict] = []
        for question in questions:
            document_ids = [mapping[d] for d in question.get("document_ids", []) if d in mapping] or None
            passages = question["relevant_passages"]

            t0 = time.perf_counter()
            retrieved = container.search(
                question["question"],
                top_k=top_k,
                document_ids=document_ids,
            )
            latency_ms = (time.perf_counter() - t0) * 1000

            flags = [_chunk_is_relevant(chunk.text, passages) for chunk in retrieved]
            hits = sum(1 for flag in flags if flag)
            # Recall: share of ground-truth passages that appear in the top-k at all.
            recall = (_covered_passages(retrieved, passages) / len(passages)) if passages else 0.0
            # Precision@k: share of the k returned slots that are relevant chunks.
            precision = min(hits / top_k, 1.0) if top_k else 0.0

            response = qa.answer(
                question["question"], document_ids=document_ids, top_k=top_k
            )
            citation_hit = any(
                _chunk_is_relevant(citation.excerpt, passages) for citation in response.citations
            )

            cases.append(
                {
                    "id": question["id"],
                    "question": question["question"],
                    "expected_answer": question["expected_answer"],
                    "retrieved_chunk_ids": [chunk.chunk_id for chunk in retrieved],
                    "relevant_chunk_ids": [
                        chunk.chunk_id for chunk, flag in zip(retrieved, flags) if flag
                    ],
                    "recall_at_k": round(recall, 6),
                    "precision_at_k": round(min(precision, 1.0), 6),
                    "reciprocal_rank": round(_reciprocal_rank(flags), 6),
                    "citation_hit": citation_hit,
                    "answered": response.answer_mode != AnswerMode.INSUFFICIENT,
                    "answer_mode": response.answer_mode.value,
                    "latency_ms": round(response.latency_ms, 3),
                }
            )

        count = len(cases)
        metrics = {
            "recall_at_k": round(statistics.fmean(case["recall_at_k"] for case in cases), 6),
            "precision_at_k": round(statistics.fmean(case["precision_at_k"] for case in cases), 6),
            "mrr": round(statistics.fmean(case["reciprocal_rank"] for case in cases), 6),
            "citation_hit_rate": round(
                sum(1 for case in cases if case["citation_hit"]) / count, 6
            ),
            "answer_rate": round(sum(1 for case in cases if case["answered"]) / count, 6),
            "mean_latency_ms": round(statistics.fmean(case["latency_ms"] for case in cases), 3),
            "p95_latency_ms": round(
                sorted(case["latency_ms"] for case in cases)[max(0, int(count * 0.95) - 1)], 3
            ),
        }

        run_id = f"eval_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
        result = {
            "run_id": run_id,
            "dataset": dataset_name,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "sample_count": count,
            "top_k": top_k,
            "configuration": {
                "embedding_provider": container.embedder.name,
                "embedding_dim": container.embedder.dim,
                "embedding_semantic": container.embedder.semantic,
                "answer_provider": container.answerer.name,
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
                "dense_weight": settings.dense_weight,
                "lexical_weight": settings.lexical_weight,
                "min_relevance": settings.min_relevance,
            },
            "metrics": metrics,
            "cases": cases,
            "methodology": METHODOLOGY,
            "limitations": LIMITATIONS,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "document_count": len(mapping),
            "chunk_count": container.db.chunk_count(),
        }

        if save:
            RESULT_DIR.mkdir(parents=True, exist_ok=True)
            json_path = RESULT_DIR / f"{run_id}.json"
            json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            result["result_path"] = str(json_path)

            report_path = RESULT_DIR / f"{run_id}.md"
            report_path.write_text(render_report(result), encoding="utf-8")
            result["report_path"] = str(report_path)

            container.db.save_eval_run(
                {
                    "run_id": run_id,
                    "dataset": dataset_name,
                    "created_at": result["created_at"],
                    "sample_count": count,
                    "top_k": top_k,
                    "metrics": metrics,
                    "cases": cases,
                    "result_path": str(json_path),
                }
            )

        return result
    finally:
        container.shutdown()


def render_report(result: Dict) -> str:
    """Human-readable Markdown report for a completed run."""
    metrics = result["metrics"]
    config = result["configuration"]
    lines = [
        f"# Evaluation report -- {result['run_id']}",
        "",
        f"- Dataset: `{result['dataset']}`",
        f"- Samples: **{result['sample_count']}** questions across "
        f"{result['document_count']} synthetic documents "
        f"({result['chunk_count']} chunks indexed)",
        f"- Top-k: {result['top_k']}",
        f"- Embedding: `{config['embedding_provider']}` ({config['embedding_dim']}d, "
        f"semantic={config['embedding_semantic']})",
        f"- Answer provider: `{config['answer_provider']}`",
        f"- Chunking: {config['chunk_size']} chars / {config['chunk_overlap']} overlap",
        f"- Fusion: dense={config['dense_weight']}, lexical={config['lexical_weight']}, "
        f"min_relevance={config['min_relevance']}",
        f"- Wall time: {result['duration_seconds']}s",
        "",
        "## Measured metrics",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Recall@{result['top_k']} | {metrics['recall_at_k']:.4f} |",
        f"| Precision@{result['top_k']} | {metrics['precision_at_k']:.4f} |",
        "| MRR | {:.4f} |".format(metrics["mrr"]),
        f"| Citation hit rate | {metrics['citation_hit_rate']:.4f} |",
        f"| Answer rate | {metrics['answer_rate']:.4f} |",
        f"| Mean answer latency | {metrics['mean_latency_ms']:.1f} ms |",
        f"| p95 answer latency | {metrics['p95_latency_ms']:.1f} ms |",
        "",
        "## Per-question results",
        "",
        "| # | Question | Recall | P@k | RR | Citation hit | Mode | Latency (ms) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for index, case in enumerate(result["cases"], start=1):
        lines.append(
            f"| {index} | {case['question']} | {case['recall_at_k']:.2f} | "
            f"{case['precision_at_k']:.2f} | {case['reciprocal_rank']:.2f} | "
            f"{'yes' if case['citation_hit'] else 'no'} | {case['answer_mode']} | "
            f"{case['latency_ms']:.0f} |"
        )

    lines += ["", "## Methodology", "", result["methodology"], "", "## Limitations", ""]
    lines += [f"- {item}" for item in result["limitations"]]
    lines += [
        "",
        "## How to reproduce",
        "",
        "```bash",
        "python eval/run_evaluation.py",
        "```",
        "",
    ]
    return "\n".join(lines)
