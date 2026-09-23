# Live rehearsal — 22 September 2026

Branch: `agent-memory`. Local app: `http://127.0.0.1:8011`.
Model: `gpt-5-mini`. Guidance: dedicated published `camera-adviser` Skill, version 1.
Only fictional shopper facts and bundled catalogue records were used.

## Observed working

- Browser onboarding created three separate RAM records for the camera, filming
  interests and lightweight preference. No session event was needed for those writes.
- A fresh conversation supplied zero prior session events and retrieved the
  shopper's long-term facts.
- A live recommendation searched the catalogue and returned two validated product
  cards, in 12.77 seconds for that turn. This is one observation, not a benchmark.
- A purchase question retrieved the fictional Sony ZV-E10 order dated 2026-04-18.
  Its card opened the actual catalogue details and attributed model-reference photo.
- Reloading the page restored the saved conversation and card. Switching to Jordan
  showed a separate empty conversation and an empty owner-filtered inventory.
- The inspector showed the published Playbook Skill's exact ID and version.

## Automatic reconciliation: observed, manually reviewed

The isolated evaluator created a direct onboarding fact:

> User currently owns a Sony a6400.

It then appended a user event stating that the Sony had been sold and the only
current camera was a Canon EOS R50. The application made no memory-update call.
The first changed inventory was observed **282.89 seconds** after evaluation began.

| Record | Before | After |
| --- | --- | --- |
| `camera-shop-5b91b914-e239-59f2-a2cd-a17ca9af2145` | User currently owns a Sony a6400. | User sold the Sony a6400 on September 22, 2026, and no longer owns it. |
| `1835f2ddea8e4b08b741ebf3c0c072dd` | Absent | User's only current camera is a Canon EOS R50 as of September 22, 2026. |

This preserves legitimate history while correcting present ownership. The script
returns `manual_review` for historical Sony records and dated paraphrases; it does
not infer correctness merely because a keyword appears. Inspection of these exact
records supports the reconciliation outcome.

## PII exclusion: failed in this configured store

The same run submitted a fictional `ram-demo-…@example.invalid` address together
with a preference for purple camera straps with tiny yellow ducks. Redis extracted
the useful preference **and retained the fictional email** in a separate record.
Owner isolation and empty new-session checks passed; the overall evaluation failed
because of the email observation. No real contact details were submitted.

Before presenting exclusion as a successful feature, verify the RAM store's
**Sensitive-data exclusions → Built-in detectors → Email address** configuration
and repeat with a fresh evaluator owner. If only semantic exclusions are enabled,
verify that their prompt covers email. Built-in detectors and semantic exclusions
are distinct controls. [Redis configuration reference](https://redis.io/docs/latest/operate/iris/agent-memory/create-service/#sensitive-data-exclusions).

The complete local evidence is `/tmp/shop-memory-live-evidence.json`. Reproduce
with `uv run python -m scripts.evaluate_shop_memory --timeout 420`. The script
preserves failures and never replaces observed records to manufacture a pass.
