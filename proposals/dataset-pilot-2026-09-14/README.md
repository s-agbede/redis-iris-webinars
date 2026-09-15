# Dataset pilot: ESCI audio versus Kubernetes documentation

**Recommendation: use the ESCI audio subset as the shared corpus for the four-webinar series.** It produced three understandable search contrasts, contains real query pairs for the caching session, and supplies enough factual product text for a memory and context-retrieval story without writing fictional product specifications.

Kubernetes remains a good alternative for an audience already familiar with infrastructure. It has stronger document provenance and a particularly useful cache counterexample, but needs more authored queries and more domain explanation during a short session.

This recommendation is based on a small exploratory retrieval run and source inspection. It is not a claim that either dataset or search method is generally superior. No changes were made to the existing application, datastore or project dependencies.

## What was actually inspected and run

| | ESCI audio | Kubernetes |
|---|---|---|
| Source | Amazon Shopping Queries / ESCI | Official Kubernetes documentation repository |
| Selection | US queries containing `headphone`, `headset` or `earbud`; retain all their judged candidate products | Focused English documentation directories covering workloads, networking, configuration, security and troubleshooting |
| Documents retained | 4,349 product records | 166 Markdown pages; 163 indexed after excluding three very short pages |
| Search inputs | 444 original queries; 8,415 query-product judgements | 12 authored queries, specified before the first retrieval run |
| Indexed passages | 9,370 | 2,188 |
| Queries/history we invented | None for the search comparison; future user sessions are authored | All 12 search queries and future user sessions are authored |

The ESCI selection also retains accessories and other distractors associated with those queries. It is not a random or representative sample of all shopping traffic. There are 339 training-split and 105 test-split queries, but all were used for exploration; this report does not claim a held-out evaluation.

Both corpora used the same implementation: BM25 with English stemming; local `all-MiniLM-L6-v2` float32 ONNX embeddings with mean pooling and normalization; exhaustive cosine search; and equal-weight reciprocal rank fusion with constant 60 and the top 50 parent documents from each leg. Passage scores are combined into parent-document scores by taking the maximum. The same passages are available to both methods. Inputs use up to 250 content wordpieces including a title prefix, with 40-wordpiece overlap in the body.

No external embedding service, production search engine, approximate vector index, semantic-cache service or agent-memory service was used. The experiment establishes interesting examples and data-preparation requirements, not deployment performance. Examples were selected after inspecting the results.

## Three ESCI search moments

The cells below show the first result. Full product IDs, titles, scores and the top ten results are in `evidence.json` and `data/esci/results.json`.

| Original query | Full-text | Vector | Hybrid | What it teaches |
|---|---|---|---|---|
| `beexcellent gm-1 gaming headset blue` (14708) | Beexcellent GM-1 | Beexcellent GM-3 | Beexcellent GM-3 | A requested model number can be lost through semantic similarity and fusion. Treat a strict model requirement as an exact constraint. |
| `astro headphones a40` (10804) | Replacement cable | ASTRO A40 headset | Replacement cable | Accessories repeat the main product's terms. Here vector retrieves the requested product, and fusion promotes the cable again. |
| `master dynamics headphones` (66249) | Carrying case | Master & Dynamic in-ear earphones | Master & Dynamic MH40 over-ear headphones | Fusion can promote a candidate supported by both rankings. ESCI labels the first results C, S and E respectively. This is a benchmark-based improvement; the query itself does not explicitly demand over-ear form. |

These do not demonstrate a universal hierarchy of methods. They show a lexical advantage, a vector advantage with a hybrid regression, and an example of useful fusion in one fixed setup. The ASTRO example is especially easy to judge from the product titles: a replacement cable is not a headset.

### The labels require inspection

For query 14708, ESCI labels both the GM-1 and GM-3 products `E`. The original product title and specifications identify the latter as GM-3. For a demo that treats the requested GM-1 model as mandatory, that is a conflict with the intended acceptance rule.

Another concrete conflict: query 112113 asks for headphones **without deep bass**, while candidate `B08PCZTTQW`, whose title explicitly includes **Deep Bass**, is labelled `E`.

Retain these source labels unchanged and add a separate, documented demo acceptance rule. Do not silently repair the data or use `E` as proof that every application constraint is satisfied.

The labels are also sparse across the combined 4,349-product corpus. Between 304 and 309 of the 444 first results are unjudged, depending on the method. This is why this report does not publish overall precision or recall. A fuller evaluation should either rank each query's supplied candidate list or judge the newly retrieved results.

## Three Kubernetes search moments

