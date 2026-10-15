"""Evaluation service tests: metric maths, dataset integrity and honest reporting."""

from __future__ import annotations

import statistics

import pytest

from app.services.evaluation import (
    DEFAULT_DATASET,
    LIMITATIONS,
    METHODOLOGY,
    _chunk_is_relevant,
    _eval_settings,
    _reciprocal_rank,
    available_datasets,
    load_dataset,
    render_report,
    run_evaluation,
)


# ---------------------------------------------------------------------------
# Dataset integrity
# ---------------------------------------------------------------------------


def test_default_dataset_is_bundled_and_well_formed():
    assert DEFAULT_DATASET in available_datasets()
    dataset = load_dataset(DEFAULT_DATASET)
    assert dataset["documents"] and dataset["questions"]

    document_ids = {document["id"] for document in dataset["documents"]}
    assert len(dataset["questions"]) >= 10

    for document in dataset["documents"]:
        assert document["text"].strip()
        assert document["filename"]

    for question in dataset["questions"]:
        assert question["id"] and question["question"]
        assert question["relevant_passages"], "every question needs ground truth"
        assert set(question["document_ids"]) <= document_ids


def test_every_ground_truth_passage_really_appears_in_its_source_document():
    """Ground truth must be verifiable, not asserted."""
    dataset = load_dataset(DEFAULT_DATASET)
    bodies = {document["id"]: document["text"].lower() for document in dataset["documents"]}

    for question in dataset["questions"]:
        haystack = " ".join(bodies[document_id] for document_id in question["document_ids"])
        for passage in question["relevant_passages"]:
            assert passage.lower() in haystack, f"{question['id']} cites a passage not in its source"


def test_load_dataset_rejects_unknown_name():
    with pytest.raises(FileNotFoundError):
        load_dataset("no_such_dataset")


# ---------------------------------------------------------------------------
# Metric maths
# ---------------------------------------------------------------------------


def test_relevance_label_is_exact_substring_containment():
    assert _chunk_is_relevant("The launch was on 14 March 2031.", ["14 March 2031"]) is True
    assert _chunk_is_relevant("The launch date is not recorded.", ["14 March 2031"]) is False
    assert _chunk_is_relevant("", ["anything"]) is False
    assert _chunk_is_relevant("TEXT ABOUT THE MISSION", ["text about"]) is True


def test_reciprocal_rank_uses_the_first_hit():
    assert _reciprocal_rank([True, False]) == 1.0
    assert _reciprocal_rank([False, True]) == 0.5
    assert _reciprocal_rank([False, False, True]) == pytest.approx(1 / 3)
    assert _reciprocal_rank([False, False]) == 0.0
    assert _reciprocal_rank([]) == 0.0


def test_eval_settings_isolate_the_data_directory(settings):
    scoped = _eval_settings(settings, top_k=3)
    try:
        assert scoped.data_dir != settings.data_dir
        assert scoped.data_dir.parent == settings.data_dir
        assert scoped.top_k == 3
        assert scoped.embedding_provider == settings.embedding_provider
        assert scoped.answer_provider == settings.answer_provider
    finally:
        pass


# ---------------------------------------------------------------------------
# End-to-end run
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def evaluation_result(tmp_path_factory):
    """Run the real evaluation once for the whole module (it ingests documents)."""
    from app.core.config import Settings

    base = Settings()
    base.data_dir = tmp_path_factory.mktemp("eval-base")
    base.ensure_dirs()
    base.chunk_size = 900
    base.chunk_overlap = 150
    return run_evaluation(base, DEFAULT_DATASET, top_k=5, save=False)


def test_evaluation_run_is_reproducible_and_fully_labelled(evaluation_result):
    result = evaluation_result
    dataset = load_dataset(DEFAULT_DATASET)

    assert result["sample_count"] == len(dataset["questions"])
    assert result["document_count"] == len(dataset["documents"])
    assert result["chunk_count"] > 0
    assert result["top_k"] == 5
    assert result["methodology"] == METHODOLOGY
    assert result["limitations"] == LIMITATIONS
    assert result["duration_seconds"] > 0


def test_evaluation_metrics_are_correctly_averaged(evaluation_result):
    cases = evaluation_result["cases"]
    metrics = evaluation_result["metrics"]

    assert metrics["recall_at_k"] == pytest.approx(
        statistics.fmean(case["recall_at_k"] for case in cases), abs=1e-6
    )
    assert metrics["precision_at_k"] == pytest.approx(
        statistics.fmean(case["precision_at_k"] for case in cases), abs=1e-6
    )
    assert metrics["mrr"] == pytest.approx(
        statistics.fmean(case["reciprocal_rank"] for case in cases), abs=1e-6
    )
    assert metrics["citation_hit_rate"] == pytest.approx(
        sum(1 for case in cases if case["citation_hit"]) / len(cases), abs=1e-6
    )


def test_evaluation_metrics_stay_inside_their_defined_range(evaluation_result):
    metrics = evaluation_result["metrics"]
    for key in ("recall_at_k", "precision_at_k", "mrr", "citation_hit_rate", "answer_rate"):
        assert 0.0 <= metrics[key] <= 1.0, key
    assert metrics["mean_latency_ms"] >= 0
    assert metrics["p95_latency_ms"] >= 0


def test_evaluation_actually_retrieves_relevant_passages(evaluation_result):
    """The point of running an evaluation is that the numbers are not all zero."""
    assert evaluation_result["metrics"]["recall_at_k"] > 0.5
    assert evaluation_result["metrics"]["citation_hit_rate"] > 0.5


def test_every_case_records_its_evidence(evaluation_result):
    for case in evaluation_result["cases"]:
        assert case["retrieved_chunk_ids"], f"{case['id']} retrieved nothing"
        assert len(case["retrieved_chunk_ids"]) == len(set(case["retrieved_chunk_ids"]))
        assert case["answer_mode"] in ("extractive", "generative", "insufficient")
        assert case["latency_ms"] >= 0


def test_report_renders_measured_values_and_limitations(evaluation_result):
    report = render_report(evaluation_result)
    assert evaluation_result["run_id"] in report
    assert "## Measured metrics" in report
    assert f"Recall@{evaluation_result['top_k']}" in report
    assert "MRR" in report
    assert "## Limitations" in report
    for limitation in LIMITATIONS:
        assert limitation in report
    # A methodology + sample count must be stated, never just a bare number.
    assert str(evaluation_result["sample_count"]) in report


def test_evaluation_does_not_write_results_when_save_is_false(evaluation_result):
    assert "result_path" not in evaluation_result
