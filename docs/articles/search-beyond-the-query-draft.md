# What happens after search works?

*Building a camera shop to understand full-text, vector and hybrid search—and what keeps the results useful when the catalogue changes.*

I’ve been building a small camera shop for a talk on search.

The initial idea was fairly straightforward: take the same catalogue, search it in different ways, and make the differences visible. A user types a query. Full-text, vector and hybrid search return their results. We look at what each method found and try to understand why.

Then I added a camera while indexing was paused.

The product had been saved successfully. I could see its record in Redis. But search couldn’t find it.

That little demonstration became a useful way to explain something easy to miss when we focus on retrieval algorithms: a search system has several different kinds of correctness. Finding relevant text is one of them. Keeping that text connected to the current state of the application is another.

## Start with what the shopper means

Imagine two people searching for a camera.

One types:

> sony zv e10

The other types:

> a compact camera for filming myself

The first person knows a model. The second knows what they want to do, but may not know the terminology used in the product listing.

Those are different demands on the search system.

Full-text search gives us a way to retrieve passages through the terms in the query. In this app, BM25 provides the lexical relevance score. That makes it useful to investigate when names and model identifiers matter.

Vector search embeds the query and compares it with embeddings of the indexed passages. That gives us another route into the catalogue when the shopper’s wording differs from the listing’s wording.

But semantic similarity doesn’t establish that a product satisfies the request. A passage can be very close to the topic of vlogging and still describe the wrong camera, an accessory, or a product missing a required feature.

I wanted the demo to make that distinction visible. You can inspect the passage that brought a product into the results, rather than trusting its position on the page.

