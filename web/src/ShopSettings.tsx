import { useRef, useState } from "react";
import { errorMessage } from "./api";
import { cacheReadiness } from "./cache-evidence";
import { shopPost, type MemoryMode, type Shopper, type ShopStatus } from "./shop-api";

type ShopSettingsProps = {
  shopper: Shopper;
  status: ShopStatus | null;
  ready: boolean;
  busy: boolean;
  setBusy: (busy: boolean) => void;
  inspect: boolean;
  mode: MemoryMode;
  useCache: boolean;
  onNewConversation: () => Promise<void>;
  onInspectorToggle: () => void;
  onShopperChange: (shopper: Shopper) => void;
  onModeChange: (mode: MemoryMode) => void;
  onUseCacheChange: (useCache: boolean) => void;
};

export function ShopSettings({
  shopper,
  status,
  ready,
  busy,
  setBusy,
  inspect,
  mode,
  useCache,
  onNewConversation,
  onInspectorToggle,
  onShopperChange,
  onModeChange,
  onUseCacheChange,
}: ShopSettingsProps) {
  const settings = useRef<HTMLDivElement>(null);
  const [includeSharedCache, setIncludeSharedCache] = useState(false);
  const [clearingCache, setClearingCache] = useState(false);
  const [cacheNotice, setCacheNotice] = useState("");
  const [cacheError, setCacheError] = useState("");

  async function clearCache() {
    if (busy || !status?.cache_ready) return;
    // Cache changes and replies share the same guard against overlapping actions.
    setBusy(true);
    setClearingCache(true);
    setCacheNotice("");
    setCacheError("");
    try {
      const result = await shopPost<{ deleted: number }>("cache/clear", {
        shopper_id: shopper,
        include_shared: includeSharedCache,
      });
      setCacheNotice(
        `Removed ${result.deleted} cached answer${result.deleted === 1 ? "" : "s"} for ${shopper}${includeSharedCache ? " and the shared scope" : ""}.`,
      );
    } catch (cause) {
      setCacheError(errorMessage(cause));
    } finally {
      setClearingCache(false);
      setBusy(false);
    }
  }

  return (
    <div
      ref={settings}
      id="shop-settings"
      popover="auto"
      className="shop-settings"
      aria-label="Chat settings"
    >
      <h2>Chat settings</h2>
      <button
        className="shop-menu-action"
        disabled={busy || !ready}
        onClick={() => {
          settings.current?.hidePopover();
          void onNewConversation();
        }}
      >
        ＋ New conversation
      </button>
      <button
        className="shop-menu-action"
        disabled={!ready}
        aria-pressed={inspect}
        onClick={() => {
          onInspectorToggle();
          settings.current?.hidePopover();
        }}
      >
        {inspect ? "Close" : "Open"} memory &amp; cache inspector
      </button>
      <label className="shop-field">
        Demo shopper
        <select
          value={shopper}
          disabled={busy}
          onChange={(event) => {
            settings.current?.hidePopover();
            onShopperChange(event.target.value as Shopper);
          }}
        >
          <option value="alex">Alex · travel filmmaker</option>
          <option value="jordan">Jordan · separate shopper</option>
        </select>
      </label>
      <label className="shop-field">
        Memory for the next reply
        <select
          value={mode}
          disabled={busy}
          onChange={(event) => onModeChange(event.target.value as MemoryMode)}
        >
          <option value="none">No conversation memory</option>
          <option value="session">Short-term: this session only</option>
          <option value="both">Short-term + long-term</option>
        </select>
      </label>
      <p className="shop-small">
        Controls conversation memory supplied to the model. Order records and
        catalogue search remain available in every mode. Turns still save events
        for background extraction. Orders are fictional. Model:{" "}
        {status?.model ?? "…"}.
      </p>
      <div className="shop-cache-settings">
        <label className="shop-check">
          <input
            type="checkbox"
            checked={useCache}
            disabled={busy || !status?.cache_ready}
            onChange={(event) => onUseCacheChange(event.target.checked)}
          />
          Use answer cache for the next reply
        </label>
        <p className="shop-small">{cacheReadiness(status)}</p>
        <label className="shop-check">
          <input
            type="checkbox"
            checked={includeSharedCache}
            disabled={busy || !status?.cache_ready}
            onChange={(event) => setIncludeSharedCache(event.target.checked)}
          />
          Also clear shared answers for both shoppers
        </label>
        <button
          className="shop-secondary"
          disabled={busy || !status?.cache_ready}
          onClick={() => void clearCache()}
        >
          {clearingCache ? "Clearing…" : `Clear cached answers for ${shopper}`}
        </button>
        <p className="shop-small">
          Local presenter controls. Clearing cached answers keeps conversation
          history and long-term memories.
        </p>
        {cacheNotice && (
          <p className="shop-notice" role="status">{cacheNotice}</p>
        )}
        {cacheError && (
          <p className="shop-error" role="alert">{cacheError}</p>
        )}
      </div>
      <nav className="shop-settings-links" aria-label="Demo labs">
        <a href="/?view=compare">Search lab ↗</a>
        <a href="/?view=manage">Manage shop ↗</a>
      </nav>
    </div>
  );
}
