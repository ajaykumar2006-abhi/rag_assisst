"""API integration tests: grounded answering, citations, insufficient evidence, conversations."""

from __future__ import annotations

from app.services.pipeline import persist_upload

from .conftest import make_txt

QUESTION = "Which institute built the Cryo-Spectrometer Array?"


def test_answer_is_grounded_and_carries_a_verifiable_citation(client, ingest):
    document_id, _detail = ingest(make_txt())

    response = client.post(
        f"/api/v1/documents/{document_id}/questions", json={"question": QUESTION}
    )
    assert response.status_code == 200
    body = response.json()

    assert body["answer_mode"] == "extractive"
    assert body["insufficient_evidence"] is False
    assert body["retrieved_count"] >= 1
    assert body["citations"], "an answered question must cite its source"

    citation = body["citations"][0]
    assert citation["document_id"] == document_id
    assert citation["filename"] == "helios.txt"
    assert citation["chunk_id"].startswith(f"{document_id}::")
    assert citation["excerpt"]
    assert citation["score"] > 0

    # The cited evidence must genuinely contain the fact, and the answer must
    # point at the citation marker it used.
    assert "Tycho Institute" in citation["excerpt"]
    assert "[1]" in body["answer"]
    assert "Tycho Institute" in body["answer"]


def test_answer_text_is_verbatim_evidence_not_invention(client, ingest):
    document_id, _detail = ingest(make_txt())
    body = client.post(
        f"/api/v1/documents/{document_id}/questions", json={"question": QUESTION}
    ).json()
    # Extractive mode copies sentences out of the document verbatim.
    first_sentence = body["answer"].split(" [")[0].strip().rstrip(".")
    assert first_sentence in body["citations"][0]["excerpt"]


def test_insufficient_evidence_is_reported_instead_of_guessing(client, ingest):
    document_id, _detail = ingest(make_txt())
    body = client.post(
        f"/api/v1/documents/{document_id}/questions",
        json={"question": "What is the migration route of the Arctic tern?"},
    ).json()

    assert body["answer_mode"] == "insufficient"
    assert body["insufficient_evidence"] is True
    assert body["citations"] == []
    assert body["notice"]
    assert "could not find" in body["answer"].lower()


def test_question_without_documents_says_so_explicitly(client):
    body = client.post("/api/v1/questions", json={"question": "Anything?"}).json()
    assert body["answer_mode"] == "insufficient"
    assert "no indexed documents" in body["answer"].lower()


def test_collection_wide_question_spans_documents(client, ingest):
    pdf_id, _ = ingest(
        (
            "second.txt",
            b"The Fine Guidance Sensor delivers 0.18 arcseconds pointing accuracy.",
            "text/plain",
        )
    )
    txt_id, _ = ingest(make_txt())

    body = client.post(
        "/api/v1/questions",
        json={"question": "What pointing accuracy does the Fine Guidance Sensor deliver?", "document_ids": [txt_id, pdf_id]},
    ).json()
    assert body["answer_mode"] == "extractive"
    assert any(citation["document_id"] == pdf_id for citation in body["citations"])


def test_question_scoped_to_the_wrong_document_finds_nothing(client, ingest):
    other_id, _ = ingest(("unrelated.txt", b"This file is about kitchen gardening and soil pH.", "text/plain"))
    body = client.post(
        f"/api/v1/documents/{other_id}/questions", json={"question": QUESTION}
    ).json()
    assert body["answer_mode"] == "insufficient"


def test_question_on_unknown_document_returns_not_found(client):
    response = client.post(
        "/api/v1/documents/doc_missing/questions", json={"question": "hello"}
    )
    assert response.status_code == 404


def test_empty_question_is_rejected(client, ingest):
    document_id, _ = ingest(make_txt())
    response = client.post(f"/api/v1/documents/{document_id}/questions", json={"question": ""})
    assert response.status_code == 422


def test_top_k_is_honoured_and_bounded(client, ingest):
    document_id, _ = ingest(make_txt())
    body = client.post(
        f"/api/v1/documents/{document_id}/questions",
        json={"question": QUESTION, "top_k": 1},
    ).json()
    assert len(body["citations"]) <= 1

    response = client.post(
        f"/api/v1/documents/{document_id}/questions",
        json={"question": QUESTION, "top_k": 500},
    )
    assert response.status_code == 422


def test_question_against_a_document_that_is_still_processing_explains_itself(client, container, upload):
    """Asking before indexing completes must produce a clear, actionable error."""
    record = persist_upload(
        container, "pending.txt", b"Some content that has not been indexed yet.", ".txt"
    )
    container.db.create_document(record)

    response = client.post(
        f"/api/v1/documents/{record['id']}/questions", json={"question": "anything at all"}
    )
    assert response.status_code == 409
    assert "still being processed" in response.json()["error"]["message"]


