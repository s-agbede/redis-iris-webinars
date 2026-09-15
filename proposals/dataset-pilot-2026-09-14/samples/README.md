# What are we searching?

We are searching product listings: headsets, headphones, earbuds, and related accessories. The proposed application helps someone find the right product and understand its compatibility. Amazon's ESCI dataset supplies both product text and customer search queries with relevance judgements.

These are actual records from the retained pilot data. The JSON exports preserve every source product field and value, including missing descriptions, HTML, marketing copy, and imperfect metadata. The short product names and explanations below are editorial summaries.

- [Five complete product records](products.raw.json)
- [Two original query–product judgements](query-judgements.raw.json)
- [Full pilot findings and methodology](../README.md)

## Dataset overview

| Dimension | Full source release | Our retained pilot |
|---|---|---|
| Product records | 1,814,924 | 4,349 |
| Search queries | 130,652 | 444 |
| Query–product judgements | 2,621,288 | 8,415 |
| Languages / locales | English / US, Spanish / ES, Japanese / JP | English / US |
| Scope | Shopping across product categories | Queries containing `headphone`, `headset`, or `earbud`, and all products judged for those queries |

The pilot includes accessories and other candidate products that may be poor matches. They are useful distractors when comparing search methods. This selection is a focused demonstration corpus, not a representative sample of all shopping traffic.

Full-release query statistics and schema: [official Amazon ESCI repository](https://github.com/amazon-science/esci-data). Product-record counts come from the source Parquet metadata; pilot counts come from the retained files. The source is pinned to commit `7916cdf6ab75a462e77f20ab40428a10923998d5`.

## Five products you can inspect

| Short name | Product ID | What the source listing says | Search question it makes tangible |
|---|---|---|---|
| Logitech H340 | `B008X3JGSI` | USB digital audio, rotating boom microphone, Windows and Mac | Can we find a headset for calls using connectivity and usage needs? |
| ASTRO A40 TR X-Edition | `B07FYY2CMH` | Gaming headset with a swappable microphone; red and black | Does an A40 query retrieve the actual headset? |
| ASTRO-compatible replacement cable | `B089VVH8HC` | A10/A40 cable with an inline mute function and 3.5 mm connections | Can an accessory outrank the product because it repeats the same model names? |
| Beexcellent GM-1 | `B07GGCM89X` | Blue gaming headset; 3.5 mm audio connection; USB powers the light | Does a mention of USB actually satisfy a USB-audio requirement? |
| Master & Dynamic MH40 | `B00MWDGW28` | Wired, over-ear, noise-isolating headphones | Can we distinguish the intended product from alternatives and cases? |

These descriptions reflect the dataset snapshot, not a current product catalogue.

### Actual searchable text

The Logitech record has this title:

> Logitech USB Headset H340, Stereo, USB Headset for Windows and Mac - Black

Its bullet text includes:

> Plug-and-play USB connection: Simply plug the headset into your PC for quick and easy stereo audio

> Clear digital sound: Pure USB digital audio for crystal clear music and calls

The Beexcellent record contains a different connectivity statement:

> The usb is to power the led light.

That distinction supports a later context-retrieval scene: retrieve and cite the passage that answers whether USB carries audio. A keyword appearing in a listing does not by itself establish compatibility.

## How a search query connects to a product

The source query `astro headphones a40` has these two actual judgements:

| Query ID | Product | Source label | Meaning for this query |
|---|---|---|---|
| 10804 | ASTRO A40 headset — `B07FYY2CMH` | E — Exact | The product being sought |
| 10804 | Replacement cable — `B089VVH8HC` | C — Complement | An accessory for the product |

The other labels are S — Substitute, an alternative, and I — Irrelevant. A label belongs to a query–product pair, not to the product permanently. A cable could be the exact result for a different query.

The product table and judgement table join on **both `product_id` and `product_locale`**. The two judgement exports retain the six columns selected for the pilot, including the original `split: train` value. They do not contain every column in the full source examples file.

The dataset judges a limited candidate set per query, up to 40 products. A retrieved product without a judgement is unjudged, not automatically irrelevant. We also found some imperfect labels in the pilot, so a live example still needs human review.

## What goes into the search index?

| Field | Role in our pilot |
|---|---|
| `product_title` | Searchable product name, model numbers, and attributes |
| `product_description` | Searchable longer description; sometimes absent or HTML |
| `product_bullet_point` | Searchable features and compatibility details |
| `product_brand`, `product_color` | Included in searchable text; available as metadata, subject to quality checks |
| `product_id`, `product_locale` | Identity and joining records; locale selects the US subset |
| Derived embedding | Computed from product text for vector search; not supplied by ESCI |

Full-text and vector search use the same product content. Hybrid search combines their rankings. Search queries and relevance labels stay outside the indexed product content and are used to evaluate results.

## What the data gives us for later webinars

| Webinar | Reuse from this corpus | What we must add |
|---|---|---|
| Context retrieval | Product passages about USB audio, microphones, and compatibility | A question and an answer flow that cites the retrieved evidence |
| Semantic caching | Existing queries and stable product information | Reviewed equivalent-question pairs, contrasting requirements, cached answers, and source-version handling |
| Agent memory | The same catalogue and compatibility facts | Clearly fictional user sessions, such as remembering that a workstation lacks a 3.5 mm port, then updating that constraint |

ESCI does not supply conversation histories, user preferences, prepared embeddings, or cache-equivalence labels. It also has no structured price, stock, or product-update history fields. Those omissions constrain the demo: price filtering or real update-throughput claims would require additional data or a clearly identified simulated workload.

Real data preparation remains part of the engineering story. In this subset, 2,192 descriptions are missing (50.4%), and 508 bullet fields are missing (11.7%). The replacement cable's `product_color` is literally `mute function`. The JSON preserves this value so that a clean schema is not mistaken for clean source data.

## Attribution

Product and judgement data: Amazon Shopping Queries Dataset / ESCI. Copyright Amazon.com, Inc. or its affiliates. Licensed under Apache License 2.0; see the retained [licence](../licenses/ESCI-LICENSE.txt) and [notice](../licenses/ESCI-NOTICE.txt). This sample is a JSON export from the pinned source records, with no rewritten product values.
