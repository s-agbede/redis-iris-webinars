import { useEffect, useRef, useState } from "react";
import { createRequestGate, errorMessage, requestJSON, type Comparison, type FusionEvidence, type Hit, type ProductDetail } from "./api";
import { highlightSegments, selectionAcrossModes, type VisibleCount } from "./learning";
import { fieldName, methods, RankLabel, SourceJudgement } from "./results";
import { ProductPhotoView } from "./ProductPhoto";

function plainSource(value: string): string {
  const document = new DOMParser().parseFromString(value, "text/html");
  document.querySelectorAll("script, style").forEach((element) => element.remove());
  document.querySelectorAll("br").forEach((element) => element.replaceWith("\n"));
  document.querySelectorAll("p, div, li").forEach((element) => element.append("\n"));
  return document.body.textContent?.trim() || value;
}

function SourceField({ label, value }: { label: string; value: string | null }) {
  return <div className="source-field"><h4>{label}</h4><p>{value ? plainSource(value) : <span className="not-supplied">Not supplied in the dataset</span>}</p></div>;
}

function IndexedText({ hit }: { hit: Hit }) {
  return <>{highlightSegments(hit.indexed_text, hit.lexical_matches).map((segment, index) => segment.matched ? <mark key={index}>{segment.text}</mark> : <span key={index}>{segment.text}</span>)}</>;
}

function FusionCalculation({ fusion, score }: { fusion: FusionEvidence | null; score: number }) {
  const verified = fusion?.status === "verified" && fusion.text_contribution !== null && fusion.vector_contribution !== null && fusion.reconstructed_score !== null;
  if (!fusion || !verified) return <div className="fusion-calculation"><strong>RRF details unavailable</strong><p>{fusion?.note || "This response does not include verified passage-rank contributions."}</p><p>Native Redis RRF score: <code>{score.toFixed(8)}</code>.</p></div>;
  const textTerm = fusion.text_rank === null ? "0" : `1 / (${fusion.constant} + ${fusion.text_rank})`;
  const vectorTerm = fusion.vector_rank === null ? "0" : `1 / (${fusion.constant} + ${fusion.vector_rank})`;
  return <div className="fusion-calculation">
    <strong className="verified-label">Verified reconstruction</strong>
    <dl className="fusion-contributions">
      <div><dt>Full-text passage rank</dt><dd>{fusion.text_rank === null ? `Outside window of ${fusion.window}` : `#${fusion.text_rank}`}</dd></div>
      <div><dt>Full-text contribution</dt><dd><code>{textTerm} ≈ {fusion.text_contribution!.toFixed(8)}</code></dd></div>
      <div><dt>Vector passage rank</dt><dd>{fusion.vector_rank === null ? `Outside window of ${fusion.window}` : `#${fusion.vector_rank}`}</dd></div>
      <div><dt>Vector contribution</dt><dd><code>{vectorTerm} ≈ {fusion.vector_contribution!.toFixed(8)}</code></dd></div>
    </dl>
    <p className="fusion-formula"><code>{textTerm} + {vectorTerm}<br />≈ {fusion.reconstructed_score!.toFixed(8)}</code></p>
    <p>Native Redis RRF score: <code>{score.toFixed(8)}</code>. Constant {fusion.constant}; window {fusion.window} passages per list.</p>
    <p>{fusion.note}</p>
  </div>;
}

