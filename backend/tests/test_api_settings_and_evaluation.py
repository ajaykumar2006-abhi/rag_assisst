"""API tests: settings, privacy controls and the Evaluation Studio endpoints."""

from __future__ import annotations

from .conftest import HELIOS_TEXT, make_txt


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


def test_settings_expose_non_secret_configuration(client):
    body = client.get("/api/v1/settings").json()
    assert body["answer_provider"] == "extractive"
    assert body["embedding_provider"] == "hashing"
    assert body["embedding_dim"] > 0
    assert ".pdf" in body["allowed_extensions"]
    assert body["max_upload_mb"] > 0
    assert any("run on this machine" in item or "Extractive" in item for item in body["runs_locally"])
    assert body["requires_external_service"]


def test_settings_separate_answerer_readiness_from_an_api_key(client):
    """The default configuration stores no key, yet the answerer is usable.

    These two facts used to share one boolean, which made the Settings screen claim an
    API key was configured while every answer came from the local extractive answerer.
    """
    body = client.get("/api/v1/settings").json()

    assert body["answer_provider"] == "extractive"
    assert body["llm_configured"] is False
    assert body["answerer_available"] is True
    assert body["answerer_reason"] == ""


def test_settings_report_a_stored_key_as_configured(client, container):
    container.settings.llm_api_key = "sk-test-DO-NOT-LEAK-1234567890"

    body = client.get("/api/v1/settings").json()

    assert body["llm_configured"] is True
    assert "sk-test-DO-NOT-LEAK" not in repr(body)


def test_settings_never_leak_the_api_key(client, container):
    container.settings.llm_api_key = "sk-test-DO-NOT-LEAK-1234567890"
    container.settings.llm_base_url = "https://example.invalid/v1"
    container.settings.llm_model = "example-model"

    response = client.get("/api/v1/settings")
    assert "sk-test-DO-NOT-LEAK" not in response.text
    assert "llm_api_key" not in response.json()
    assert response.json()["llm_base_url"] == "https://example.invalid/v1"

    # Nothing else in the API may echo it either.
    for path in ("/api/v1/health", "/api/v1/privacy", "/api/v1/evaluation/summary"):
        assert "sk-test-DO-NOT-LEAK" not in client.get(path).text


def test_settings_patch_updates_retrieval_parameters(client):
    response = client.patch("/api/v1/settings", json={"top_k": 3, "min_relevance": 0.2})
    assert response.status_code == 200
    body = response.json()
    assert body["applied"] is True
    assert body["settings"]["top_k"] == 3

    assert client.get("/api/v1/settings").json()["top_k"] == 3
    assert client.get("/api/v1/settings").json()["min_relevance"] == 0.2


def test_settings_patch_rejects_inconsistent_chunking(client):
    response = client.patch("/api/v1/settings", json={"chunk_size": 300, "chunk_overlap": 400})
    assert response.status_code == 422
    assert "chunk_overlap" in response.json()["error"]["message"]


def test_settings_patch_rejects_out_of_range_values(client):
    assert client.patch("/api/v1/settings", json={"top_k": 0}).status_code == 422
    assert client.patch("/api/v1/settings", json={"chunk_size": 10}).status_code == 422


def test_switching_provider_at_runtime_is_refused_with_an_explanation(client):
    response = client.patch("/api/v1/settings", json={"embedding_provider": "sentence"})
    assert response.status_code == 422
    assert "restart" in response.json()["error"]["message"].lower()

    response = client.patch("/api/v1/settings", json={"answer_provider": "openai_compatible"})
    assert response.status_code == 422
    assert "restart" in response.json()["error"]["message"].lower()


def test_settings_changes_affect_subsequent_answers(client, ingest):
    document_id, _ = ingest(make_txt())
    question = "Which institute built the Cryo-Spectrometer Array?"

    client.patch("/api/v1/settings", json={"top_k": 1})
    one = client.post(f"/api/v1/documents/{document_id}/questions", json={"question": question}).json()
    assert len(one["citations"]) <= 1


def test_min_relevance_threshold_produces_insufficient_evidence(client, ingest):
    document_id, _ = ingest(make_txt())
    client.patch("/api/v1/settings", json={"min_relevance": 0.99})
    body = client.post(
        f"/api/v1/documents/{document_id}/questions",
        json={"question": "Which institute built the Cryo-Spectrometer Array?"},
    ).json()
    assert body["answer_mode"] == "insufficient"
    assert "threshold" in body["notice"].lower() or "threshold" in body["answer"].lower()


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------


