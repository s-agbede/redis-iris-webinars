# Product reference photos implementation plan

User approved getting photos for the seven suggested searches. Continue inline using the executing-plans workflow; preserve unrelated uncommitted work.

**Goal:** Attach verified, attributed product-model photos to matching catalogue records and display them in the local camera search lab.

**Architecture:** A separate `seed/photos/manifest.json` maps exact product IDs to locally stored reference photos with source URL, author, licence and caption. Photos never enter indexed source fields or embeddings. FastAPI returns an optional photo on each hit and product detail and serves local assets. React displays images with attribution and a clear fallback. Some images show only the base model or a mounted lens; captions explicitly describe that and distinguish these from seller listing photos.

**Stack:** Existing FastAPI/Pydantic and strict React/TypeScript. No new dependencies, hosted models or Redis rebuild.

- [x] Collect source-confirmed Commons photographs, verify depicted models and licence, save local assets and exact-ID mappings. Never map a camera photo to an accessory just because its title mentions that camera.
- [x] Add failing API tests: photo metadata survives comparison/detail, unmapped product returns null, local photo route serves valid bytes and unknown paths return 404.
- [x] Implement `ProductPhoto`, optional `SearchHit.photo`/`ProductDetail.photo`, manifest loading and startup validation; serve `/photos` from the photo asset directory.
- [x] Add a reusable React photo component to result cards and inspector. Preserve card keyboard actions; use contained images, visible model-reference caption, source/author/licence links, and a fallback on missing/failed loads.
- [x] Update README with actual coverage and source licences. Run focused/full tests, Python checks, frontend build and live browser photo/attribution/mobile verification. Reload only the camera app on port 8001.

## Acceptance checks

`GET /api/products/B00FOTF8M2` includes the Nikon D610 reference photo; a product without a mapping has `photo: null`. `GET /photos/nikon-d610.jpg` returns image/jpeg. Retrieval ranks and source records remain unchanged. The three-column layout shows useful photos while retaining passage evidence and rankings. Downloaded photos and attribution are available offline.

## Verification

- 8 locally stored Commons JPEGs (2.9 MB) mapped to 14 original catalogue records; all asset hashes and product IDs verified.
- 30 Python tests passed; the separately enabled live Redis/model integration test also passed. Ruff and strict mypy passed.
- Strict TypeScript/Vite build and all 5 existing frontend tests passed.
- Browser verified Nikon photos and credits in all three columns and inspector, Escape/focus restoration, and a 390px mobile viewport with no horizontal overflow.
- Independent photo review found no concrete blockers. Camera app restarted on port 8001; no index rebuild.
- Bag and tripod matches have no verified reusable photos from the sources checked and retain placeholders. W300 colour and body/lens bundle differences are explicit in captions.
