import { useState } from "react";
import type { Comparison, Hit, Mode, SourceLabel } from "./api";
import { rankForProduct, visibleProductUnion, type ProductRank, type VisibleCount } from "./learning";
import { ProductPhotoView } from "./ProductPhoto";

export const methods: { mode: Mode; name: string; hint: string; explanation: string }[] = [
  { mode: "text", name: "Full-text", hint: "Words in the indexed text", explanation: "Rank passages by matching query terms with BM25. Model names and exact wording can help; a word in the query is not a hard brand filter." },
  { mode: "vector", name: "Vector", hint: "Nearby meaning", explanation: "Rank passages by embedding similarity. Read the retrieved passage to decide whether it answers the need; similarity does not prove a product meets every requirement." },
  { mode: "hybrid", name: "Hybrid", hint: "Combine passage rankings", explanation: "Redis combines the full-text and vector passage rankings with reciprocal rank fusion (RRF). Each method then keeps the best passage per product." },
];

export const sourceLabels: Record<SourceLabel, string> = { E: "Exact", S: "Substitute", C: "Complement", I: "Irrelevant" };

export function formatTime(milliseconds: number): string {
  return milliseconds < 1000 ? `${milliseconds.toFixed(1)} ms` : `${(milliseconds / 1000).toFixed(2)} s`;
}

export function fieldName(field: string): string {
  const names: Record<string, string> = { product_title: "Title", product_description: "Description", product_bullet_point: "Bullet points" };
  return names[field] ?? field;
}

export function RankLabel({ rank, visibleCount, compact = false }: { rank: ProductRank; visibleCount: VisibleCount; compact?: boolean }) {
  if (rank.status === "unavailable") return <span className="rank-unavailable">{compact ? "N/A" : "Unavailable"}</span>;
  if (rank.status === "outside") return <span className="rank-outside">{compact ? ">5" : "Outside fetched top 5"}</span>;
  return <span className={rank.outsideVisible ? "rank-outside-visible" : ""}>#{rank.rank}{rank.outsideVisible && (compact ? "*" : <small>Beyond visible top {visibleCount}</small>)}</span>;
}

export function MethodIcon({ mode }: { mode: Mode }) {
  return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
    {mode === "text" ? <path d="M4 5h16M12 5v15M8 20h8M4 5v4M20 5v4" /> : mode === "vector" ? <><circle cx="6" cy="7" r="2" /><circle cx="18" cy="6" r="2" /><circle cx="14" cy="18" r="2" /><path d="m8 7 8-1M7 9l6 7M17 8l-2 8" /></> : <path d="M4 5h3c5 0 5 14 10 14h3M4 19h3C12 19 12 5 17 5h3M17 2l3 3-3 3M17 16l3 3-3 3" />}
  </svg>;
}

export function SourceJudgement({ label }: { label: SourceLabel | null }) {
  return <span className={`judgement ${label ? `judgement-${label.toLowerCase()}` : ""}`} title={label ? `Original ESCI judgement: ${sourceLabels[label]}` : "No original ESCI judgement for this query and product"}>
    <span aria-hidden="true">{label ?? "–"}</span>{label ? sourceLabels[label] : "Unjudged"}
  </span>;
}

function ProductCard({ hit, rank, selected, highlighted, onSelect, onHover }: {
  hit: Hit; rank: number; selected: boolean; highlighted: boolean;
  onSelect: (id: string) => void; onHover: (id: string | null) => void;
}) {
  return <article className={`product-card ${selected ? "is-selected" : ""} ${highlighted ? "is-highlighted" : ""}`} onMouseEnter={() => onHover(hit.product_id)} onMouseLeave={() => onHover(null)}>
    <button type="button" className="product-select" aria-pressed={selected} aria-controls="product-evidence" aria-label={`Inspect rank ${rank}: ${hit.title} across all three methods`} onClick={() => onSelect(hit.product_id)}>
      <span className="product-topline"><span className="rank">{String(rank).padStart(2, "0")}</span><span className="product-brand">{hit.brand || "Brand not supplied"}</span><span className="select-mark" aria-hidden="true">{selected ? "✓" : "↗"}</span></span>
      <h3 title={hit.title}>{hit.title}</h3>
      <span className="passage-preview">{hit.passage.text}</span>
      <span className="inspect-cue">Compare this product’s evidence <span aria-hidden="true">↗</span></span>
    </button>
    <ProductPhotoView photo={hit.photo} compact />
    {hit.source_label && <div className="product-footer"><SourceJudgement label={hit.source_label} /><span>Original ESCI judgement</span></div>}
  </article>;
}