| Authored query | Full-text first result | Vector first result | Hybrid first result | Interpretation |
|---|---|---|---|---|
| `CrashLoopBackOff` | Pod Lifecycle | Pod Lifecycle | Pod Lifecycle | All three locate the same relevant source. The identifier does not automatically defeat vector search. |
| `readinessProbe stop traffic while the application warms up` | Pod Lifecycle | Configure Liveness, Readiness and Startup Probes | Configure Liveness, Readiness and Startup Probes | Vector and hybrid surface the focused task guide. The broader lifecycle page is also relevant, so this is not a binary full-text failure. |
| `Stop sending customers to my application until it has finished starting` | Pod Lifecycle | Automatic Cleanup for Finished Jobs | Automatic Cleanup for Finished Jobs | The semantic model confuses startup readiness with completed jobs. Fusion does not rescue the request. |

These are honest teaching examples, but the audience must understand readiness, lifecycle and job completion to judge them. They also expose limitations of this particular small embedding model and passage/document aggregation, rather than proving that the source corpus is deficient.

## One scene for each later webinar

All the scenes below are designs grounded in the inspected data. The conversations, users and expected actions are authored fixtures; no agent has been implemented or evaluated here.

### ESCI: agent memory

**Recurring task:** help a returning engineer choose headphones for their workstation.

1. Session one: the user states that the workstation has USB-A ports, no 3.5 mm audio socket, and that adapters are unacceptable. Store these as user-provided constraints with session provenance.
2. Session two: the user asks about the blue Beexcellent GM-1. Retrieve the remembered constraints and the original GM-1 product bullets.
3. Explain that its 3.5 mm connection carries audio and its USB connection powers the lighting. It does not satisfy the stated no-adapter setup. Surface the Logitech H340 as a candidate whose supplied text explicitly describes USB digital audio.
4. Session three: the user says they now have an audio adapter. Update the constraint and stop applying the previous blanket exclusion.

**Source records:** GM-1 `B07GGCM89X`, Logitech H340 `B008X3JGSI`.

**Added data:** one fictional user and three short sessions. No invented product specifications, prices, stock or policies are required. Memory should retain the user's history; product facts should remain grounded in the source corpus.

### ESCI: semantic caching

Use original source queries:

- Potential hit: `headphones without mic` (49768) and `headphones without microphone` (49769), assuming identical user context and source snapshot.
- Required miss: `earbuds with microphone` (36390) and `earbuds without microphone` (36391).

Measured query-vector cosine similarities were **0.9697** for the potential hit and **0.9156** for the required miss. At a threshold of 0.90, both pairs would qualify by similarity alone. A higher threshold separates these two pairs, but that does not establish a generally safe threshold.

**Added data:** cache acceptance judgements, source-version/context scope, and one source-grounded cached response per scenario. The query strings already exist. The measurements use a general retrieval encoder, not a dedicated cache model or a complete cache implementation.

### ESCI: context retriever

**Request:** compare GM-1, GM-3 and Logitech H340 for the remembered USB-only workstation requirement.

Retrieve the relevant connection-specification passages from all three records and the user's current constraint. The assembled context should distinguish a USB plug used only for lighting from USB digital audio and preserve record IDs beside the supporting passages.

**Source records:** `B07GGCM89X`, `B074PR1PB4`, `B008X3JGSI`.

**Added data:** a comparison prompt and expected evidence checklist. All product facts are already present. This gives context retrieval a distinct purpose: assemble the evidence needed to answer a comparison, beyond returning a list of similar products.

### Kubernetes: agent memory

Session one establishes a fictional engineer's namespace, container name, environment version and the fact that they already inspected the current logs. In session two they return to the crash investigation. Retrieve that history so the assistant can focus on the previous container instance's logs, grounded in **Debug Running Pods** and **kubectl logs**, without repeating the earlier step.

Add a later correction to the container name or environment version and verify that the previous value is no longer used. Remembered context must not grant access or substitute for live authorization checks.

**Added data:** a fictional environment and three sessions. Commands and their explanations come from the documentation.

### Kubernetes: semantic caching

Authored base question: `Show the logs from the previous instance of my container`.

- Potential hit: `How do I read the logs from my container before it restarted?` — cosine **0.7524**.
- Required miss: `Show the logs from the current instance of my container` — cosine **0.9491**.

For these pairs and this encoder, a single similarity cutoff cannot accept the first and reject the second. This is a particularly clear teaching example. Cache the documentation answer, not live container logs, and keep environment/version/request scope explicit.

**Added data:** all three questions, their reuse judgements and source-grounded response fixtures.

### Kubernetes: context retriever

**Request:** explain how to inspect the previous `api` container's logs in the fictional `payments` namespace.

Assemble the remembered environment, the previous-instance explanation from **Debug Running Pods**, and the relevant options from **kubectl logs**. Show which information came from the conversation and which came from a versioned document.

**Added data:** a fictional namespace/container, a prompt and an evidence checklist. The documentation supplies the command semantics. Additional sources or generated incident tickets are not necessary.

## Preparation cost and decision

