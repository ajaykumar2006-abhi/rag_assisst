"""End-to-end verification against a *running* backend.

This is not a mock and not a unit test: it talks to a live uvicorn process over
real HTTP, uploads the real sample documents from ``eval/fixtures``, waits for the
background pipeline, asks questions whose answers are known from the source text,
and checks the returned citations against the document the fact came from.

Every check is asserted, and the script exits non-zero if any check fails, so it
can be used as a gate in CI (see ``.github/workflows/ci.yml``).

Usage
-----
    # terminal 1
    cd backend && uvicorn app.main:app --port 8000
    # terminal 2
    python scripts/make_sample_documents.py
    python scripts/e2e_check.py --base-url http://127.0.0.1:8000

Options
-------
    --keep       do not delete the uploaded documents at the end
    --base-url   API origin (default http://127.0.0.1:8000)
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "eval" / "fixtures"

API_PREFIX = "/api/v1"
POLL_INTERVAL_SECONDS = 0.4
POLL_TIMEOUT_SECONDS = 120.0

# (question, expected substring of the answer, expected source filename)
KNOWN_ANSWER_QUESTIONS: list[tuple[str, str, str]] = [
    (
        "When did the Helios mission launch?",
        "14 March 2031",
        "helios_mission_brief.pdf",
    ),
    (
        "What altitude and inclination does the observatory orbit at?",
        "612 kilometres",
        "helios_mission_brief.pdf",
    ),
    (
        "What frequency range does the Low Frequency Spectrometer cover?",
        "320 megahertz",
        "helios_mission_brief.pdf",
    ),
    (
        "How often is calibration performed?",
        "every 30 days",
        "helios_ops_procedures.docx",
    ),
    (
        "What is the aperture of the Wide Field Imager?",
        "1.2 metre aperture",
        "helios_instrument_specs.txt",
    ),
]

OUT_OF_SCOPE_QUESTION = "Which football team won the 1994 FIFA World Cup final?"


class Checks:
    """Collects pass/fail results so the script can report every check it ran."""

    def __init__(self) -> None:
        self.results: list[tuple[bool, str, str]] = []

    def check(self, ok: bool, label: str, detail: str = "") -> bool:
        self.results.append((bool(ok), label, detail))
        marker = "PASS" if ok else "FAIL"
        print(f"  [{marker}] {label}" + (f" — {detail}" if detail else ""))
        return bool(ok)

    @property
    def failed(self) -> list[tuple[bool, str, str]]:
        return [item for item in self.results if not item[0]]

    def report(self) -> int:
        total = len(self.results)
        failures = len(self.failed)
        print()
        print(f"{total - failures}/{total} checks passed")
        if failures:
            print("\nFailures:")
            for _ok, label, detail in self.failed:
                print(f"  - {label}{f' — {detail}' if detail else ''}")
        return 1 if failures else 0


def wait_for_ready(client: httpx.Client, document_id: str, checks: Checks) -> dict[str, Any]:
    deadline = time.time() + POLL_TIMEOUT_SECONDS
    last: dict[str, Any] = {}
    while time.time() < deadline:
        response = client.get(f"{API_PREFIX}/documents/{document_id}/status")
        response.raise_for_status()
        last = response.json()
        if last["status"] in ("ready", "failed"):
            return last
        time.sleep(POLL_INTERVAL_SECONDS)
    checks.check(False, f"document {document_id} settled", f"timed out after {POLL_TIMEOUT_SECONDS}s")
    return last


def main() -> int:
    parser = argparse.ArgumentParser(description="End-to-end check against a running backend.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--keep", action="store_true", help="keep uploaded documents afterwards")
    args = parser.parse_args()

    checks = Checks()

    fixtures = [
        FIXTURE_DIR / "helios_mission_brief.pdf",
        FIXTURE_DIR / "helios_instrument_specs.txt",
        FIXTURE_DIR / "helios_ops_procedures.docx",
    ]

    print(f"Target: {args.base_url}")
    missing = [path.name for path in fixtures if not path.exists()]
    if missing:
        print(f"Missing fixtures: {', '.join(missing)}")
        print("Run: python scripts/make_sample_documents.py")
        return 2

    with httpx.Client(base_url=args.base_url, timeout=httpx.Timeout(120.0)) as client:
        # Start from a clean store: leftovers from earlier manual sessions would
        # otherwise be cited instead of the fixtures this script just uploaded.
        leftovers = client.get(f"{API_PREFIX}/documents").json()
        for document in leftovers:
            client.delete(f"{API_PREFIX}/documents/{document['id']}")
        if leftovers:
            print(f"Cleared {len(leftovers)} pre-existing document(s) first.")

        print("\n1. Health")
        health = client.get(f"{API_PREFIX}/health")
        checks.check(health.status_code == 200, "GET /health returns 200", f"http {health.status_code}")
        health_body = health.json()
        print(
            "     embedder={embedding_provider} dim={embedding_dim} answers={answer_provider}".format(**health_body)
        )

        print("\n2. Upload")
        uploaded: dict[str, str] = {}
        for path in fixtures:
            with path.open("rb") as handle:
                response = client.post(
                    f"{API_PREFIX}/documents",
                    files={"file": (path.name, handle, "application/octet-stream")},
                )
            checks.check(
                response.status_code == 201,
                f"POST /documents accepts {path.name}",
                f"http {response.status_code}",
            )
            if response.status_code != 201:
                continue
            document = response.json()["document"]
            uploaded[path.name] = document["id"]
            checks.check(
                document["extension"].lstrip(".") in {"pdf", "txt", "docx"},
                f"{path.name} extension detected",
                document["extension"],
            )

        print("\n3. Processing")
        for name, document_id in uploaded.items():
            status = wait_for_ready(client, document_id, checks)
            checks.check(status["status"] == "ready", f"{name} indexed", f"status={status['status']}")
            checks.check(status["indexed"] is True, f"{name} marked as indexed")
            stages = status["stages"]
            checks.check(
                len(stages) == 7 and all(stage["state"] == "completed" for stage in stages),
                f"{name} completed all 7 stages",
                ", ".join(f"{s['name']}:{s['state']}" for s in stages),
            )
            listing = client.get(f"{API_PREFIX}/documents/{document_id}/sources").json()
            checks.check(
                len(listing["sources"]) > 0,
                f"{name} produced retrievable chunks",
                f"{len(listing['sources'])} chunks",
            )

        print("\n4. Grounded answers with verifiable citations")
        for question, expected_fact, expected_file in KNOWN_ANSWER_QUESTIONS:
            response = client.post(
                f"{API_PREFIX}/questions",
                json={"question": question, "top_k": 5},
            )
            checks.check(response.status_code == 200, f"answered: {question[:52]}", f"http {response.status_code}")
            if response.status_code != 200:
                continue
            answer = response.json()
            checks.check(
                not answer["insufficient_evidence"],
                f"evidence found for: {question[:52]}",
                f"mode={answer['answer_mode']}",
            )
            checks.check(
                expected_fact.lower() in answer["answer"].lower(),
                f"answer contains '{expected_fact}'",
                answer["answer"][:140],
            )
            files = {citation["filename"] for citation in answer["citations"]}
            checks.check(
                expected_file in files,
                f"citation points at {expected_file}",
                "cited: " + ", ".join(sorted(files)),
            )
            if expected_file.endswith(".pdf"):
                pages = {citation["page"] for citation in answer["citations"] if citation["filename"] == expected_file}
                checks.check(
                    any(page is not None for page in pages),
                    "PDF citation carries a page number",
                    f"pages={sorted(page for page in pages if page is not None)}",
                )
            # Citation markers in the answer text must resolve to a real citation.
            markers = [
                int(chunk.strip("[]"))
                for chunk in answer["answer"].replace("]", "[").split("[")[1:]
                if chunk.strip("[]").isdigit()
            ]
            indexes = {citation["index"] for citation in answer["citations"]}
            checks.check(
                all(marker in indexes for marker in markers),
                "every [n] marker in the answer maps to a returned citation",
                f"markers={markers} citations={sorted(indexes)}",
            )

        print("\n5. Refusal when the documents cannot support an answer")
        refusal = client.post(
            f"{API_PREFIX}/questions",
            json={"question": OUT_OF_SCOPE_QUESTION, "top_k": 5},
        ).json()
        checks.check(
            refusal["insufficient_evidence"] is True,
            "out-of-scope question is refused",
            f"mode={refusal['answer_mode']}",
        )
        checks.check(
            len(refusal["citations"]) == 0,
            "refusal returns no citations",
            f"{len(refusal['citations'])} citations",
        )

        print("\n6. Conversations are persisted")
        conversation = client.post(
            f"{API_PREFIX}/conversations",
            json={"document_ids": list(uploaded.values()), "title": "e2e check"},
        )
        checks.check(conversation.status_code in (200, 201), "conversation created", f"http {conversation.status_code}")
        if conversation.status_code in (200, 201):
            conversation_id = conversation.json()["id"]
            asked = client.post(
                f"{API_PREFIX}/questions",
                json={
                    "question": "What is the primary science objective?",
                    "conversation_id": conversation_id,
                    "top_k": 5,
                },
            ).json()
            checks.check(asked["conversation_id"] == conversation_id, "answer recorded in the conversation")
            stored = client.get(f"{API_PREFIX}/conversations/{conversation_id}").json()
            checks.check(
                len(stored["messages"]) >= 2,
                "conversation stores the question and the answer",
                f"{len(stored['messages'])} messages",
            )
            checks.check(
                any(message["citations"] for message in stored["messages"] if message["role"] == "assistant"),
                "stored answer kept its citations",
            )

        print("\n7. Deletion removes file, chunks and vectors")
        if not args.keep and uploaded:
            victim_name, victim_id = next(iter(uploaded.items()))
            before = client.get(f"{API_PREFIX}/documents").json()
            deleted = client.delete(f"{API_PREFIX}/documents/{victim_id}")
            checks.check(deleted.status_code == 200, f"DELETE {victim_name}", f"http {deleted.status_code}")
            body = deleted.json()
            checks.check(body["vectors_removed"] > 0, "vectors removed", f"{body['vectors_removed']} vectors")
            after = client.get(f"{API_PREFIX}/documents").json()
            checks.check(
                len(after) == len(before) - 1,
                "document no longer listed",
                f"{len(before)} -> {len(after)}",
            )
            checks.check(
                all(document["id"] != victim_id for document in after),
                "deleted id absent from the listing",
            )
            gone = client.get(f"{API_PREFIX}/documents/{victim_id}")
            checks.check(gone.status_code == 404, "fetching the deleted document returns 404", f"http {gone.status_code}")
            # Scoping a question to a document that no longer exists must never
            # return evidence from it: the API either 404s or reports no evidence.
            orphan = client.post(
                f"{API_PREFIX}/questions",
                json={"question": "What was the mission cost?", "document_ids": [victim_id], "top_k": 5},
            )
            if orphan.status_code == 200:
                body = orphan.json()
                checks.check(
                    body["insufficient_evidence"] is True or len(body["citations"]) == 0,
                    "questions scoped to the deleted document retrieve nothing",
                    f"mode={body['answer_mode']}",
                )
            else:
                checks.check(
                    orphan.status_code in (404, 422),
                    "questions scoped to the deleted document are rejected cleanly",
                    f"http {orphan.status_code}",
                )
            uploaded.pop(victim_name)

        if not args.keep:
            for name, document_id in uploaded.items():
                client.delete(f"{API_PREFIX}/documents/{document_id}")
            client.delete(f"{API_PREFIX}/conversations")

    return checks.report()


if __name__ == "__main__":
    raise SystemExit(main())