function RankMatrix({ comparison, visibleCount, selectedId, onSelect }: { comparison: Comparison; visibleCount: VisibleCount; selectedId: string | null; onSelect: (id: string) => void }) {
  const products = visibleProductUnion(comparison, visibleCount);
  if (!products.length) return null;
  return <div className="rank-matrix">
    <table>
      <caption>Follow the same product across all three methods</caption>
      <thead><tr><th scope="col">Product</th>{methods.map((method) => <th key={method.mode} scope="col" className={`method-${method.mode}`}>{method.name}</th>)}</tr></thead>
      <tbody>{products.map((hit) => <tr key={hit.product_id} className={selectedId === hit.product_id ? "selected-row" : ""}>
        <th scope="row"><button type="button" aria-pressed={selectedId === hit.product_id} aria-controls="product-evidence" onClick={() => onSelect(hit.product_id)} title={hit.title}>{hit.title}</button></th>
        {methods.map((method) => <td key={method.mode} className={`method-${method.mode}`}><RankLabel rank={rankForProduct(comparison, method.mode, hit.product_id, visibleCount)} visibleCount={visibleCount} compact /></td>)}
      </tr>)}</tbody>
    </table>
    <p className="matrix-key">&gt;5: outside fetched top 5 · N/A: method unavailable{visibleCount === 3 && " · *: fetched, beyond visible top 3"}</p>
  </div>;
}

export function ResultColumns({ comparison, busy, selectedId, hoveredId, visibleCount, onSelect, onHover }: {
  comparison: Comparison | null; busy: boolean; selectedId: string | null; hoveredId: string | null; visibleCount: VisibleCount;
  onSelect: (id: string) => void; onHover: (id: string | null) => void;
}) {
  const [activeMode, setActiveMode] = useState<Mode>("text");
  return <>
    {comparison && <RankMatrix comparison={comparison} visibleCount={visibleCount} selectedId={selectedId} onSelect={onSelect} />}
    <div className="method-tabs" role="tablist" aria-label="Method results">
      {methods.map((method, index) => <button type="button" key={method.mode} id={`${method.mode}-tab`} role="tab" className={`method-${method.mode}`} aria-selected={activeMode === method.mode} aria-controls={`${method.mode}-panel`} tabIndex={activeMode === method.mode ? 0 : -1} onClick={() => setActiveMode(method.mode)} onKeyDown={(event) => {
        let next = index;
        if (event.key === "ArrowRight") next = (index + 1) % methods.length;
        else if (event.key === "ArrowLeft") next = (index + methods.length - 1) % methods.length;
        else if (event.key === "Home") next = 0;
        else if (event.key === "End") next = methods.length - 1;
        else return;
        event.preventDefault();
        setActiveMode(methods[next].mode);
        document.getElementById(`${methods[next].mode}-tab`)?.focus();
      }}>{method.name}</button>)}
    </div>
    <div className={`comparison-grid ${comparison ? "has-results" : ""}`}>
      {methods.map((method, methodIndex) => {
        const result = comparison?.results.find((item) => item.mode === method.mode);
        return <section id={`${method.mode}-panel`} role="tabpanel" className={`method-column method-${method.mode} ${activeMode === method.mode ? "active-method" : ""}`} key={method.mode} aria-labelledby={`${method.mode}-heading`}>
          <div className="method-heading">
            <div className="method-title"><span className="method-icon"><MethodIcon mode={method.mode} /></span><div><h2 id={`${method.mode}-heading`}>{method.name}</h2><p>{method.hint}</p></div><span className="method-index">0{methodIndex + 1}</span></div>
            <div className="method-metrics"><span>{result && !result.error ? `${Math.min(visibleCount, result.hits.length)} of ${result.hits.length} fetched` : `Top ${visibleCount} products`}</span><span>{busy ? "Running…" : result && !result.error ? `${formatTime(result.query_ms)} · Redis` : "One shared query"}</span></div>
          </div>
          {busy ? <div className="column-state loading-state"><span className="loader" aria-hidden="true" /><h3>Comparing search methods</h3><p>The query is embedded once for vector and hybrid.</p></div>
          : (result?.error || (comparison && !result)) ? <div className="column-state column-error" role="alert"><h3>{method.name} is unavailable</h3><p>{result?.error || "This method did not return a response."}</p><p>Retry the comparison after resolving the service error.</p></div>
          : result && result.hits.length > 0 ? result.hits.slice(0, visibleCount).map((hit, index) => <ProductCard key={hit.product_id} hit={hit} rank={index + 1} selected={selectedId === hit.product_id} highlighted={hoveredId === hit.product_id} onSelect={onSelect} onHover={onHover} />)
          : <div className="column-state"><span className="state-symbol" aria-hidden="true"><MethodIcon mode={method.mode} /></span><h3>{result ? "No products returned" : method.hint}</h3><p>{result ? "Try broader wording or remove the brand filter, then compare again." : method.explanation}</p>{!result && <span className="awaiting-label">Ready for your query</span>}</div>}
          <details className="method-details"><summary>How {method.name.toLowerCase()} works <span aria-hidden="true">+</span></summary><p>{method.explanation}</p></details>
        </section>;
      })}
    </div>
  </>;
}
