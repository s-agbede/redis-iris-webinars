# Historical experiments

The active repository contains the Camera Search Lab. Superseded material is
preserved in commit `728be2e` (the full camera lab snapshot before cleanup):

- `proposals/`: travel and dataset investigations, source snapshots and their licences.
- `seed/`: the old apparel records, customer/order data, hero products and store policies.
- `scripts/generate_descriptions.py`, `normalise_thelook.py`, `validate_seed.py`:
  the old apparel preparation tools, which do not work with the current settings.
- `schemas/policies.yaml`: the old policy index.
- `docs/superpowers/`: completed implementation plans and design notes.

Inspect a historical file without changing your checkout:

```bash
git show 728be2e:proposals/travel/demo-queries.md
```

Use the complete historical revision when investigating old code; individual old
scripts may depend on settings or models that have since changed. The historical
snapshot itself contains both the camera app and older assets, not a separately
supported apparel application.
