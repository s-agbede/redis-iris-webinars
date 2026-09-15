from app.models import CameraProduct
from app.suggestions import suggestion_entries


def test_suggestions_use_titles_and_brands_counted_once_per_product() -> None:
    products = [
        CameraProduct(product_id="a", product_title="  Sony   Alpha  ", product_brand="Sony"),
        CameraProduct(product_id="b", product_title="Sony Alpha", product_brand="Sony"),
        CameraProduct(product_id="c", product_title="Canon lens", product_brand=None),
    ]
    entries = suggestion_entries(products)
    assert entries["Sony"] == 2
    assert entries["Sony Alpha"] == 2
    assert entries["Canon lens"] == 1
    assert len(entries) == 3


def test_empty_and_overlong_suggestions_are_excluded() -> None:
    products = [CameraProduct(product_id="a", product_title="x" * 201, product_brand="  ")]
    assert suggestion_entries(products) == {}