def test_privacy_reports_what_is_stored_locally(client, ingest):
    ingest(("privacy.txt", HELIOS_TEXT.encode(), "text/plain"))
    body = client.get("/api/v1/privacy").json()

    assert body["data_dir"]
    kinds = {item["what"]: item for item in body["storage"]}
    assert kinds["Uploaded documents"]["count"] == 1
    assert kinds["Uploaded documents"]["bytes"] > 0
    assert kinds["Vector index"]["count"] > 0
    assert body["delete_instructions"]
    assert body["external_services"]


def test_privacy_delete_all_documents_clears_everything(client, ingest, container):
    ingest(("one.txt", HELIOS_TEXT.encode(), "text/plain"))
    ingest(("two.txt", b"Second document with different content about gardening.", "text/plain"))

    response = client.delete("/api/v1/privacy/documents")
    assert response.status_code == 200
    assert response.json()["documents_removed"] == 2
    assert response.json()["index_size_after"] == 0

    assert client.get("/api/v1/documents").json() == []
    assert container.db.chunk_count() == 0
    assert not list(container.settings.upload_dir.rglob("source.txt"))


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def test_evaluation_summary_is_zero_before_any_work(client):
    body = client.get("/api/v1/evaluation/summary").json()
    assert body["documents_total"] == 0
    assert body["chunks_indexed"] == 0
    assert body["questions_answered"] == 0
    assert body["mean_answer_latency_ms"] == 0.0


def test_evaluation_summary_counts_real_work(client, ingest):
    document_id, _ = ingest(make_txt())
    client.post(f"/api/v1/documents/{document_id}/questions", json={"question": "altitude of the orbit"})

    body = client.get("/api/v1/evaluation/summary").json()
    assert body["documents_total"] == 1
    assert body["documents_ready"] == 1
    assert body["chunks_indexed"] > 0
    assert body["questions_answered"] == 1
    assert body["mean_answer_latency_ms"] > 0


def test_evaluation_datasets_lists_the_bundled_corpus(client):
    assert "synthetic_galaxy" in client.get("/api/v1/evaluation/datasets").json()


def test_evaluation_run_produces_real_measured_metrics(client):
    response = client.post(
        "/api/v1/evaluation/run", json={"dataset": "synthetic_galaxy", "top_k": 5, "limit": 6}
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["sample_count"] == 6
    assert body["top_k"] == 5
    assert 0.0 <= body["recall_at_k"] <= 1.0
    assert 0.0 <= body["precision_at_k"] <= 1.0
    assert 0.0 <= body["mrr"] <= 1.0
    assert 0.0 <= body["citation_hit_rate"] <= 1.0
    assert 0.0 <= body["answer_rate"] <= 1.0
    assert body["mean_latency_ms"] > 0
    assert len(body["cases"]) == 6
    assert body["methodology"] and body["limitations"]
    assert body["result_path"]

    # The measured retrieval must actually work on the dataset, not merely return.
    assert body["recall_at_k"] > 0.0
    assert body["citation_hit_rate"] > 0.0

    for case in body["cases"]:
        assert case["retrieved_chunk_ids"]
        assert case["id"].startswith("q_")


def test_evaluation_run_rejects_unknown_dataset(client):
    response = client.post("/api/v1/evaluation/run", json={"dataset": "does_not_exist"})
    assert response.status_code == 422
    assert "Unknown dataset" in response.json()["error"]["message"]


def test_evaluation_runs_are_recorded_and_listed(client):
    client.post("/api/v1/evaluation/run", json={"dataset": "synthetic_galaxy", "top_k": 5, "limit": 3})
    runs = client.get("/api/v1/evaluation/runs").json()["runs"]
    assert len(runs) >= 1
    assert runs[0]["dataset"] == "synthetic_galaxy"
    assert runs[0]["sample_count"] == 3
    assert "recall_at_k" in runs[0]["metrics"]


def test_evaluation_does_not_touch_the_user_library(client, ingest):
    document_id, _ = ingest(make_txt())
    before = client.get("/api/v1/documents").json()

    client.post("/api/v1/evaluation/run", json={"dataset": "synthetic_galaxy", "top_k": 3, "limit": 2})

    after = client.get("/api/v1/documents").json()
    assert after == before, "an evaluation run must not modify the user's documents"
