# Webinar series planning constraints

User direction recorded on 2026-09-14.

- Plan for a software engineering audience and a 15-minute search webinar. A bank is an example audience, not a requirement to use banking data.
- Evaluate the concept independently of the existing Redis Iris webinar application, its domain, and its implementation.
- Choose the use case and learning objectives jointly with dataset availability. Do not promise a demonstration before establishing that suitable data can support it.
- Reuse the same core dataset and application scenario for later webinars on agent memory, semantic caching, and context retriever.
- Each webinar must provide an independently useful engineering lesson while extending the shared scenario.
- Explain relevance and application constraints alongside retrieval latency, update freshness, throughput, and operational trade-offs within the time budget.

## Dataset selection checks

- Establish accessibility, reuse rights, preparation effort, and reproducibility before committing to a domain.
- Search: sufficient text variety, specific terminology, structured metadata, and representative queries with assessable relevant results.
- Agent memory: a credible recurring task across sessions, with stable users or entities and useful facts that can change. A static source corpus alone does not demonstrate memory.
- Semantic caching: repeated equivalent requests plus similar requests that require different answers; define the context and source freshness within which reuse is valid.
- Context retriever: related source material, provenance, and metadata that support assembling relevant context for a task.
- Keep one shared source corpus. Any supporting simulated users, interaction histories, paraphrases, or update events must be clearly labelled and tied to that corpus.
- Use small datasets to demonstrate behaviour; scope performance claims to measured dataset sizes and workloads.

## Confirmed redesign direction

User decisions recorded on 2026-09-14:

- Redesign the application around the Amazon ESCI camera, lens, and photography-accessory data.
- Use RedisVL for the Redis search integration.
- Make the primary experience a search comparison lab showing full-text, vector, and hybrid results side by side.
- Keep the same core data and scenario available for the later agent-memory, semantic-caching, and context-retrieval webinars.

The initial English/US keyword slice contains 5,602 product IDs, 497 queries, and 8,700 query–product judgements. The reviewed photography selection now includes 183 queries, all 3,147 of their original judgements, and 2,317 product records. Unrelated judged candidates are deliberately retained. Default passage preparation yields 8,472 passages from complete source fields.

The user approved implementation with local models. The app uses Python/FastAPI, React/Vite with TypeScript, RedisVL, Redis in Docker, and a pinned MiniLM ONNX embedding model running on CPU. After preparation, no hosted model or API key is required. Later memory, caching and context-retrieval capabilities remain future work.
