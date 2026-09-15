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
  const gate = useRef(createRequestGate());
  const [sourceOpen, setSourceOpen] = useState(false);
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const selection = selectionAcrossModes(comparison, selectedId, visibleCount);
  const selectedProduct = selection.find((item) => item.hit)?.hit;

  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    heading.current?.scrollIntoView({ block: "start", behavior: "instant" });
  }, [selectedId]);

  useEffect(() => {
    if (!sourceOpen || product) return;
    const request = gate.current.begin();
    setError("");
    requestJSON<ProductDetail>(`/products/${encodeURIComponent(selectedId)}`, { signal: request.signal })
      .then((data) => { if (request.isCurrent()) setProduct(data); })
      .catch((cause: unknown) => { if (request.isCurrent()) setError(errorMessage(cause)); });
    return () => gate.current.cancel();
  }, [selectedId, sourceOpen, attempt, product]);

  if (!selectedProduct) return null;
  return <section id="product-evidence" className="evidence-panel" aria-labelledby="evidence-heading" onKeyDown={(event) => { if (event.key === "Escape") onClose(); }}>
    <div className="evidence-toolbar"><span className="eyebrow">02 / Follow one product</span><button type="button" className="close-button" onClick={onClose} aria-label="Close evidence and return to results">×</button></div>
    <h2 id="evidence-heading" ref={heading} tabIndex={-1}>{selectedProduct.title}</h2>
    <p className="evidence-intro">Same product, three retrieval decisions. Each method can choose a different winning passage.</p>
    <div className="evidence-ranks">{selection.map((item) => <div className={`method-${item.mode}`} key={item.mode}><span>{methods.find((method) => method.mode === item.mode)!.name}</span><strong><RankLabel rank={item.rank} visibleCount={visibleCount} /></strong></div>)}</div>
    <div className="evidence-grid">{selection.map(({ mode, hit, rank, result }) => <section className={`evidence-method method-${mode}`} key={mode} aria-labelledby={`evidence-${mode}`}>
      <div className="section-heading"><h3 id={`evidence-${mode}`}>{methods.find((method) => method.mode === mode)!.name} evidence</h3></div>
      {!hit ? <div className="evidence-missing"><strong><RankLabel rank={rank} visibleCount={visibleCount} /></strong><p>{rank.status === "unavailable" ? result?.error || "This method did not return a response." : "This product has no winning passage in this method’s fetched results. That does not establish that it cannot match."}</p></div> : <>
        <p className="evidence-label">{fieldName(hit.passage.field)} · winning passage #{hit.passage_rank}</p>
        <p className="evidence-explanation">{mode === "text" ? "Literal query-word overlap: highlights show literal word overlap, not engine-reported matches. Redis may also match stemmed forms." : mode === "vector" ? "This passage was retrieved by embedding similarity. Use its words to assess the fit; the vector score does not explain the model’s reasoning." : "This passage wins after combining the two passage rankings."}</p>
        <blockquote className="evidence-excerpt">{mode === "text" ? <IndexedText hit={hit} /> : hit.passage.text}</blockquote>
        {mode === "text" && hit.lexical_matches.length === 0 && <p className="fine-print">No literal query-word overlap is highlighted in this indexed passage.</p>}
        <details className="indexed-details"><summary>Read full indexed text</summary><p className="fine-print">The indexed text includes bounded context from title, brand, and color plus the source passage.</p><blockquote><IndexedText hit={hit} /></blockquote><p className="fine-print">Source: {fieldName(hit.passage.field)}, characters {hit.passage.start}–{hit.passage.end}. Passage ranks are before product deduplication.</p><code>{hit.passage.passage_id}</code></details>
        {mode === "hybrid" && <FusionCalculation fusion={hit.fusion} score={hit.score} />}
        <details className="score-details"><summary>Score & source judgement</summary><p><strong>{result?.score_kind}: {hit.score.toFixed(8)}</strong></p><p>{mode === "vector" ? "Cosine similarity (1 − cosine distance), not a percentage of relevance." : mode === "text" ? "BM25 score within this full-text ranking." : "Native Redis RRF score is authoritative; the arithmetic above is a checked reconstruction."} Score scales differ between methods.</p><SourceJudgement label={hit.source_label} /><p>Judgements belong to original ESCI query/product pairs. They are not new assessments of your query.</p></details>
      </>}
    </section>)}</div>
    <p className="evidence-footnote"><strong>RRF uses passage ranks before product deduplication.</strong> The product ranks at the top of this panel do not enter the formula. A missing branch contributes zero only when verified outside its RRF window.</p>
    <details className="original-source" onToggle={(event) => setSourceOpen(event.currentTarget.open)}>
      <summary>Original source record <span>ESCI · US</span></summary>
      <div className="source-section" aria-busy={!product && !error}>
        {!product && !error && <p className="inline-loading" role="status"><span className="loader" aria-hidden="true" />Loading source record…</p>}
        {error && <div className="error-box" role="alert"><p>{error}</p><button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry source record</button></div>}
        {product && <>
          <ProductPhotoView photo={product.photo} compact />
          <SourceField label="Title" value={product.product_title} />
          <dl className="source-metadata"><div><dt>Brand</dt><dd>{product.product_brand || "Not supplied"}</dd></div><div><dt>Color</dt><dd>{product.product_color || "Not supplied"}</dd></div><div><dt>Locale</dt><dd>{product.product_locale}</dd></div></dl>
          <SourceField label="Description" value={product.product_description} /><SourceField label="Bullet points" value={product.product_bullet_point} />
          <details className="raw-fields"><summary>Verbatim source fields & provenance</summary><p>HTML is displayed as text.</p><pre>{JSON.stringify({ product_id: product.product_id, product_title: product.product_title, product_description: product.product_description, product_bullet_point: product.product_bullet_point, product_brand: product.product_brand, product_color: product.product_color, product_locale: product.product_locale, source_revision: product.source_revision }, null, 2)}</pre></details>
        </>}
      </div>
    </details>
    <details className="commands-details"><summary>Redis commands for this comparison</summary><p>Query traces use the same query and brand filter. Failed methods include an attempted command when available.</p>{methods.map((method) => { const result = comparison.results.find((item) => item.mode === method.mode); return <div key={method.mode}><h4>{method.name}</h4>{result?.redis_query ? <><p>{result.error ? "Attempted command; this method returned an error." : "Executed command"}</p><pre>{result.redis_query}</pre></> : <p>Command not run. {result?.error || "No query trace is available."}</p>}</div>; })}</details>
    <button type="button" className="back-to-results" onClick={onClose}>Back to results ↑</button>
  </section>;
}
