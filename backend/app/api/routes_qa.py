"""Question answering and conversation history."""

from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends, status

from ..core.errors import NotFoundError, ValidationError
from ..schemas.models import (
    AnswerResponse,
    Citation,
    ConversationDetail,
    ConversationMessage,
    ConversationSummary,
    QuestionRequest,
)
from ..services.container import ServiceContainer
from ..services.qa import QAService
from .deps import get_container

router = APIRouter(tags=["questions"])


def _load_citations(raw: str) -> List[Citation]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    citations: List[Citation] = []
    for item in data:
        try:
            citations.append(Citation(**item))
        except (TypeError, ValueError):
            continue
    return citations


# ---------------------------------------------------------------------------
# Per-document questions
# ---------------------------------------------------------------------------


@router.post(
    "/documents/{document_id}/questions",
    response_model=AnswerResponse,
    summary="Ask a question about one document",
)
def ask_document_question(
    document_id: str,
    payload: QuestionRequest,
    container: ServiceContainer = Depends(get_container),
) -> AnswerResponse:
    if container.db.get_document(document_id) is None:
        raise NotFoundError(f"No document with id '{document_id}'.")
    qa = QAService(container)
    return qa.answer(
        question=payload.question,
        document_ids=[document_id],
        top_k=payload.top_k,
        conversation_id=payload.conversation_id,
    )


# ---------------------------------------------------------------------------
# Collection-wide questions
# ---------------------------------------------------------------------------


@router.post(
    "/questions",
    response_model=AnswerResponse,
    summary="Ask a question across selected documents (or the whole collection)",
)
def ask_question(
    payload: QuestionRequest, container: ServiceContainer = Depends(get_container)
) -> AnswerResponse:
    if not payload.question.strip():
        raise ValidationError("The question must not be empty.")
    qa = QAService(container)
    return qa.answer(
        question=payload.question,
        document_ids=payload.document_ids,
        top_k=payload.top_k,
        conversation_id=payload.conversation_id,
    )


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


@router.get("/conversations", response_model=List[ConversationSummary], summary="List conversations")
def list_conversations(container: ServiceContainer = Depends(get_container)) -> List[ConversationSummary]:
    summaries: List[ConversationSummary] = []
    for row in container.db.list_conversations():
        summaries.append(
            ConversationSummary(
                id=row["id"],
                title=row["title"],
                document_ids=json.loads(row["document_ids"] or "[]"),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                message_count=int(row["message_count"] or 0),
            )
        )
    return summaries


@router.post(
    "/conversations",
    response_model=ConversationSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new conversation",
)
def create_conversation(
    payload: dict, container: ServiceContainer = Depends(get_container)
) -> ConversationSummary:
    document_ids = payload.get("document_ids") or []
    if not isinstance(document_ids, list):
        raise ValidationError("document_ids must be a list of document ids.")
    for document_id in document_ids:
        if container.db.get_document(document_id) is None:
            raise NotFoundError(f"No document with id '{document_id}'.")

    qa = QAService(container)
    conversation_id = qa.ensure_conversation(document_ids, title=payload.get("title", ""))
    row = container.db.get_conversation(conversation_id)
    return ConversationSummary(
        id=row["id"],
        title=row["title"],
        document_ids=json.loads(row["document_ids"] or "[]"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        message_count=0,
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
    summary="Fetch a conversation with its messages",
)
def get_conversation(
    conversation_id: str, container: ServiceContainer = Depends(get_container)
) -> ConversationDetail:
    row = container.db.get_conversation(conversation_id)
    if row is None:
        raise NotFoundError(f"No conversation with id '{conversation_id}'.")

    messages = [
        ConversationMessage(
            id=message["id"],
            role=message["role"],
            content=message["content"],
            created_at=message["created_at"],
            citations=_load_citations(message["citations"]),
            answer_mode=message["answer_mode"],
        )
        for message in container.db.get_messages(conversation_id)
    ]
    return ConversationDetail(
        id=row["id"],
        title=row["title"],
        document_ids=json.loads(row["document_ids"] or "[]"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        message_count=len(messages),
        messages=messages,
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete one conversation",
)
def delete_conversation(
    conversation_id: str, container: ServiceContainer = Depends(get_container)
) -> dict:
    if container.db.get_conversation(conversation_id) is None:
        raise NotFoundError(f"No conversation with id '{conversation_id}'.")
    with container.db.write() as conn:
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    return {"deleted": conversation_id}


@router.delete(
    "/conversations",
    status_code=status.HTTP_200_OK,
    summary="Clear all chat history",
)
def clear_conversations(container: ServiceContainer = Depends(get_container)) -> dict:
    removed = container.db.clear_conversations()
    container.db.log_event("chat_cleared", {"conversations_removed": removed})
    return {"conversations_removed": removed}