def test_conversation_records_both_turns_and_its_citations(client, ingest):
    document_id, _ = ingest(make_txt())
    created = client.post("/api/v1/conversations", json={"document_ids": [document_id]})
    assert created.status_code == 201
    conversation_id = created.json()["id"]

    client.post(
        f"/api/v1/documents/{document_id}/questions",
        json={"question": QUESTION, "conversation_id": conversation_id},
    )

    detail = client.get(f"/api/v1/conversations/{conversation_id}").json()
    assert detail["message_count"] == 2
    assert [message["role"] for message in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][0]["content"] == QUESTION
    assert detail["messages"][1]["citations"], "the stored assistant turn must keep its citations"
    assert detail["messages"][1]["answer_mode"] == "extractive"


def test_conversation_listing_and_deletion(client, ingest):
    document_id, _ = ingest(make_txt())
    conversation_id = client.post(
        "/api/v1/conversations", json={"document_ids": [document_id]}
    ).json()["id"]

    listing = client.get("/api/v1/conversations").json()
    assert [item["id"] for item in listing] == [conversation_id]

    assert client.delete(f"/api/v1/conversations/{conversation_id}").status_code == 200
    assert client.get("/api/v1/conversations").json() == []
    assert client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404


def test_clearing_all_chat_history(client, ingest):
    document_id, _ = ingest(make_txt())
    for _ in range(2):
        client.post("/api/v1/conversations", json={"document_ids": [document_id]})
    assert len(client.get("/api/v1/conversations").json()) == 2

    response = client.delete("/api/v1/conversations")
    assert response.status_code == 200
    assert response.json()["conversations_removed"] == 2
    assert client.get("/api/v1/conversations").json() == []


def test_conversation_with_unknown_document_is_rejected(client):
    response = client.post("/api/v1/conversations", json={"document_ids": ["doc_missing"]})
    assert response.status_code == 404


def test_answers_and_citations_are_computed_after_deletion(client, ingest):
    """Deleting a document must remove it from retrieval, not just from the list."""
    document_id, _ = ingest(make_txt())
    assert client.post(f"/api/v1/documents/{document_id}/questions", json={"question": QUESTION}).json()[
        "answer_mode"
    ] == "extractive"

    client.delete(f"/api/v1/documents/{document_id}")

    body = client.post("/api/v1/questions", json={"question": QUESTION}).json()
    assert body["answer_mode"] == "insufficient"
    assert body["citations"] == []


# ---------------------------------------------------------------------------
# Conversation context (follow-ups)
# ---------------------------------------------------------------------------

def _spy_search(container, monkeypatch):
    """Record every retrieval query the QA service issues."""
    queries: list[str] = []
    real_search = container.search

    def spying_search(query, **kwargs):
        queries.append(query)
        return real_search(query, **kwargs)

    monkeypatch.setattr(container, "search", spying_search)
    return queries


def test_out_of_scope_follow_up_retries_with_context_but_still_refuses(
    client, ingest, container, monkeypatch
):
    """Conversation history may widen retrieval, never the decision to answer."""
    document_id, _ = ingest(make_txt())
    conversation_id = client.post(
        "/api/v1/conversations", json={"document_ids": [document_id]}
    ).json()["id"]
    client.post(
        f"/api/v1/documents/{document_id}/questions",
        json={"question": QUESTION, "conversation_id": conversation_id},
    )

    queries = _spy_search(container, monkeypatch)
    body = client.post(
        "/api/v1/questions",
        json={"question": "What is the capital of Mongolia?", "conversation_id": conversation_id},
    ).json()

    # The follow-up failed the gate on its own words, so the service retried once
    # with the previous question added to the query...
    assert len(queries) == 2
    assert queries[0] == "What is the capital of Mongolia?"
    assert queries[1].startswith("What is the capital of Mongolia?")
    assert QUESTION in queries[1]
    # ...and the retry still could not turn it into an answer.
    assert body["answer_mode"] == "insufficient"
    assert body["insufficient_evidence"] is True
    assert body["citations"] == []


def test_without_a_conversation_no_context_retry_happens(client, ingest, container, monkeypatch):
    document_id, _ = ingest(make_txt())
    assert document_id
    queries = _spy_search(container, monkeypatch)

    body = client.post(
        "/api/v1/questions", json={"question": "What is the capital of Mongolia?"}
    ).json()

    assert queries == ["What is the capital of Mongolia?"]
    assert body["answer_mode"] == "insufficient"


def test_in_scope_follow_up_answers_without_needing_the_context_retry(
    client, ingest, container, monkeypatch
):
    document_id, _ = ingest(make_txt())
    conversation_id = client.post(
        "/api/v1/conversations", json={"document_ids": [document_id]}
    ).json()["id"]
    client.post(
        f"/api/v1/documents/{document_id}/questions",
        json={"question": QUESTION, "conversation_id": conversation_id},
    )

    queries = _spy_search(container, monkeypatch)
    body = client.post(
        "/api/v1/questions",
        json={"question": QUESTION, "conversation_id": conversation_id},
    ).json()

    assert body["answer_mode"] == "extractive"
    assert queries == [QUESTION], "a supported follow-up must not be re-retrieved with context"