export function Inspector({ selectedId, comparison, visibleCount, onClose }: {
  selectedId: string; comparison: Comparison; visibleCount: VisibleCount; onClose: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const gate = useRef(createRequestGate());
  const [sourceOpen, setSourceOpen] = useState(false);
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const selection = selectionAcrossModes(comparison, selectedId, visibleCount);
  const selectedProduct = selection.find((item) => item.hit)?.hit;

  useEffect(() => {
    const element = dialog.current;
    if (!element) return;
    const previousOverflow = document.body.style.overflow;
    element.showModal();
    document.body.style.overflow = "hidden";
    heading.current?.focus({ preventScroll: true });
    return () => {
      element.close();
      document.body.style.overflow = previousOverflow;
    };
  }, [selectedId]);

  useEffect(() => {
    if (product) return;
    const request = gate.current.begin();
    setError("");
    requestJSON<ProductDetail>(`/products/${encodeURIComponent(selectedId)}`, { signal: request.signal })
      .then((data) => { if (request.isCurrent()) setProduct(data); })
      .catch((cause: unknown) => { if (request.isCurrent()) setError(errorMessage(cause)); });
    return () => gate.current.cancel();
  }, [selectedId, sourceOpen, attempt, product]);

  function dismiss() {
    dialog.current?.close();
    onClose();
  }

  if (!selectedProduct) return null;
  return <dialog ref={dialog} id="product-evidence" className="evidence-panel" aria-labelledby="evidence-heading" onCancel={(event) => { event.preventDefault(); dismiss(); }} onClick={(event) => {
    if (event.target !== event.currentTarget) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dismiss();
  }}>
    <div className="evidence-toolbar"><span className="eyebrow">A closer look</span><button type="button" className="close-button" onClick={dismiss} aria-label="Close evidence and return to results">×</button></div>
    {error && <p role="alert" className="error-box">Live catalogue check: {error}</p>}
    <h2 id="evidence-heading" ref={heading} tabIndex={-1}>{selectedProduct.title}</h2>
    <p className="evidence-intro">See where this product appears, and what each search method found.</p>
    {selectedProduct.photo && <ProductPhotoView photo={selectedProduct.photo} compact />}
    <div className="evidence-ranks">{selection.map((item) => <div className={`method-${item.mode}`} key={item.mode}><span>{methods.find((method) => method.mode === item.mode)!.name}</span><strong><RankLabel rank={item.rank} visibleCount={visibleCount} /></strong></div>)}</div>
    <div className="evidence-grid">{selection.map(({ mode, hit, rank, result }) => <details className={`evidence-method method-${mode}`} key={mode}>
      <summary>{methods.find((method) => method.mode === mode)!.name} evidence</summary>
      {!hit ? <div className="evidence-missing"><strong><RankLabel rank={rank} visibleCount={visibleCount} /></strong><p>{rank.status === "unavailable" ? result?.error || "This method did not return a response." : "This product has no winning passage in this method’s fetched results. That does not establish that it cannot match."}</p></div> : <>
        <p className="evidence-label">{fieldName(hit.passage.field)}{mode === "basic" ? " · literal match" : ` · winning passage #${hit.passage_rank}`}</p>
        <p className="evidence-explanation">{mode === "basic" ? "The complete query appears in this title, ignoring case. Results are in alphabetical order, not relevance order. This baseline scans the loaded catalogue without a Redis search command." : mode === "text" ? "Literal query-word overlap: highlights show literal word overlap, not engine-reported matches. Redis may also match stemmed forms." : mode === "vector" ? "This passage was retrieved by embedding similarity. Use its words to assess the fit; the vector score does not explain the model’s reasoning." : "This passage wins after combining the two passage rankings."}</p>
        <blockquote className="evidence-excerpt">{mode === "text" ? <IndexedText hit={hit} /> : hit.passage.text}</blockquote>
        {mode === "text" && hit.lexical_matches.length === 0 && <p className="fine-print">No literal query-word overlap is highlighted in this indexed passage.</p>}
        {mode !== "basic" && <details className="indexed-details"><summary>Read full indexed text</summary><p className="fine-print">The indexed text includes bounded context from title, brand, and color plus the source passage.</p><blockquote><IndexedText hit={hit} /></blockquote><p className="fine-print">Source: {fieldName(hit.passage.field)}, characters {hit.passage.start}–{hit.passage.end}. Passage ranks are before product deduplication.</p><code>{hit.passage.passage_id}</code></details>}
        {mode === "hybrid" && <details className="score-details"><summary>How the hybrid score is calculated</summary><FusionCalculation fusion={hit.fusion} score={hit.score} /><p className="fine-print">RRF uses passage ranks before product deduplication. The product ranks above do not enter the formula. A missing branch contributes zero only when verified outside its RRF window.</p></details>}
        {mode !== "basic" && <details className="score-details"><summary>Score & source judgement</summary><p><strong>{result?.score_kind}: {hit.score.toFixed(8)}</strong></p><p>{mode === "vector" ? "Cosine similarity (1 − cosine distance), not a percentage of relevance." : mode === "text" ? "BM25 score within this full-text ranking." : "Native Redis RRF score is authoritative; the arithmetic above is a checked reconstruction."} Score scales differ between methods.</p><SourceJudgement label={hit.source_label} /><p>Judgements belong to original ESCI query/product pairs. They are not new assessments of your query.</p></details>}
      </>}
    </details>)}</div>
    <details className="original-source" onToggle={(event) => setSourceOpen(event.currentTarget.open)}>
      <summary>Original source record {product && <span>{product.source_origin === "demo" ? "Demo catalogue" : "ESCI · US"}</span>}</summary>
      <div className="source-section" aria-busy={!product && !error}>
        {!product && !error && <p className="inline-loading" role="status"><span className="loader" aria-hidden="true" />Loading source record…</p>}
        {error && <div className="error-box" role="alert"><p>{error}</p><button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry source record</button></div>}
        {product && <>
          <ProductPhotoView photo={product.photo} compact />
          <SourceField label="Title" value={product.product_title} />
          <dl className="source-metadata"><div><dt>Brand</dt><dd>{product.product_brand || "Not supplied"}</dd></div><div><dt>Color</dt><dd>{product.product_color || "Not supplied"}</dd></div><div><dt>Locale</dt><dd>{product.product_locale}</dd></div></dl>
          <SourceField label="Description" value={product.product_description} /><SourceField label="Bullet points" value={product.product_bullet_point} />
          <details className="raw-fields"><summary>Verbatim source fields & provenance</summary><p>HTML is displayed as text.</p><pre>{JSON.stringify({ product_id: product.product_id, product_title: product.product_title, product_description: product.product_description, product_bullet_point: product.product_bullet_point, product_brand: product.product_brand, product_color: product.product_color, product_locale: product.product_locale, source_origin: product.source_origin, source_revision: product.source_revision }, null, 2)}</pre></details>
        </>}
      </div>
    </details>
    <details className="commands-details"><summary>Redis commands for this comparison</summary><p>Query traces use the same query, brand and color filters. Filters restrict eligible products before ranking. Failed methods include an attempted command when available.</p>{methods.map((method) => { const result = comparison.results.find((item) => item.mode === method.mode); return <div key={method.mode}><h4>{method.name}</h4>{method.mode === "basic" ? <p>Reads the live catalogue from Redis, then matches titles in memory and sorts alphabetically. No Redis search index is used.</p> : result?.redis_query ? <><p>{result.error ? "Attempted command; this method returned an error." : "Executed command"}</p><pre>{result.redis_query}</pre></> : <p>Command not run. {result?.error || "No query trace is available."}</p>}</div>; })}</details>
    <button type="button" className="back-to-results" onClick={dismiss}>Back to results</button>
  </dialog>;
}
