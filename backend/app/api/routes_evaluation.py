"""Evaluation Studio endpoints.

Everything returned here is measured, not modelled: counts come from SQLite,
latencies come from logged request events, and metrics come from an actual run
of the evaluation pipeline. When no run has been performed yet, the endpoint
says so rather than inventing numbers.
"""

from __future__ import annotations

import logging
import statistics
from typing import List

from fastapi import APIRouter, Depends

from ..core.errors import ValidationError
from ..schemas.models import (
    EvaluationRunList,
    EvaluationRunRequest,
    EvaluationRunResponse,
    EvaluationSummary,
)
from ..services import evaluation as evaluation_service
from ..services.container import ServiceContainer
from .deps import get_container

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.get("/summary", response_model=EvaluationSummary, summary="Live processing and latency statistics")
def summary(container: ServiceContainer = Depends(get_container)) -> EvaluationSummary:
    counts = container.db.count_by_status()
    stats = container.db.event_stats()
    kinds = stats["kinds"]
    latencies = stats["answer_latencies"] or [0.0]
    ordered = sorted(latencies)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95) - 1))

    return EvaluationSummary(
        documents_total=sum(counts.values()),
        documents_ready=counts.get("ready", 0),
        documents_failed=counts.get("failed", 0),
        chunks_indexed=container.db.chunk_count(),
        questions_answered=int(kinds.get("answer", {}).get("count", 0)),
        errors_total=int(kinds.get("processing_failed", {}).get("count", 0))
        + int(kinds.get("pipeline_crash", {}).get("count", 0)),
        mean_answer_latency_ms=round(statistics.fmean(latencies), 3),
        p95_answer_latency_ms=round(ordered[p95_index], 3),
        embedding_provider=container.embedder.name,
        answer_provider=container.answerer.name,
    )


@router.get("/datasets", response_model=List[str], summary="Available evaluation datasets")
def datasets() -> List[str]:
    return evaluation_service.available_datasets()


@router.get("/runs", response_model=EvaluationRunList, summary="Previously recorded evaluation runs")
def runs(container: ServiceContainer = Depends(get_container)) -> EvaluationRunList:
    return EvaluationRunList(runs=container.db.list_eval_runs())


@router.post("/run", response_model=EvaluationRunResponse, summary="Run the evaluation dataset")
def run(
    payload: EvaluationRunRequest, container: ServiceContainer = Depends(get_container)
) -> EvaluationRunResponse:
    dataset = payload.dataset or evaluation_service.DEFAULT_DATASET
    if dataset not in evaluation_service.available_datasets():
        raise ValidationError(
            f"Unknown dataset '{dataset}'. Available: "
            f"{', '.join(evaluation_service.available_datasets()) or 'none'}."
        )

    result = evaluation_service.run_evaluation(
        base_settings=container.settings,
        dataset_name=dataset,
        top_k=payload.top_k or container.settings.top_k,
        limit=payload.limit,
        save=True,
    )
    metrics = result["metrics"]

    # The evaluation runs in its own isolated collection, so record the result in
    # the application's database too -- otherwise the run would be invisible to
    # /evaluation/runs even though the numbers were genuinely measured.
    container.db.save_eval_run(
        {
            "run_id": result["run_id"],
            "dataset": result["dataset"],
            "created_at": result["created_at"],
            "sample_count": result["sample_count"],
            "top_k": result["top_k"],
            "metrics": metrics,
            "cases": result["cases"],
            "result_path": result.get("result_path"),
        }
    )
    container.db.log_event(
        "evaluation_run",
        {
            "run_id": result["run_id"],
            "dataset": dataset,
            "samples": result["sample_count"],
            "recall_at_k": metrics["recall_at_k"],
        },
    )
    return EvaluationRunResponse(
        run_id=result["run_id"],
        dataset=result["dataset"],
        created_at=result["created_at"],
        sample_count=result["sample_count"],
        top_k=result["top_k"],
        recall_at_k=metrics["recall_at_k"],
        precision_at_k=metrics["precision_at_k"],
        mrr=metrics["mrr"],
        citation_hit_rate=metrics["citation_hit_rate"],
        answer_rate=metrics["answer_rate"],
        mean_latency_ms=metrics["mean_latency_ms"],
        cases=result["cases"],
        methodology=result["methodology"],
        limitations=result["limitations"],
        result_path=result.get("result_path"),
    )