| Work | ESCI audio | Kubernetes |
|---|---|---|
| Obtain a usable sample | Original 1.1 GB product Parquet has one row group; extracting the selected records required scanning it. The retained sample is included. | Markdown is easy to fetch by a pinned revision. The retained pages are included. |
| Clean source content | Strip HTML; retain bullets and metadata; inspect duplicated marketing text and missing fields. | Handle front matter, shortcodes, code examples and section boundaries. This pilot removes shortcodes and does not expand external code includes. |
| Search acceptance | Use original judgements as a starting point, then inspect cases and annotate strict requirements separately. | Write and review a small acceptance set from scratch. |
| Memory | Three authored sessions; no extra factual corpus needed. | Three authored sessions and an environment profile; no extra factual corpus needed. |
| Cache examples | Useful positive and negative query pairs already present; reuse labels still need authoring. | Author all pairs; the tested negative is particularly instructive. |
| Context retrieval | Product specifications plus user constraints support a practical compatibility comparison. | Task guide plus command reference plus remembered environment support troubleshooting. |
| Audience effort | Headset versus cable/case and USB-audio compatibility are visible with little explanation. | Requires some familiarity with pods, containers and the relevant operational task. |

ESCI has **2,192 missing descriptions (50.4%)**, **508 missing bullet fields (11.7%)**, and **444 records missing both (10.2%)**. Missing descriptions alone do not make the corpus unusable: the selected scenes have supporting bullet text. Keep the unknowns visible rather than generating specifications to fill gaps.

**Use ESCI audio for the general engineering series.** The decisive evidence is the combination of understandable search contrasts, real cache-pair candidates and an end-to-end compatibility story that needs only fictional user interactions. Use Kubernetes if the organiser confirms that infrastructure troubleshooting is a familiar shared activity; it is especially strong for source provenance and the caching failure example.

Do not add prices, inventory, proprietary support tickets or external policy documents to the first version. The inspected corpus already supports the proposed four scenes, and those additions would create new data-preparation and correctness work.

## Suggested 15-minute search episode

1. **0–2 minutes:** introduce the headphone-finding task and the difference between requested products and compatible accessories.
2. **2–5 minutes:** GM-1 versus GM-3; demonstrate why exact requirements need explicit treatment.
3. **5–8 minutes:** ASTRO A40 versus replacement cables; show vector improvement and the hybrid regression.
4. **8–11 minutes:** Master & Dynamic; show useful fusion and explain ranked-list combination briefly.
5. **11–13 minutes:** inspect one conflicting label and show the small acceptance set engineers should build.
6. **13–15 minutes:** relate the extra retrieval work to latency/freshness measurement, recap the decision and allow breathing room.

Only three live demo moments. The surrounding explanation should use the same screen, not introduce separate architecture, indexing and load-test demos. Reserve the USB-only returning-user scene for the memory episode.

## Evidence and reproduction

- `evidence.json`: selected results, source revisions, cache-pair measurements, corpus counts and explicit limitations.
- `data/esci/results.json`: all 444 exploratory queries, with each method's first ten results and original labels where available.
- `data/kubernetes/results.json`: all 12 authored queries and their results.
- `data/*.parquet`, `data/kubernetes_raw/`: the retained original source records.
- `scripts/compare.py`: lexical, vector and hybrid comparison. It reads the retained sample and runs locally.
- `scripts/verify.py`: checks joins, counts, source-file integrity, recorded cases and long-document chunk coverage.
- `requirements.txt`: versions used by the isolated analysis environment.

To rerun, create a separate environment with `uv`, install `requirements.txt`, and set `SEARCH_PILOT_MODEL_PATH` to a local snapshot of `sentence-transformers/all-MiniLM-L6-v2` at revision `c9745ed1d9f207416be6d2e6f8de32d1f16199bf`, including `tokenizer.json` and `onnx/model.onnx`. Run `scripts/compare.py esci` and `scripts/compare.py kubernetes`. The script regenerates embeddings locally. Source-fetch scripts are included separately; they are not needed to use the supplied sample.

The packaged source snapshots are:

- ESCI: [`7916cdf6ab75a462e77f20ab40428a10923998d5`](https://github.com/amazon-science/esci-data/tree/7916cdf6ab75a462e77f20ab40428a10923998d5).
- Kubernetes: [`5f9632dd3bdfd6dc15547b4f0796046d0ded0bed`](https://github.com/kubernetes/website/tree/5f9632dd3bdfd6dc15547b4f0796046d0ded0bed).

Retained ESCI records are attributed to Amazon.com, Inc. or its affiliates, under the source project's Apache 2.0 licence. Retained Kubernetes documents are attributed to the Kubernetes documentation contributors under CC BY 4.0; `data/kubernetes_manifest.json` links each original page. Raw documents are preserved; the retrieval text is cleaned and chunked as described above. Source licences and notices are in `licenses/`.
