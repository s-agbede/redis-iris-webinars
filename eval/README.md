# Product-focused search evaluations

Run `make eval` against the prepared local Redis service and embedding model.
It runs ten queries across Basic, full-text, vector and hybrid, writes
`eval/latest.json`, and exits nonzero on retrieval errors or failed configured
full-text/hybrid checks. Use `uv run python -m eval.run` for report-only quality
assessment (retrieval errors still fail).

## Targets

| Product | Cases | Acceptable targets |
| --- | --- | --- |
| Sony ZV-E10 | 4: exact model, spaced model, camera intent, Sony filter | Body B09BBKVMCD or kit B09BBMQKSR |
| Nikon D610 | 3: exact model, reordered camera intent, Nikon filter | Body B00FOTF8M2 or renewed body B014I11JV0 |
| Canon RF 85mm F1.2 L USM | 3: exact model, aperture punctuation, Canon filter | Lens B07RB7SHD7 |

The configured expectation is an acceptable target in the first three products
for full-text and hybrid. These model-identification queries should be supported
by lexical matching and preserved by hybrid retrieval. Basic and vector report
the same target-rank assessment, but do not gate the command: they demonstrate
literal substring and semantic retrieval limitations. Autocomplete suggestions
are a separate interaction and are not assessed by these product-ranking cases.

Each result records the first acceptable target rank, reciprocal rank within the
returned top five (zero when absent), relevant/irrelevant/unreviewed counts, original
source-label coverage, and per-method query latency. Shared embedding time is
recorded separately in the comparison. This single sequential run is not a latency
benchmark. No search implementation was changed for this suite.

## Recorded run

[product-observations.json](product-observations.json) records the September 15,
2026 local run: 40 rankings, zero execution errors, and 20/20 configured checks passed.

| Method | Target in top three | Target ranked first |
| --- | --- | --- |
| Basic | 5/10 | 5/10 |
| Full-text | 10/10 | 10/10 |
| Vector | 7/10 | 6/10 |
| Hybrid | 10/10 | 10/10 |

Sony is the useful contrast: Basic returns a compatible strap for `Sony ZV-E10`
and no results for `sony zv e10`. Vector puts a target at rank five for both,
and misses it in the top five for `Sony ZV-E10 vlog camera`. Full-text and hybrid
rank a target first for all four Sony cases.

## Judgement limits

These are assistant-reviewed judgements based on bundled catalogue titles and
bullet points, separate from original ESCI annotations. Compatible accessories
and explicitly reviewed wrong models are irrelevant to these exact-product
requests; unknown results remain unreviewed. Body/kit and renewed variants are
accepted where the query does not exclude them. The cases and top-three threshold
were authored before this focused run. This is a small regression/demo suite,
not held-out evidence of general search quality.

Historical `demo-observations.json` and `learning-observations.json` describe older,
different cases. `--all-source` remains available to explore the original source
queries; it is not equivalent to this focused regression suite.
