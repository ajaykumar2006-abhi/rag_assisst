"""Embedding provider and vector index tests."""

from __future__ import annotations

import numpy as np
import pytest

from app.services.embeddings import (
    HASHING_PROVIDER_NAME,
    HashingEmbedder,
    build_embedder,
    get_embedder,
)
from app.storage.vector_store import VectorIndex


# ---------------------------------------------------------------------------
# Hashing embedder
# ---------------------------------------------------------------------------


def test_hashing_embedder_shape_and_normalisation():
    embedder = HashingEmbedder(dim=128)
    matrix = embedder.embed_documents(["alpha beta gamma", "delta epsilon"])
    assert matrix.shape == (2, 128)
    assert matrix.dtype == np.float32
    norms = np.linalg.norm(matrix, axis=1)
    np.testing.assert_allclose(norms, np.ones(2), atol=1e-5)


def test_hashing_embedder_is_deterministic_across_instances():
    first = HashingEmbedder(dim=256).embed_documents(["repeatable text"])
    second = HashingEmbedder(dim=256).embed_documents(["repeatable text"])
    np.testing.assert_array_equal(first, second)


def test_hashing_embedder_separates_unrelated_text():
    embedder = HashingEmbedder(dim=512)
    vectors = embedder.embed_documents(
        ["the spectrometer covers 40 to 320 megahertz", "passive thermal control of the radiator"]
    )
    cosine = float(vectors[0] @ vectors[1])
    assert cosine < 0.5


def test_hashing_embedder_similarity_follows_surface_overlap():
    embedder = HashingEmbedder(dim=512)
    vectors = embedder.embed_documents(
        [
            "the wide field imager aperture is 1.2 metres",
            "the wide field imager aperture is 1.2 metres across",
            "calibration uses a noise diode injection",
        ]
    )
    near = float(vectors[0] @ vectors[1])
    far = float(vectors[0] @ vectors[2])
    assert near > far
    assert near > 0.5


def test_hashing_embedder_query_matches_document_encoding():
    embedder = HashingEmbedder(dim=256)
    np.testing.assert_array_equal(
        embedder.embed_query("altitude of the orbit"),
        embedder.embed_documents(["altitude of the orbit"])[0],
    )


def test_hashing_embedder_handles_empty_and_whitespace_input():
    embedder = HashingEmbedder(dim=64)
    matrix = embedder.embed_documents(["", "   ", "text"])
    assert matrix.shape == (3, 64)
    assert np.linalg.norm(matrix[0]) == 0.0  # empty input -> zero vector, explicitly


def test_hashing_embedder_empty_batch():
    assert HashingEmbedder(dim=64).embed_documents([]).shape == (0, 64)


def test_hashing_embedder_rejects_tiny_dimensions():
    with pytest.raises(ValueError):
        HashingEmbedder(dim=8)


def test_embedder_is_labelled_lexical_not_semantic():
    embedder = HashingEmbedder(dim=64)
    assert embedder.semantic is False
    assert "lexical" in embedder.label


def test_build_embedder_caches_instances():
    first = build_embedder("hashing", 128, "unused")
    second = build_embedder("hashing", 128, "unused")
    assert first is second
    assert first.name == HASHING_PROVIDER_NAME


def test_get_embedder_falls_back_when_sentence_model_missing(monkeypatch):
    """If sentence-transformers is not installed we fall back explicitly, not silently."""
    import app.services.embeddings as embeddings_module

    def boom(*_args, **_kwargs):
        raise ImportError("sentence-transformers is not installed")

    monkeypatch.setattr(embeddings_module, "SentenceTransformerEmbedder", boom)

    class FakeSettings:
        embedding_provider = "sentence"
        embedding_dim = 64
        embedding_model = "sentence-transformers/all-MiniLM-L6-v2"

    embeddings_module.reset_embedder_cache()
    embedder = get_embedder(FakeSettings())
    assert embedder.name == HASHING_PROVIDER_NAME
    assert embedder.semantic is False
    embeddings_module.reset_embedder_cache()


