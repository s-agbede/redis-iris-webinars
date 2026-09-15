import pytest
from pydantic import ValidationError

from app.models import RedisPassage, SearchMode
from app.settings import Settings
from seed.load import configure_schema


def test_schema_finds_embedding_by_name_instead_of_field_order() -> None:
    schema = {
        "index": {},
        "fields": [
            {"name": "embedding", "type": "vector", "attrs": {"algorithm": "flat"}},
            {"name": "brand", "type": "tag"},
        ],
    }
    settings = Settings(_env_file=None, namespace="demo", index_algorithm="HNSW")
    configure_schema(schema, settings)
    assert schema["fields"][0]["attrs"]["algorithm"] == "hnsw"
    assert schema["fields"][1] == {"name": "brand", "type": "tag"}
    assert schema["index"] == {"name": "demo_passages", "prefix": "demo:passage"}


def test_missing_embedding_schema_has_a_clear_error() -> None:
    with pytest.raises(ValueError, match="embedding"):
        configure_schema({"index": {}, "fields": []}, Settings(_env_file=None))


def test_redis_passage_parses_numeric_strings_and_preserves_source_evidence() -> None:
    row = RedisPassage.model_validate(
        {
            "product_id": "a",
            "passage_id": "a:1",
            "field": "product_description",
            "text": "Lens",
            "start": "2",
            "end": "6",
            "search_text": "Canon. Lens",
            "score": "3.5",
            "vector_distance": "0.2",
            "combined_score": "0.03",
        }
    )
    assert row.relevance_score(SearchMode.TEXT) == 3.5
    assert row.relevance_score(SearchMode.VECTOR) == pytest.approx(0.8)
    assert row.relevance_score(SearchMode.HYBRID) == 0.03
    assert row.passage().model_dump() == {
        "passage_id": "a:1",
        "field": "product_description",
        "text": "Lens",
        "start": 2,
        "end": 6,
    }
    with pytest.raises(ValidationError):
        RedisPassage.model_validate({"product_id": "a"})
    with pytest.raises(ValueError, match="score"):
        row.model_copy(update={"score": None}).relevance_score(SearchMode.TEXT)
