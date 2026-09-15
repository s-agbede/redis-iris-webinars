import { useEffect, useState } from "react";
import { requestJSON } from "./api";

type Props = { enabled?: boolean; value: string; onChange: (value: string) => void };

export function SearchInput({ value, onChange, enabled = true }: Props) {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [focused, setFocused] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [active, setActive] = useState(-1);
  const [status, setStatus] = useState("");
  useEffect(() => {
    setSuggestions([]);
    setActive(-1);
    setStatus("");
    const prefix = value.trim();
    if (!enabled || !focused || dismissed || prefix.length < 2 || prefix.length > 200) return;
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setStatus("Loading suggestions…");
      requestJSON<string[]>(`/suggestions?prefix=${encodeURIComponent(prefix)}`, { signal: controller.signal })
        .then((items) => { if (!controller.signal.aborted) { setSuggestions(items); setStatus(items.length ? "" : "No prefix suggestions. You can still search."); } })
        .catch(() => { if (!controller.signal.aborted) setStatus("Autocomplete unavailable. You can still search."); });
    }, 180);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [value, focused, dismissed, enabled]);
  const open = enabled && focused && !dismissed && suggestions.length > 0;
  function choose(text: string) { setDismissed(true); setSuggestions([]); onChange(text); }
  return <div className="autocomplete">
    <label className="sr-only" htmlFor="search-query">Search cameras</label>
    <span className="query-input-wrap"><input id="search-query" value={value}
      onChange={(event) => { setDismissed(false); setSuggestions([]); setActive(-1); onChange(event.target.value); }}
      onFocus={() => { setFocused(true); setDismissed(false); }} onBlur={() => setFocused(false)}
      onKeyDown={(event) => {
        if (event.key === "Escape") { setDismissed(true); return; }
        if (open && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
          event.preventDefault();
          setActive((index) => event.key === "ArrowDown" ? (index + 1) % suggestions.length : (index <= 0 ? suggestions.length - 1 : index - 1));
        }
        if (event.key === "Enter") {
          if (open && active >= 0) { event.preventDefault(); choose(suggestions[active]); }
          else setDismissed(true);
        }
      }} role="combobox" aria-autocomplete={enabled ? "list" : "none"} aria-expanded={open}
      aria-controls="query-suggestions" aria-activedescendant={open && active >= 0 ? `suggestion-${active}` : undefined}
      aria-describedby="autocomplete-help" placeholder="Search cameras…" autoComplete="off" maxLength={1000} required /></span>
    {open && <ul id="query-suggestions" role="listbox" aria-label="Catalogue suggestions" className="suggestion-list">
      {suggestions.map((text, index) => <li key={text} id={`suggestion-${index}`} role="option" aria-selected={active === index}
        onMouseDown={(event) => event.preventDefault()} onClick={() => choose(text)}>{text}</li>)}
    </ul>}
    <small id="autocomplete-help">Redis autocomplete · title and brand prefixes · all brands</small>
    <span className="sr-only" role="status">{status || (open ? `${suggestions.length} suggestions. Use arrow keys and Enter to choose.` : "")}</span>
  </div>;
}
