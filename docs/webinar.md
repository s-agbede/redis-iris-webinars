# A 15-minute demonstration


| Time | Demonstration | Engineering takeaway |
|---|---|---|
| 0–2 min | State the task, available listing fields and definition of a useful result | Define relevance before choosing a search mode |
| 2–5 min | Run **Start with a model**: `sony zv e10`. Select the ZV-E10 and inspect its ranks and passages | Full-text ranks the ZV-E10 first; vector ranks it fifth and puts a ZV-1 first. Semantic proximity can lose an exact model requirement |
| 5–8 min | Run **Describe a need**: `a compact camera for filming myself` | Read the source to judge the need. Full-text's first result is a video head; vector and hybrid have different camera results. A ranking alone does not establish suitability |
| 8–12 min | Run **Add requirements**, then apply/remove the Sony brand filter. Inspect a hybrid result | Query words influence relevance; the same exact brand filter controls eligibility in all modes. Use passage ranks to explain RRF |
| 12–15 min | Open **Inside this comparison** and inspect commands | Separate embedding cost, retrieval and explanation overhead; design separate latency-under-load, throughput and freshness experiments |

Each guided example resets to all brands. The filter experiment keeps the query
unchanged and reruns all three methods. On narrow screens a product-rank matrix
stays above method tabs; select any product for the same shared evidence panel.
Showing three or five uses the existing response. Keyboard selection moves focus
to the panel; closing it returns to the selecting control.

The seven learning scenarios and actual rankings are recorded in
[learning observations](../eval/learning-observations.json), with the developer
experience checks in [the learning audit](search-learning-audit.md).
These queries are authored demonstrations, not newly judged relevance labels.
The older reviewed evaluation examples remain in `eval/demo-observations.json`.
The demo does not force a different winner for each mode.

`eval/cases.yaml` contains a limited assistant-reviewed pool of source-based
relevance judgements, separate from Amazon's original labels. Inspect those
judgements before presenting. `make eval` reports each mode's actual results,
original-label coverage and reviewed first-result assessment. It exits nonzero
on execution errors, not when a ranking improves or changes. To inspect all
selected source queries:

```bash
uv run python -m eval.run --all-source --output /tmp/all-camera-queries.json
```


## Extend the same scenario


The current app implements search comparison. Later episodes can reuse stable
product IDs, source revisions and evidence passages:

- **Context retrieval:** assemble cited evidence for a camera-kit comparison;
  expose missing or conflicting specifications instead of inventing answers.
- **Agent memory:** add explicitly simulated shoppers with remembered bodies,
  preferences and changing needs across sessions. These histories are new demo
  data, not part of ESCI.
- **Semantic caching:** add reviewed equivalent questions and near misses;
  scope reuse to user constraints, model and source version, with invalidation
  when that context changes.

Those capabilities are extension points, not implemented features in this version.

## Presentation materials

- [Presentation design brief](claude-design-search-webinar-prompt.md)
- [Series constraints](webinar-series-constraints.md)
