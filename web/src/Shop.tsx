import { useEffect, useRef, useState } from "react";
import { errorMessage, requestJSON } from "./api";
import { ProductPhotoView } from "./ProductPhoto";
import { ModelEvidence } from "./ModelEvidence";
import { ShopInspector } from "./ShopInspector";
import { shouldForgetSession } from "./shop-evidence";
import { shopPost, type MemoryMode, type Session, type Shopper, type ShopStatus, type Turn } from "./shop-api";
import "./shop.css";

const prompts = ["Help me build a lightweight filming kit", "What did I buy here before?", "What do you remember about my camera?"];
export function Shop() {
  const [shopper, setShopper] = useState<Shopper>("alex");
  return <div className="app-shell shop-shell">
    <ShopConversation key={shopper} shopper={shopper} onShopperChange={setShopper} />
  </div>;
}

function ShopConversation({ shopper, onShopperChange }: { shopper: Shopper; onShopperChange: (shopper: Shopper) => void }) {
  const [status, setStatus] = useState<ShopStatus | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [restoreFailed, setRestoreFailed] = useState(false);
  const [restoreAttempt, setRestoreAttempt] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState("");
  const [mode, setMode] = useState<MemoryMode>("both");
  const [inspect, setInspect] = useState(false);
  const [revision, setRevision] = useState(0);
  const bottom = useRef<HTMLDivElement>(null);
  const settings = useRef<HTMLDivElement>(null);
  const settingsTrigger = useRef<HTMLButtonElement>(null);
  const storageKey = `sams-camera-shop-session-${shopper}`;
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true); setError(""); setRestoreFailed(false);
      try {
        const data = await requestJSON<ShopStatus>("/shop/status", { signal: controller.signal });
        if (controller.signal.aborted) return;
        setStatus(data);
        const saved = localStorage.getItem(storageKey);
        if (saved && data.configured && data.catalogue_ready) {
          try {
            const restored = await requestJSON<Session>(`/shop/sessions/${encodeURIComponent(saved)}?shopper_id=${shopper}`, { signal: controller.signal });
            if (!controller.signal.aborted) setSession(restored);
          } catch (cause) {
            if (!controller.signal.aborted) {
              if (shouldForgetSession(cause)) localStorage.removeItem(storageKey);
              else setRestoreFailed(true);
              setNotice(`Previous conversation could not be restored: ${errorMessage(cause)}`);
            }
          }
        }
      } catch (cause) { if (!controller.signal.aborted) setError(errorMessage(cause)); }
      finally { if (!controller.signal.aborted) setLoading(false); }
    }
    void load();
    return () => controller.abort();
  }, [shopper, storageKey, restoreAttempt]);
  useEffect(() => { if (session?.turns.length || pending) bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }); }, [session?.turns.length, pending]);
  function activity(value: boolean) { setBusy(value); }
  function rememberSession(value: Session) { setSession(value); localStorage.setItem(storageKey, value.session_id); }
  async function newConversation() {
    settings.current?.hidePopover();
    activity(true); setError("");
    try { rememberSession(await shopPost<Session>("sessions", { shopper_id: shopper })); setRestoreFailed(false); setNotice("New conversation. Your long-term memories remain available."); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { activity(false); }
  }
  async function send(text = message) {
    if (busy || restoreFailed || !text.trim()) return;
    activity(true); setError(""); setNotice(""); setPending(text.trim());
    try {
      const active = session ?? await shopPost<Session>("sessions", { shopper_id: shopper });
      if (!session) rememberSession(active);
      const turn = await shopPost<Turn>("chat", { shopper_id: shopper, session_id: active.session_id, message: text.trim(), mode });
      rememberSession({ ...active, turns: [...active.turns, turn] });
      setMessage(""); setRevision(value => value + 1);
    } catch (cause) { setError(`${errorMessage(cause)} A failed request may have saved session events; inspect before resending.`); }
    finally { setPending(""); activity(false); }
  }
  const ready = !!status?.configured && status.catalogue_ready && !loading;
  return <main className={`shop-layout ${inspect ? "with-inspector" : ""}`} aria-label="Camera adviser">
    <h1 className="sr-only">Chat with your camera adviser</h1>
    <div ref={settings} id="shop-settings" popover="auto" className="shop-settings" aria-label="Chat settings">
      <h2>Chat settings</h2>
      <button className="shop-menu-action" disabled={busy || !ready} onClick={() => void newConversation()}>＋ New conversation</button>
      <button className="shop-menu-action" disabled={!ready} aria-pressed={inspect} onClick={() => { setInspect(value => !value); settings.current?.hidePopover(); }}>{inspect ? "Close" : "Open"} memory inspector</button>
      <label className="shop-field">Demo shopper<select value={shopper} disabled={busy} onChange={event => { settings.current?.hidePopover(); onShopperChange(event.target.value as Shopper); }}><option value="alex">Alex · travel filmmaker</option><option value="jordan">Jordan · separate shopper</option></select></label>
      <label className="shop-field">Memory for the next reply<select value={mode} disabled={busy} onChange={event => setMode(event.target.value as MemoryMode)}><option value="none">No conversation memory</option><option value="session">Short-term: this session only</option><option value="both">Short-term + long-term</option></select></label>
      <p className="shop-small">Controls context supplied to the model. Turns still save events for background extraction. Orders are fictional. Model: {status?.model ?? "…"}.</p>
      <nav className="shop-settings-links" aria-label="Demo labs"><a href="/?view=compare">Search lab ↗</a><a href="/?view=manage">Manage shop ↗</a></nav>
    </div>
    <section className="shop-main" aria-label="Shopping conversation">
      <div className="shop-scroll">
      {loading && <p role="status">Connecting to the shop…</p>}
      {status && !ready && !loading && <div className="error-box"><strong>Finish connecting your adviser</strong><p>{status.missing.length ? `Configure ${status.missing.join(", ")} in .env and restart.` : "The catalogue is not ready. Check the backend health."}</p><a href="/?view=compare">Open the search lab</a></div>}
      {error && <p className="shop-error" role="alert">{error}</p>}
      {notice && <p className="shop-notice" role="status">{notice}</p>}
      {restoreFailed && <p className="shop-small">Your saved conversation is still available to retry. <button disabled={busy || loading} className="shop-secondary" onClick={() => setRestoreAttempt(value => value + 1)}>Retry restoring conversation</button></p>}
      <div className="shop-conversation" role="log" aria-label="Conversation" aria-live="polite" aria-busy={busy}>
        {!session?.turns.length && !pending && !restoreFailed && <div className="shop-welcome"><span className="adviser-avatar">S</span><div><h2>A little advice goes a long way.</h2><p>Tell me what you’d like to create. We’ll find the gear to help you get there.</p><div className="shop-prompts">{prompts.map(prompt => <button key={prompt} disabled={busy || !ready} onClick={() => void send(prompt)}>{prompt}<span>↗</span></button>)}</div></div></div>}
        {session?.turns.map((turn, index) => <div className="shop-turn" key={index}>
          <div className="shop-user"><span>{shopper}</span><p>{turn.user}</p></div>
          <div className="shop-assistant"><span className="adviser-avatar">S</span><div className="assistant-content"><span className="eyebrow">Sam’s adviser</span><p className="reply-text">{turn.assistant}</p>
            {!!turn.products.length && <div className="shop-products">{turn.products.map((product, cardIndex) => <article className="shop-product" key={product.product_id}><ProductPhotoView photo={product.photo} compact /><div><span className="eyebrow">{cardIndex + 1} / {product.brand || "From our catalogue"}</span><h3>{product.title}</h3><a href={product.url} target="_blank" rel="noreferrer">View gear details <span aria-hidden="true">↗</span></a></div></article>)}</div>}
            <ModelEvidence request={turn.inspector.answer_request} />
          </div></div>
        </div>)}
        {pending && <><div className="shop-user"><span>{shopper}</span><p>{pending}</p></div><p className="shop-thinking" role="status">Your adviser is gathering a little context…</p></>}
        <div ref={bottom} />
      </div>
      </div>
      <form className="shop-composer" onSubmit={event => { event.preventDefault(); void send(); }}>
        <label className="sr-only" htmlFor="shop-message">Message your camera adviser</label><textarea id="shop-message" value={message} maxLength={4000} rows={2} placeholder="What would you love to film?" disabled={busy || !ready || restoreFailed} onChange={event => setMessage(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(); } }} />
        <div><button type="button" ref={settingsTrigger} className="shop-settings-trigger" popoverTarget="shop-settings" aria-label="Chat settings" title="Chat settings"><svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.7" /><circle cx="12" cy="12" r="1.7" /><circle cx="19" cy="12" r="1.7" /></svg></button><span className="shop-small">Check product details before buying.</span><button className="primary-button" type="submit" disabled={busy || !ready || restoreFailed || !message.trim()} aria-label="Send message">Send ↑</button></div>
      </form>
    </section>
    {inspect && ready && <ShopInspector shopper={shopper} session={session} revision={revision} onClose={() => { setInspect(false); settingsTrigger.current?.focus(); }} />}
  </main>;
}
