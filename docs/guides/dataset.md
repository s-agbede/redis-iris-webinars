# Dataset and provenance


The bundled corpus comes from [Amazon ESCI](https://github.com/amazon-science/esci-data)
at revision `7916cdf6ab75a462e77f20ab40428a10923998d5`, with its Apache 2.0 license
and notice in `seed/cameras/`.

| Item | Count |
|---|---:|
| Selected English/US photography queries | 183 |
| Distinct US product records | 2,317 |
| Original query–product judgements | 3,147 |
| Derived retrieval passages with default settings | 8,472 |
| Products without a description | 969 |
| Products without bullet points | 146 |

The initial keyword slice contained 497 queries and 5,602 products. The explicit
inclusion decisions are in `seed/cameras/query-selection.json`. For each selected
query, **all judged candidate products are retained**, including irrelevant
candidates, accessories and unrelated products. This is a query-selected search
corpus, not a verified photography taxonomy or a complete camera catalogue.

Each product preserves the original seven fields: ID, title, description, bullet
points, brand, color and locale. There are no supplied images, prices, stock,
reviews, mount facets or verified compatibility rules. Missing fields remain
missing. Some listings contain contradictory copy; the inspector keeps the
original fields visible instead of filling gaps or resolving claims by guessing.

The app adds **9 locally stored reference photos for 16 product records** as a
separate enrichment. These cover Nikon D610/D5600/W300, Sony A7R II/ZV-E10, and four Canon
lenses. Result cards and the inspector show the photographer, source and licence;
captions identify body-only views, mounted lenses and the W300 colour difference.
Other products show a placeholder. The photos are bundled for offline demos and
do not alter the source records, embeddings or rankings. See
[photo credits](../../seed/photos/CREDITS.md) and the explicit product-ID mappings in
[the photo manifest](../../seed/photos/manifest.json). Photos retain their individual
CC BY-SA 3.0/4.0 licences. Startup verifies asset checksums and mapped product IDs.
To extend coverage, add a verified JPEG and attributed entry to that manifest,
then restart the app; no Redis reindex is required.

Original ESCI labels mean Exact, Substitute, Complement and Irrelevant. They are
sparse query–product judgements, not universal product labels. The UI attaches
them only when the submitted query exactly matches the original query text.
**Unjudged does not mean irrelevant.** Labels never enter the search text or
embeddings. Original train/test split values are preserved, but this selected demo
corpus and its chosen examples are not a held-out evaluation.

### Reproduce the subset

Normal setup uses bundled compressed JSONL and verifies its checksums. To rebuild
it, obtain the original `shopping_queries_dataset_products.parquet` and
`shopping_queries_dataset_examples.parquet` from the pinned ESCI revision's
`shopping_queries_dataset/` directory, resolving Git LFS files. Then run:

```bash
uv run --extra prepare python scripts/prepare_cameras.py \
  --products /path/to/shopping_queries_dataset_products.parquet \
  --examples /path/to/shopping_queries_dataset_examples.parquet \
  --output /tmp/camera-subset
```

The arguments also accept HTTPS URLs. The script streams Parquet batches and
uses the bundled reviewed query selection. It verifies every selected source
record against the canonical bundle and fails on missing or changed products or
judgements. Product values and judgement pairs reproduce the bundled
corpus; row order and gzip bytes may differ by source export or compression
runtime. The generated manifest records its actual file checksums. To use a
rebuilt corpus, set `DATA_DIR=/tmp/camera-subset`, reseed and restart.
