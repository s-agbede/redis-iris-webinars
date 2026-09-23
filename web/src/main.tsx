import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { createRequestGate, errorMessage, requestJSON, type Catalog, type Comparison, type Mode } from "./api";
import { Inspector } from "./Inspector";
import { formatTime, methods, SearchResults } from "./results";
import "./style.css";
import { SearchInput } from "./SearchInput";
import { ManageShop } from "./ManageShop";
import { SiteHeader } from "./SiteHeader";
import { SearchFilters } from "./SearchFilters";
import { Shop } from "./Shop";
import { ProductPage } from "./ProductPage";

const initialParams = new URLSearchParams(window.location.search);

const examples = [
  { label: "Sony ZV-E10", query: "sony zv e10" },
  { label: "A camera for vlogging", query: "a compact camera for filming myself" },
  { label: "Interchangeable lenses", query: "sony camera for vlogging with interchangeable lenses" },
];

function App() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [catalogError, setCatalogError] = useState("");
  const [catalogAttempt, setCatalogAttempt] = useState(0);
  const [query, setQuery] = useState(initialParams.get("q") || "");
  const [brand, setBrand] = useState("");
  const [dismissedBrandQuery, setDismissedBrandQuery] = useState<string | null>(null);
  const [queryUnderstanding, setQueryUnderstanding] = useState(true);
  const [selectedModes, setSelectedModes] = useState<Mode[]>([initialParams.has("q") ? "hybrid" : "basic"]);
  const [autocomplete, setAutocomplete] = useState(true);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [hasSearch, setHasSearch] = useState(false);
  const [error, setError] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
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

  const openedQuery = useRef(false);
  useEffect(() => {
    if (catalog && initialParams.get("q") && !openedQuery.current) {
      openedQuery.current = true;
      void compare(initialParams.get("q") || "");
    }
  }, [catalog]);

  useEffect(() => {
    const refresh = () => setCatalogAttempt(value => value + 1);
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, []);

  function invalidateComparison() {
    gate.current.cancel();
    setBusy(false);
    setComparison(null);
    setError("");
    setSelectedId(null);
  }

  async function compare(nextQuery = query, nextBrand = brand, inferBrand = queryUnderstanding && nextQuery.trim() !== dismissedBrandQuery) {
    const submittedQuery = nextQuery.trim();
    if (!submittedQuery || !catalog) return;
    const request = gate.current.begin();
    setQuery(nextQuery);
    setBrand(nextBrand);
    setBusy(true);
    setHasSearch(true);
    setError("");
    setComparison(null);
    setSelectedId(null);
    try {
      const data = await requestJSON<Comparison>("/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: submittedQuery, brands: nextBrand ? [nextBrand] : [], num_results: 5, include_basic: true, interpret_brand: inferBrand }),
        signal: request.signal,
      });
      if (request.isCurrent()) setComparison(data);
    } catch (cause: unknown) {
      if (request.isCurrent()) setError(errorMessage(cause));
    } finally {
      if (request.isCurrent()) setBusy(false);
    }
  }

  function changeFilters(nextBrand: string) {
    setBrand(nextBrand);
    if (hasSearch && query.trim()) void compare(query, nextBrand);
    else invalidateComparison();
  }

  function changeQueryUnderstanding(enabled: boolean) {
    setQueryUnderstanding(enabled);
    setDismissedBrandQuery(null);
    if (hasSearch && query.trim()) void compare(query, brand, enabled);
    else invalidateComparison();
  }

  function toggleMode(mode: Mode) {
    setSelectedModes((current) => {
      if (current.includes(mode)) {
        return current.length === 1 ? current : current.filter((item) => item !== mode);
      }
      return methods.filter((item) => current.includes(item.mode) || item.mode === mode).map((item) => item.mode);
    });
  }

  function selectProduct(id: string) {
    selectionTrigger.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setSelectedId(id);
  }

  function closeEvidence() {
    setSelectedId(null);
    selectionTrigger.current?.focus({ preventScroll: true });
  }
  return <div className="app-shell">
    <SiteHeader />

    <main className={`search-page ${hasSearch ? "has-search" : ""} ${hasSearch && selectedModes.length > 1 ? "is-comparing" : ""}`}>
      <section className="search-intro" aria-labelledby="search-heading">
        <h1 id="search-heading">Find your next camera.</h1>
        <p>A model you know. Or something you’d like to do.</p>
        <form className="search-form" role="search" onSubmit={(event) => { event.preventDefault(); void compare(); }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 5 5" /></svg>
          <SearchInput enabled={autocomplete} value={query} onChange={(value) => { invalidateComparison(); setQuery(value); }} />
          <button className="primary-button" type="submit" disabled={!catalog || !query.trim()} aria-label="Search">Search <span aria-hidden="true">→</span></button>
        </form>
        <div className="example-queries" aria-label="Example searches">
          <span>Try</span>
          {examples.map((example) => <button type="button" key={example.query} disabled={!catalog} onClick={() => void compare(example.query)}>{example.label}</button>)}
        </div>
      </section>

      {!!comparison?.inferred_brands?.length && <div className="inferred-filters" aria-label="Interpreted filters">
        <span>From your query</span>
        {comparison.inferred_brands.map(value => <button type="button" key={value} aria-label={`Remove inferred brand ${value}`} onClick={() => {
          setDismissedBrandQuery(query.trim());
          void compare(query, brand, false);
        }}>Brand: {value} <span aria-hidden="true">×</span></button>)}
      </div>}
      <details className="advanced-tray">
        <summary>Advanced{(brand) && <span className="advanced-active"> · {brand}</span>}</summary>
        <div className="advanced-content">
        <SearchFilters catalog={catalog} brand={brand} onChange={changeFilters} />
        <div className="query-understanding-option">
          <label><input type="checkbox" checked={queryUnderstanding} onChange={(event) => changeQueryUnderstanding(event.target.checked)} aria-describedby="query-understanding-help" />Query understanding</label>
          <p id="query-understanding-help">Use local rules to turn a leading brand, such as “Sony camera”, into a brand filter. Turning this off keeps manually selected filters.</p>
        </div>
        <details className="search-options">
          <summary><span>Compare methods</span>{selectedModes.length > 1 && <span className="selection-count">{selectedModes.length} selected</span>}</summary>
          <div className="options-content">
            <fieldset><legend>Choose one or more methods</legend><div className="method-choices">
              {methods.map((method) => <label key={method.mode}><input type="checkbox" checked={selectedModes.includes(method.mode)} disabled={selectedModes.length === 1 && selectedModes[0] === method.mode} onChange={() => toggleMode(method.mode)} />{method.name}</label>)}
            </div></fieldset>
            <label className="autocomplete-choice"><input type="checkbox" checked={autocomplete} onChange={(event) => setAutocomplete(event.target.checked)} />Autocomplete</label>
            <p>Autocomplete suggests what to type. The methods compare what comes back.</p>
          </div>
        </details>


        </div>
      </details>
      {catalogError && <div className="error-box" role="alert"><strong>Search is currently unavailable</strong><p>{catalogError}</p><button type="button" onClick={() => setCatalogAttempt((value) => value + 1)}>Try again</button></div>}
      {!catalog && !catalogError && <p className="connection-note" role="status">Connecting to search…</p>}
      <div className="sr-only" role="status">{busy ? `Searching for ${query}.` : comparison ? `Results ready for ${comparison.query}. Choose methods to compare their results.` : ""}</div>
      {error && <div className="error-box" role="alert"><strong>Search could not finish</strong><p>{error}</p><button type="button" onClick={() => void compare()}>Try again</button></div>}
      {(busy || comparison) && <SearchResults selectedModes={selectedModes} comparison={comparison} busy={busy} selectedId={selectedId} onSelect={selectProduct} filtered={Boolean(brand || comparison?.inferred_brands?.length)} onRetry={() => void compare()} />}
    </main>

    <footer className="site-footer">
      <details className="lab-details"><summary><span>About this search</span></summary><div className="lab-details-grid">
        <section><h3>A shared source</h3><p>Basic matches the complete query as a case-insensitive substring in original product titles, sorted alphabetically. Full-text, vector, and hybrid search original titles, descriptions, and bullet points as indexed passages, keeping the best passage per product. All four result sets are fetched together; method checkboxes change the view without rerunning the query.</p><p>This selection keeps every judged candidate for the chosen photography queries, including unrelated products. Source listings can have missing or inconsistent details.</p><p>ESCI judgements describe original query/product pairs, not new relevance assessments of your search.</p>{catalog && <dl><dt>Products / passages</dt><dd>{catalog.product_count.toLocaleString()} / {catalog.passage_count.toLocaleString()}</dd><dt>Source revision</dt><dd><code>{catalog.source_revision}</code></dd></dl>}</section>
        <section><h3>Local embeddings</h3>{catalog ? <dl><dt>Model</dt><dd><code>{catalog.embedding_model}</code></dd><dt>Model revision</dt><dd><code>{catalog.embedding_revision}</code></dd><dt>Vector index</dt><dd>{catalog.vector_dimensions} dimensions · {catalog.index_algorithm}</dd></dl> : <p>Connect the local service to see the configured model and index.</p>}</section>
        <section><h3>What the timings mean</h3><p>The query embedding is shared by vector and hybrid. Full-text, vector, and hybrid timings measure the backend’s Redis round trip. Basic includes reading the live catalogue from Redis and scanning its titles in memory. Total time includes sequential queries, embedding, and evidence processing. This is a local observation, not a production benchmark. It does not establish p95 latency, throughput under load, or index freshness.</p>{comparison && <dl><dt>Shared embedding</dt><dd>{formatTime(comparison.embedding_ms)}</dd><dt>Evidence processing</dt><dd>{formatTime(comparison.explanation_ms)}</dd><dt>Total comparison</dt><dd>{formatTime(comparison.total_ms)}</dd><dt>Candidate limit</dt><dd>{comparison.candidate_limit} passages per retrieval list</dd></dl>}</section>
      </div></details>
    </footer>
    {selectedId && comparison && <Inspector key={selectedId} selectedId={selectedId} comparison={comparison} visibleCount={5} onClose={closeEvidence} />}
  </div>;
}

const view = initialParams.get("view");
createRoot(document.getElementById("root")!).render(<React.StrictMode>{view === "manage" ? <ManageShop /> : view === "compare" || initialParams.has("q") ? <App /> : view === "product" ? <ProductPage id={initialParams.get("id") || ""} /> : <Shop />}</React.StrictMode>);
