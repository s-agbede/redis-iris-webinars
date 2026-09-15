import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { createRequestGate, errorMessage, requestJSON, type Catalog, type Comparison } from "./api";
import { Inspector } from "./Inspector";
import { formatTime, methods, ResultColumns } from "./results";
import type { VisibleCount } from "./learning";
import "./style.css";

const guidedExamples = [
  {
    kind: "exact",
    title: "Start with a model",
    query: "sony zv e10",
    objective: "See how a model name affects the full-text ranking.",
    next: "Select one camera. Compare its literal word overlap with the passage chosen by vector search.",
  },
  {
    kind: "intent",
    title: "Describe a need",
    query: "a compact camera for filming myself",
    objective: "Compare exact wording with a description of what you want to do.",
    next: "Inspect a product whose ranks differ. Read the vector passage and decide whether it supports the need.",
  },
  {
    kind: "constraint",
    title: "Add requirements",
    query: "sony camera for vlogging with interchangeable lenses",
    objective: "Separate words that influence relevance from a filter that controls eligibility.",
    next: "Apply the Sony brand filter, keeping this query. Inspect a hybrid result and follow the RRF contributions.",
  },
] as const;

function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [query, setQuery] = useState("");
  const [brand, setBrand] = useState("");
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [visibleCount, setVisibleCount] = useState<VisibleCount>(3);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const gate = useRef(createRequestGate());
  const selectionTrigger = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    setCatalogError("");
    requestJSON<Catalog>("/catalog", { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setCatalog(data); })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setCatalogError(errorMessage(cause)); });
    return () => controller.abort();
  }, [catalogAttempt]);

  useEffect(() => () => gate.current.cancel(), []);

  function invalidateComparison() {
    gate.current.cancel();
    setBusy(false);
    setComparison(null);
    setError("");
    setSelectedId(null);
    setHoveredId(null);
  }

  async function compare(nextQuery = query, nextBrand = brand) {
    const submittedQuery = nextQuery.trim();
    if (!submittedQuery || !catalog) return;
    const request = gate.current.begin();
    setQuery(nextQuery);
    setBrand(nextBrand);
    setBusy(true);
    setError("");
    setComparison(null);
    setSelectedId(null);
    setHoveredId(null);
    try {
      const data = await requestJSON<Comparison>("/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: submittedQuery, brands: nextBrand ? [nextBrand] : [], num_results: 5 }),
        signal: request.signal,
      });
      if (request.isCurrent()) setComparison(data);
    } catch (cause: unknown) {
      if (request.isCurrent()) setError(errorMessage(cause));
    } finally {
      if (request.isCurrent()) setBusy(false);
    }
  }

  function changeBrand(nextBrand: string) {
    setBrand(nextBrand);
    if (query.trim()) void compare(query, nextBrand);
    else invalidateComparison();
  }

  function selectProduct(id: string) {
    selectionTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSelectedId(id);
    if (selectedId === id) {
      document.getElementById("evidence-heading")?.focus();
      document.getElementById("product-evidence")?.scrollIntoView({ block: "start" });
    }
  }

  function closeEvidence() {
    setSelectedId(null);
    // A 3/5 toggle or a mobile tab change can remove or hide the original button.
    const candidates = [selectionTrigger.current, ...document.querySelectorAll<HTMLElement>(
      '.rank-matrix button[aria-pressed="true"], .product-select[aria-pressed="true"]',
    ), ...document.querySelectorAll<HTMLElement>(
      '.method-tabs [aria-selected="true"], .results-count button[aria-pressed="true"]',
    )];
    for (const target of candidates) {
      if (!target?.isConnected || target.getClientRects().length === 0) continue;
      target.focus();
      if (document.activeElement === target) break;
    }
  }

  const activeExample = guidedExamples.find((example) => example.query === query.trim());
  const sonyBrand = catalog?.brands.find((item) => item.value.trim().toLowerCase() === "sony")?.value;
  const hasPartialFailure = comparison && methods.some((method) => {
    const result = comparison.results.find((item) => item.mode === method.mode);
    return !result || result.error;
  });

  return <>
    <header className="site-header">
      <a className="brand-link" href="/" aria-label="Camera Search Lab home"><span className="lab-mark" aria-hidden="true"><svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M8 4H4v4M16 4h4v4M20 16v4h-4M8 20H4v-4" /><circle cx="12" cy="12" r="4" /></svg></span><span>Camera Search Lab<span className="brand-slash"> / </span><span className="brand-subtitle">Redis</span></span></a>
      <div className="connection-state"><span className={`status-dot ${catalog ? "connected" : catalogError ? "unavailable" : ""}`} />{catalog ? "Local search ready" : catalogError ? "Service unavailable" : "Connecting to local search"}</div>
    </header>
    <main>
      <div className="intro"><div><div className="eyebrow"><span className="eyebrow-rule" />A 15-minute retrieval lab</div><h1>One query. Three perspectives.</h1><p>Explore the words, passages, and rankings behind a search result.</p></div><div className="catalog-count"><strong>{catalog ? catalog.product_count.toLocaleString() : "—"}</strong><span>catalogue products<span>Camera query selection</span></span></div></div>

      {catalogError && <div className="error-box catalog-error" role="alert"><div><strong>The camera catalogue is not ready</strong><p>{catalogError}</p><p>Start the local services and prepare the camera index, then retry.</p></div><button type="button" onClick={() => setCatalogAttempt((value) => value + 1)}>Retry connection ↻</button></div>}

      <section className="guided-lab" aria-labelledby="guided-heading">
        <div className="guided-heading"><h2 id="guided-heading">01 / Choose a starting point</h2><span>Authored examples · each starts with all brands</span></div>
        <div className="guided-examples">{guidedExamples.map((example, index) => <button type="button" key={example.kind} disabled={!catalog} className={`guided-example example-${example.kind} ${activeExample?.kind === example.kind ? "active-example" : ""}`} aria-pressed={activeExample?.kind === example.kind} onClick={() => { setVisibleCount(3); void compare(example.query, ""); }}><span className="example-kicker">0{index + 1} / {example.title}</span><strong>“{example.query}”</strong><span className="example-objective">{example.objective}</span><span className="example-start">Run this example <span aria-hidden="true">↗</span></span></button>)}</div>
      </section>

      <section className="search-panel" aria-label="Compare a search query">
        <form onSubmit={(event) => { event.preventDefault(); void compare(); }}>
          <div className="search-controls">
            <label className="query-label" htmlFor="search-query"><span className="control-label">Your query <span>· affects relevance</span></span><span className="query-input-wrap"><svg width="21" height="21" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 5 5" /></svg><input id="search-query" value={query} onChange={(event) => { invalidateComparison(); setQuery(event.target.value); }} placeholder="A model, a use case, a detail that matters…" autoComplete="off" maxLength={1000} required /></span></label>
            <label className="brand-filter" htmlFor="brand-filter"><span className="control-label">Brand <span>· controls eligibility</span></span><select id="brand-filter" value={brand} disabled={!catalog} onChange={(event) => changeBrand(event.target.value)}><option value="">All brands</option>{catalog?.brands.map((item) => <option key={item.value} value={item.value}>{item.value} ({item.count})</option>)}</select></label>
            <button className="primary-button" type="submit" disabled={!catalog || !query.trim()}>{busy ? "Compare again" : "Compare search"}<span aria-hidden="true">↗</span></button>
          </div>
        </form>
        <div className="filter-lesson"><div><strong>03 / Try a hard filter</strong><p>Writing “Sony” influences relevance. The brand filter makes only Sony products eligible in all three methods.</p></div><button type="button" className="filter-action" disabled={!sonyBrand || !query.trim()} onClick={() => changeBrand(brand === sonyBrand ? "" : sonyBrand!)}>{brand === sonyBrand && sonyBrand ? "Remove Sony brand filter" : "Apply Sony brand filter"}<span aria-hidden="true">↻</span></button><span className="filter-rerun-note">Keeps your query and reruns the comparison.</span></div>
      </section>

      {activeExample && <div className="next-action"><span>Next step</span><p>{activeExample.next}</p></div>}

      <section className="results-section" aria-label="Search comparison" aria-busy={busy}>
        <div className="comparison-heading"><div><div className="eyebrow">Read the ranks, then inspect a product</div><h2>{comparison ? <>Results for <span>“{comparison.query}”</span></> : busy ? "Finding the connections…" : "Compare the ranking"}</h2></div><div className="results-count" role="group" aria-label="Visible results per method"><span>Show</span>{([3, 5] as const).map((count) => <button type="button" key={count} aria-pressed={visibleCount === count} onClick={() => setVisibleCount(count)}>{count}</button>)}</div></div>
        <div className="sr-only" role="status">{busy ? `Comparing results for ${query}.` : comparison ? `Comparison complete for ${comparison.query}. ${methods.map((method) => { const result = comparison.results.find((item) => item.mode === method.mode); return `${method.name}: ${!result || result.error ? "unavailable" : `${Math.min(visibleCount, result.hits.length)} of ${result.hits.length} fetched products shown`}`; }).join(". ")}` : "Choose an example or enter a query to compare three search methods."}</div>
        {error && <div className="error-box comparison-error" role="alert"><div><strong>The comparison could not finish</strong><p>{error}</p></div><button type="button" onClick={() => void compare()}>Retry comparison</button></div>}
        {hasPartialFailure && <div className="partial-failure" role="status"><p>Some methods are unavailable. Available results remain usable; the rank matrix marks missing methods as N/A.</p><button type="button" onClick={() => void compare()}>Retry comparison</button></div>}
        {comparison && <div className="comparison-meta"><span>Eligible brands: <strong>{comparison.brands.join(", ") || "All brands"}</strong></span><span>Same query · same filter · up to {visibleCount} shown per method</span><span className="rank-hint">Select a product to compare all three winning passages ↗</span></div>}
        <ResultColumns comparison={comparison} busy={busy} selectedId={selectedId} hoveredId={hoveredId} visibleCount={visibleCount} onSelect={selectProduct} onHover={setHoveredId} />
        <div className="comparison-notes"><p><strong>Read the ranks.</strong> Each method uses its own score scale; scores are not comparable across methods.</p><p>Up to five products per method are fetched once. Showing three or five does not rerun the search.</p></div>
        {selectedId && comparison && <Inspector key={selectedId} selectedId={selectedId} comparison={comparison} visibleCount={visibleCount} onClose={closeEvidence} />}
      </section>

      <details className="lab-details"><summary><span>Inside this comparison</span><span>Data, model & measurement <span aria-hidden="true">+</span></span></summary><div className="lab-details-grid">
        <section><h3>A shared source</h3><p>Searches use original product titles, descriptions, and bullet points, with bounded context from title, brand, and color prefixed to each indexed passage. Each method returns distinct products, keeping its best passage.</p><p>This selection keeps every judged candidate for the chosen photography queries, including unrelated products. Source listings can have missing or inconsistent details.</p><p>ESCI judgements describe original query/product pairs, not new relevance assessments of your search.</p>{catalog && <dl><dt>Products / passages</dt><dd>{catalog.product_count.toLocaleString()} / {catalog.passage_count.toLocaleString()}</dd><dt>Source revision</dt><dd><code>{catalog.source_revision}</code></dd></dl>}</section>
        <section><h3>Local embeddings</h3>{catalog ? <dl><dt>Model</dt><dd><code>{catalog.embedding_model}</code></dd><dt>Model revision</dt><dd><code>{catalog.embedding_revision}</code></dd><dt>Vector index</dt><dd>{catalog.vector_dimensions} dimensions · {catalog.index_algorithm}</dd></dl> : <p>Connect the local service to see the configured model and index.</p>}</section>
        <section><h3>What the timings mean</h3><p>The query embedding is shared by vector and hybrid. Method timings measure the backend’s Redis round trip. Total time includes sequential queries, embedding, and evidence processing. This is a local observation, not a production benchmark. It does not establish p95 latency, throughput under load, or index freshness.</p>{comparison && <dl><dt>Shared embedding</dt><dd>{formatTime(comparison.embedding_ms)}</dd><dt>Evidence processing</dt><dd>{formatTime(comparison.explanation_ms)}</dd><dt>Total comparison</dt><dd>{formatTime(comparison.total_ms)}</dd><dt>Candidate limit</dt><dd>{comparison.candidate_limit} passages per retrieval list</dd></dl>}</section>
      </div></details>
      <footer className="site-footer"><span>Camera Search Lab <span aria-hidden="true">·</span> Built with Redis</span><span>Explore the result. Inspect the evidence.</span></footer>
    </main>
  </>;
}

createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
