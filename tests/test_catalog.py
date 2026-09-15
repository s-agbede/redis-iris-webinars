from tokenizers import Tokenizer
from tokenizers.models import WordLevel
from tokenizers.pre_tokenizers import Whitespace

from app.catalog import clean_text, make_passages
from app.models import CameraProduct


def tokenizer() -> Tokenizer:
    value = Tokenizer(WordLevel({"[UNK]": 0}, unk_token="[UNK]"))
    value.pre_tokenizer = Whitespace()
    return value


def product(**changes: object) -> CameraProduct:
    return CameraProduct.model_validate(
        {
            "product_id": "camera-1",
            "product_locale": "us",
            "product_title": "Canon camera lens",
            "product_brand": "Canon",
            "product_color": None,
            "product_description": None,
            "product_bullet_point": None,
            **changes,
        }
    )


def test_source_fields_are_preserved_while_search_text_is_cleaned() -> None:
    raw = "<b>Lens</b><br>Fits &amp; works."
    item = product(product_description=raw)
    passages = make_passages(item, tokenizer(), max_tokens=32, overlap=4)
    description = next(p for p in passages if p.field == "product_description")
    assert item.product_description == raw
    assert description.text == "Lens Fits & works."
    assert description.text in description.search_text
    assert item.product_title in description.search_text


def test_long_description_is_covered_to_the_end_without_duplicate_products() -> None:
    body = " ".join(f"word{i}" for i in range(200))
    item = product(product_description=body)
    tok = tokenizer()
    passages = [
        p
        for p in make_passages(item, tok, max_tokens=40, overlap=5)
        if p.field == "product_description"
    ]
    assert len(passages) > 1
    assert passages[0].start == 0
    assert passages[-1].end == len(body)
    assert all(b.start <= a.end for a, b in zip(passages, passages[1:], strict=False))
    assert all(p.text == body[p.start : p.end] for p in passages)
    assert all(len(tok.encode(p.search_text).ids) <= 40 for p in passages)
    assert {p.product_id for p in passages} == {"camera-1"}
    assert len({p.passage_id for p in passages}) == len(passages)


def test_missing_fields_do_not_become_invented_product_facts() -> None:
    passages = make_passages(product(), tokenizer())
    assert {p.field for p in passages} == {"product_title"}
    assert "None" not in passages[0].search_text


def test_clean_text_ignores_script_and_style_content() -> None:
    assert clean_text("<script>bad()</script><p>Real text</p><style>body{}</style>") == "Real text"


def test_long_title_also_gets_complete_coverage() -> None:
    title = " ".join(f"model{i}" for i in range(150))
    passages = make_passages(product(product_title=title), tokenizer(), max_tokens=40, overlap=5)
    assert passages[-1].end == len(title)
    assert all(len(tokenizer().encode(p.search_text).ids) <= 40 for p in passages)
