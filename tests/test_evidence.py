import pytest

from app.evidence import explain_fusion, literal_query_matches


def test_literal_overlap_preserves_unicode_offsets_and_excludes_stopwords() -> None:
    text = "📷 Sony ZV-E10. café & <b>lens</b> for filming"
    spans = literal_query_matches(text, "Sony ZV E10, café for", {"for"})
    assert [text[s.start : s.end] for s in spans] == ["Sony", "ZV", "E10", "café"]
    assert spans[0].start == 2


def test_literal_overlap_does_not_invent_stemming_or_substring_matches() -> None:
    assert literal_query_matches("Cameras for Sonycam", "camera Sony", set()) == []


def test_literal_overlap_escapes_regex_characters_and_preserves_raw_markup() -> None:
    text = "<b>F/1.8 (lens)</b> f/1x8"
    spans = literal_query_matches(text, "f/1.8 (lens)", set())
    assert [text[s.start : s.end] for s in spans] == ["F/1.8", "(lens)"]


def test_stopword_only_query_has_no_literal_emphasis() -> None:
    assert literal_query_matches("for the camera", "for the", {"for", "the"}) == []


def test_fusion_uses_native_passage_branch_ranks_and_verifies_the_score() -> None:
    rows = [
        {
            "passage_id": "a:1",
            "text_score": 8.0,
            "vsim_score": 0.7,
            "combined_score": 1 / 61 + 1 / 62,
        },
        {
            "passage_id": "a:2",
            "text_score": 7.0,
            "vsim_score": 0.9,
            "combined_score": 1 / 62 + 1 / 61,
        },
        {"passage_id": "b:1", "vsim_score": 0.6, "combined_score": 1 / 63},
    ]
    result = explain_fusion(rows, window=100)
    a = result["a:1"]
    assert a.status == "verified"
    assert (a.text_rank, a.vector_rank) == (1, 2)
    assert a.reconstructed_score == pytest.approx(rows[0]["combined_score"])
    assert result["b:1"].text_rank is None
    assert result["b:1"].text_contribution == 0


def test_fusion_tie_is_resolved_only_when_native_score_identifies_one_rank_pair() -> None:
    rows = [
        {
            "passage_id": "a",
            "text_score": 3.0,
            "vsim_score": 0.9,
            "combined_score": 1 / 62 + 1 / 61,
        },
        {
            "passage_id": "b",
            "text_score": 3.0,
            "vsim_score": 0.8,
            "combined_score": 1 / 61 + 1 / 62,
        },
    ]
    result = explain_fusion(rows, window=100)
    assert result["a"].status == "verified"
    assert result["a"].text_rank == 2


def test_ambiguous_ties_do_not_claim_verified_component_ranks() -> None:
    rows = [
        {"passage_id": pid, "text_score": 3.0, "vsim_score": 0.8, "combined_score": 1 / 61 + 1 / 62}
        for pid in ["a", "b"]
    ]
    result = explain_fusion(rows, window=100)
    assert result["a"].status == "unavailable"
    assert result["a"].text_rank is None
    assert result["a"].text_contribution is None


def test_missing_branch_evidence_or_mismatched_score_is_explicitly_unavailable() -> None:
    rows = [
        {"passage_id": "a", "combined_score": 0.03},
        {"passage_id": "b", "text_score": 1.0, "combined_score": 0.99},
    ]
    result = explain_fusion(rows, window=100)
    assert all(e.status == "unavailable" for e in result.values())
