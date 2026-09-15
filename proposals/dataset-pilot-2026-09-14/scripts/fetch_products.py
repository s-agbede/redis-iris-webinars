"""Stream the original ESCI product file and retain only judged audio candidates."""

import json
from pathlib import Path

import fsspec
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1] / "data"
snapshots = json.loads((ROOT / "snapshots.json").read_text())
examples = pq.read_table(ROOT / "esci_audio_examples.parquet")
target_ids = pc.unique(examples["product_id"])
url = (
    f"https://media.githubusercontent.com/media/amazon-science/esci-data/"
    f"{snapshots['amazon-science/esci-data']}/shopping_queries_dataset/"
    "shopping_queries_dataset_products.parquet"
)
fs = fsspec.filesystem("http")
selected = []
seen = 0
with fs.open(url, block_size=8 * 1024 * 1024, cache_type="readahead") as stream:
    file = pq.ParquetFile(stream)
    for batch in file.iter_batches(batch_size=65536):
        table = pa.Table.from_batches([batch])
        match = pc.and_(
            pc.equal(table["product_locale"], "us"),
            pc.is_in(table["product_id"], value_set=target_ids),
        )
        subset = table.filter(match)
        if len(subset):
            selected.append(subset)
        seen += len(table)
        print(f"Scanned {seen:,} product rows; retained {sum(map(len, selected)):,}", flush=True)
        if sum(map(len, selected)) == len(target_ids):
            break
    pq.write_table(pa.concat_tables(selected), ROOT / "esci_audio_products.parquet")
print("Saved selected products", flush=True)
