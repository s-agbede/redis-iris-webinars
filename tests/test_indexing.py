import pytest

from app.catalog import make_passages
from app.indexing import prepare_product_passages
from app.settings import Settings
from tests.test_catalog import product, tokenizer


class Encoder:
    def __init__(self):
        self.tokenizer = tokenizer()
        self.calls = []

    def embed_many(self, texts):
        self.calls.append(texts)
        return [[float(len(text))] for text in texts]


def test_preparation_preserves_passages_and_embeds_their_search_text():
    encoder = Encoder()
    settings = Settings(_env_file=None)
    item = product(product_description="A portable camera.")
    expected = make_passages(item, encoder.tokenizer)
    records = prepare_product_passages(item, encoder, settings)
    assert [r.model_dump(exclude={"embedding"}) for r in records] == [
        p.model_dump() for p in expected
    ]
    assert encoder.calls == [[p.search_text for p in expected]]
    assert [r.embedding for r in records] == [[float(len(p.search_text))] for p in expected]


def test_preparation_reuses_available_vectors_and_embeds_only_missing_passages():
    encoder = Encoder()
    records = prepare_product_passages(
        product(product_description="A portable camera."),
        encoder,
        Settings(_env_file=None),
        reuse_embedding=lambda passage: [42.0] if passage.field == "product_title" else None,
    )
    assert records[0].embedding == [42.0]
    assert encoder.calls == [[records[1].search_text]]


def test_missing_product_needs_no_embeddings():
    encoder = Encoder()
    assert prepare_product_passages(None, encoder, Settings(_env_file=None)) == []
    assert encoder.calls == []


def test_incomplete_embedding_response_fails_instead_of_dropping_passages():
    class IncompleteEncoder(Encoder):
        def embed_many(self, texts):
            return []

    with pytest.raises(ValueError):
        prepare_product_passages(product(), IncompleteEncoder(), Settings(_env_file=None))


def test_unchanged_rebuild_reuses_all_vectors_without_model_inference():
    encoder = Encoder()
    records = prepare_product_passages(
        product(), encoder, Settings(_env_file=None), reuse_embedding=lambda passage: [42.0]
    )
    assert records
    assert all(record.embedding == [42.0] for record in records)
    assert encoder.calls == []
