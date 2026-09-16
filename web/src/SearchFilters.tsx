import type { Catalog } from "./api";

export function SearchFilters({ catalog, brand, onChange }: {
  catalog: Catalog | null;
  brand: string;
  onChange: (brand: string) => void;
}) {
  const active = Boolean(brand);
  return <fieldset className="metadata-filters" disabled={!catalog}>
    <legend>Filter products</legend>
    <div className="filter-controls">
      <label><span>Brand</span><select aria-label="Filter by brand" value={brand} onChange={(event) => onChange(event.target.value)}>
        <option value="">All brands</option>
        {catalog?.brands.map((item) => <option key={item.value} value={item.value}>{item.value} ({item.count})</option>)}
      </select></label>
      {active && <button type="button" onClick={() => onChange("")}>Clear filters</button>}
    </div>
    {active && <p className="active-filters" role="status">
      {brand && <span>Brand: {brand}</span>}
    </p>}
    <p className="filter-help">Filters apply to every search method. Counts cover the whole catalogue.</p>
  </fieldset>;
}