def test_unknown_embedding_provider_raises():
    with pytest.raises(ValueError):
        build_embedder("telepathy", 64, "model")


# ---------------------------------------------------------------------------
# Vector index
# ---------------------------------------------------------------------------


def _index(tmp_path, dim=64, provider="test-provider"):
    return VectorIndex(tmp_path / "index", dim=dim, provider=provider)


def test_vector_index_add_search_and_size(tmp_path):
    index = _index(tmp_path)
    embedder = HashingEmbedder(dim=64)
    ids = ["doc::00000", "doc::00001"]
    index.add(ids, embedder.embed_documents(["alpha beta", "gamma delta"]))
    assert index.size == 2
    assert index.has("doc::00000")

    hits = index.search(embedder.embed_query("alpha beta"), top_k=2)
    assert hits[0].chunk_id == "doc::00000"
    assert hits[0].score > hits[1].score


def test_vector_index_round_trips_through_disk(tmp_path):
    index = _index(tmp_path)
    embedder = HashingEmbedder(dim=64)
    index.add(["a::1", "a::2"], embedder.embed_documents(["first text", "second text"]))
    index.save()

    reloaded = _index(tmp_path)
    assert reloaded.size == 0
    assert reloaded.load() is True
    assert reloaded.size == 2
    assert reloaded.has("a::1")


def test_vector_index_rejects_manifest_from_a_different_provider(tmp_path):
    index = _index(tmp_path, provider="provider-a")
    embedder = HashingEmbedder(dim=64)
    index.add(["a::1"], embedder.embed_documents(["text"]))
    index.save()

    other = _index(tmp_path, provider="provider-b")
    assert other.load() is False, "a different embedding space must not be reused"


def test_vector_index_rejects_dimension_mismatch(tmp_path):
    index = VectorIndex(tmp_path / "index", dim=64, provider="p")
    embedder = HashingEmbedder(dim=64)
    index.add(["a::1"], embedder.embed_documents(["text"]))
    index.save()

    other = VectorIndex(tmp_path / "index", dim=16, provider="p")
    assert other.load() is False


def test_vector_index_add_replaces_existing_ids(tmp_path):
    index = _index(tmp_path)
    embedder = HashingEmbedder(dim=64)
    index.add(["a::1"], embedder.embed_documents(["original text"]))
    index.add(["a::1"], embedder.embed_documents(["completely different content"]))
    assert index.size == 1


def test_vector_index_filters_by_allowed_ids(tmp_path):
    index = _index(tmp_path)
    embedder = HashingEmbedder(dim=64)
    index.add(["d1::0", "d2::0"], embedder.embed_documents(["alpha beta", "alpha beta gamma"]))
    hits = index.search(embedder.embed_query("alpha beta"), top_k=5, allowed_chunk_ids={"d2::0"})
    assert [hit.chunk_id for hit in hits] == ["d2::0"]
    assert index.search(embedder.embed_query("alpha"), top_k=5, allowed_chunk_ids=set()) == []


def test_vector_index_remove_document_prefix(tmp_path):
    index = _index(tmp_path)
    embedder = HashingEmbedder(dim=64)
    index.add(["doc_a::0", "doc_a::1", "doc_b::0"], embedder.embed_documents(["x", "y", "z"]))
    assert index.remove_document("doc_a::") == 2
    assert index.ids() == ["doc_b::0"]


def test_vector_index_dimension_mismatch_on_add_raises(tmp_path):
    index = _index(tmp_path, dim=64)
    with pytest.raises(ValueError):
        index.add(["a::1"], np.ones((1, 4), dtype=np.float32))


def test_vector_index_search_on_empty_index_returns_nothing(tmp_path):
    assert _index(tmp_path).search(np.ones(64, dtype=np.float32), top_k=3) == []


def test_vector_index_reset_clears_everything(tmp_path):
    index = _index(tmp_path)
    embedder = HashingEmbedder(dim=64)
    index.add(["a::1"], embedder.embed_documents(["text"]))
    index.reset()
    assert index.size == 0
    assert index.ids() == []