Hybrid search combines the lexical and vector branches. We use Reciprocal Rank Fusion, or RRF, to combine their ranked lists. RRF uses positions in the lists; it does not read the product description and decide afresh whether it answers the question. Redis performs the fusion inside its native [hybrid search command](https://redis.io/docs/latest/commands/ft.hybrid/).

This is also where architecture diagrams can become confusing. BM25 and vector similarity already order results during retrieval. RRF combines those orders. Putting another box labelled “ranking” after all three can imply that we have a separate relevance model when we don’t.

A cross-encoder or an LLM could provide that additional reranking stage. I left it out of this demo. Before adding one, I’d want to show that the right product is entering the candidate set but appearing too far down, then test whether reranking improves that behaviour enough to justify the extra latency.

## What are we actually searching?

The shop uses a photography-query subset of Amazon’s ESCI dataset: 2,317 product records, producing 8,472 passages with our default settings.

It is a useful teaching corpus partly because it is untidy. Some products have no description. Others have long bullet points, inconsistent metadata, or copy that needs careful reading. We preserve the candidate products associated with the selected source queries, including irrelevant ones. This isn’t a neatly curated catalogue in which every query has an obvious winner.

It also doesn’t supply live stock, prices or verified compatibility rules. When I talk about the live catalogue here, I mean the product records managed by the demo. I’m not claiming to have built an inventory-management system.

Each source listing keeps its original fields. We clean the text and split the title, description and bullet points into bounded passages, with some title and brand context attached. Each passage keeps its product ID, source field and offsets into the cleaned text.

That gives us a path back from a search result to the evidence behind it.

The indexing path looks like this:

```text
Product record
    ↓
Clean and split into passages
    ↓
Generate local embeddings
    ↓
Store passage JSON in Redis
    ↓
Redis Search indexes the configured fields
```

The schema describes how those fields should behave: searchable text, categorical tags such as brand, and a vector field for the embedding. RedisVL is the Python library we use to define the index and construct queries. Redis stores the records and executes the searches.

The embeddings come from a pinned local MiniLM model with 384 dimensions. Once setup is complete, the demo runs without a hosted embedding API. Passage preparation lives in one shared Python function, used by initial seeding, ongoing synchronization and replacement-index builds.

At query time, the flow is:

```text
Query and selected filters
    ↓
Query interpretation and normalization
    ↓
Selected retrieval method
(full-text, vector or hybrid)
    ↓
Validate against the live catalogue
    ↓
Keep the best passage per product
    ↓
Product results and source evidence
```

The comparison page runs the methods separately so their results can be inspected side by side. It doesn’t feed all three into a fourth shared ranker.

Query interpretation is deliberately modest. For example, an unambiguous leading brand can become a filter, while wording about compatibility or alternatives is left alone. “Sony camera” and “a lens compatible with Sony” should not automatically impose the same brand restriction.

The interface also uses Redis autocomplete to suggest catalogue terms while someone types. That helps people explore the data, but it is separate from passage retrieval.

## The first production question: will search notice a change?

Here is the freshness demonstration.

I pause the indexing worker and add a fictional camera through Manage shop. The application saves the product and appends a change event to a Redis Stream in the same transaction.

The catalogue now contains the camera. The stream contains work waiting to be processed. The search index still has no passages for that product.

Search cannot discover it yet.

When I resume indexing, the worker consumes the event, prepares the passages and embeddings, and writes the indexed records. The camera becomes searchable without being submitted again.

There is a small implementation detail here that prompted a surprisingly useful question: the event contains only the product ID. How does the worker know whether to add or remove it?

The event tells the worker which product needs synchronization. The worker reads the current catalogue state:

```python
# Simplified to show the decision.
product = get_product(product_id)

if product is None:
    remove_indexed_passages(product_id)
else:
    replace_indexed_passages(product)
```

If the product exists, prepare its current passages. If it has been deleted, remove its old passages.

This is useful when several changes happen before the worker catches up. Suppose I add a camera and delete it while indexing is paused. Reading current state prevents the worker from recreating the deleted camera from an old add payload. Revision checks also prevent a product change during embedding from being overwritten by the work already in progress.

There is another protection at query time: the application checks retrieved candidates against the live catalogue. That hides deleted products while their old passages await cleanup.

But it cannot make a newly added product discoverable. For that, indexing still has to happen.

For the presentation, I kept the shopper’s behaviour consistent. Normal search hides deleted products; Redis Insight lets us inspect any remaining stale passages. Adding a special shop mode that deliberately showed deleted listings made the explanation harder to follow.

## What if the worker itself fails?

Pausing a worker proves that unread events can wait. It doesn’t prove that an event already being processed will recover after a crash.

Redis consumer groups distinguish between unread events and pending events. Pending means the event has been delivered but has not yet been acknowledged. Our worker uses [XAUTOCLAIM](https://redis.io/docs/latest/commands/xautoclaim/) to recover eligible pending work left by an earlier consumer.

That recovery requires safe retries. We use deterministic passage keys and replace the product’s passages, so another attempt doesn’t append a second copy of the same records.

The API and worker now run in separate Python processes. A small local supervisor restarts an exited process. During verification, we killed the worker and ran eight search comparisons while it recovered. Those searches succeeded, and the API process stayed running.

That tests a specific failure boundary. It doesn’t establish high availability for the whole application: the supervisor still needs to be started again after a machine restart, and Redis durability depends on its persistence configuration.

Some failures also won’t be fixed by restarting a process. A particular product might repeatedly fail preparation. We give processing failures three attempts with backoff, then move exhausted events to a failed stream with the product ID, original event ID, error and attempt count.

Manage shop shows those failures and provides a Retry action after the cause has been addressed. Redis connection failures are handled separately; an unavailable database shouldn’t consume every product’s retry budget.

One consequence is easy to overlook: zero unread events and zero pending events no longer mean everything succeeded. You also have to check the failed queue.

Index writes and successful acknowledgement are queued in one Redis transaction. That prevents other operations from interleaving with the transaction, but Redis transactions do not roll back individual command runtime errors. The error path still deserves attention.

## The second question: what happens when everyone searches?

A quick response to one query tells us very little about concurrent demand.

For the performance demonstration, I use a separate endpoint that executes hybrid search alone. The comparison page runs multiple retrieval methods and collects explanation data, so it represents a different workload.

The traffic runner sends a fixed mix of queries and filters with bounded concurrency, duration and request deadlines. We measure client-observed p95 latency, completed searches per second, and errors or timeouts. Backend timings help separate embedding work, Redis retrieval and product fetching.

Holding the workload constant matters. Changing the query mix at the same time as the implementation makes it difficult to know what caused the difference.

One improvement in the app is a bounded cache for repeated query embeddings. Its key includes the embedding model, revision and query input. A cache hit saves the embedding computation; the request still searches Redis and checks current product records.

That is different from caching the search response or reusing an answer to a semantically similar question.

It also has an obvious limitation: queries that haven’t been seen still need embedding. The demo’s repeated workload is useful for showing the mechanism, but the benefit in another application depends on its traffic.

I’m keeping the measurements local to the experiment. The traffic generator, model, API and Redis share one computer. Short runs on that machine are observations about that setup, not evidence of production capacity.

And faster successful requests are only part of the result. If failures or rejections increase, those need to stay in the comparison.

## The third question: can I replace the index while people use it?

The initial seed script can rebuild the index as a setup operation. Doing the same thing to the serving index would expose the application to a period of missing or incomplete search data.

So the live rebuild takes a different path.

Version one continues serving while version two is built separately. Each version owns a distinct passage-key prefix. That detail matters: separate index names do not isolate the underlying records if both versions point at the same document keys.

Before switching, we validate passage coverage, content and selected relevance cases. We also need to account for catalogue changes that happened during the build. A replacement that matches yesterday’s catalogue can be complete and still be wrong for today’s traffic.

The synchronization worker updates the retained versions, and cutover requires an empty backlog, no unresolved failed events, and validation against the current catalogue revision. If the catalogue changes after validation, we validate again.

Redis provides [FT.ALIASUPDATE](https://redis.io/docs/latest/commands/ft.aliasupdate/) to change which index an alias references. The app also maintains a serving registry and pins one concrete index version for each comparison, so the methods in that comparison use the same version.

```text
v1 serves → build v2 → validate and catch up → switch → retain v1
                                                        ↓
                                            rollback if still ready
```

Keeping v1 around gives us a rollback option, provided it remains current enough to serve. Merely retaining its keys is insufficient.

For this demo, both versions use the same embedding model and can reuse unchanged passage embeddings. Changing the model would add another coordination problem: query embeddings and indexed embeddings must remain compatible during the transition.

## What I want people to take away

Building the slides helped me separate four questions that can otherwise collapse into “does search work?”

| Question | What I need to inspect |
|---|---|
| Are the results useful? | Relevance and source evidence |
| How long does a request take? | End-to-end latency and its contributing stages |
| How much demand can the system handle? | Throughput, latency and failures under a defined workload |
| Does search reflect the current catalogue? | Freshness, pending work and failed changes |

A search can be fast and stale. It can return relevant results for one person and struggle under concurrent traffic. It can perform well until the next index rebuild.

The camera shop gives me a concrete place to demonstrate each of those behaviours. There are still limits: a small corpus, one local Redis deployment, a simple supervisor, and no separate reranking model. The demonstrations make particular mechanisms inspectable; they don’t certify a production system.

The same questions will matter when this becomes context retrieval for an agent. A stale passage can become stale context. A missing record can change what an agent believes is available. Retrieving more text won’t repair a synchronization failure.

For the later sessions, I want to keep the same scenario and build on it: retrieving evidence for a camera comparison, remembering a simulated shopper’s preferences, and deciding when an answer is safe to reuse. Those are future extensions, rather than capabilities the current search demo already has.

For now, the question I’d take into another retrieval project is: when the source changes, a worker fails, or a new index goes live, what evidence will tell me that search still reflects the world it is supposed to represent?

The demo code is in [redis-iris-webinars](https://github.com/s-agbede/redis-iris-webinars). If you’re building something similar, I’d be interested to hear which failure you tested first.
