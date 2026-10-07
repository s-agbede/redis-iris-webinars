import { useEffect, useRef, useState, type RefObject } from "react";
import { ProductPhotoView } from "./ProductPhoto";
import { ModelEvidence } from "./ModelEvidence";
import { ShopInspector } from "./ShopInspector";
import { ShopSettings } from "./ShopSettings";
import { useShopConversation } from "./useShopConversation";
import type { MemoryMode, Session, Shopper, Turn } from "./shop-api";
import "./shop.css";

export function Shop() {
  const [shopper, setShopper] = useState<Shopper>("alex");
  return (
    <div className="app-shell shop-shell">
      {/* Switching shoppers remounts all conversation state and cancels restoration. */}
      <ShopConversation
        key={shopper}
        shopper={shopper}
        onShopperChange={setShopper}
      />
    </div>
  );
}

type ShopConversationProps = {
  shopper: Shopper;
  onShopperChange: (shopper: Shopper) => void;
};

function ShopConversation({ shopper, onShopperChange }: ShopConversationProps) {
  const [mode, setMode] = useState<MemoryMode>("both");
  const [useCache, setUseCache] = useState(true);
  const [inspect, setInspect] = useState(false);
  const settingsTrigger = useRef<HTMLButtonElement>(null);
  const {
    status,
    session,
    loading,
    restoreFailed,
    busy,
    setBusy,
    error,
    notice,
    message,
    setMessage,
    pending,
    revision,
    ready,
    newConversation,
    retryRestoration,
    send,
  } = useShopConversation(shopper, mode, useCache);

  return (
    <main
      className={`shop-layout ${inspect ? "with-inspector" : ""}`}
      aria-label="Camera adviser"
    >
      <h1 className="sr-only">Chat with your camera adviser</h1>
      <ShopSettings
        shopper={shopper}
        status={status}
        ready={ready}
        busy={busy}
        setBusy={setBusy}
        inspect={inspect}
        mode={mode}
        useCache={useCache}
        onNewConversation={newConversation}
        onInspectorToggle={() => setInspect((value) => !value)}
        onShopperChange={onShopperChange}
        onModeChange={setMode}
        onUseCacheChange={setUseCache}
      />
      <section className="shop-main" aria-label="Shopping conversation">
        <div className="shop-scroll">
          {loading && <p role="status">Connecting to the shop…</p>}
          {status && !ready && !loading && (
            <div className="error-box">
              <strong>Finish connecting your adviser</strong>
              <p>
                {status.missing.length
                  ? `Configure ${status.missing.join(", ")} in .env and restart.`
                  : "The catalogue is not ready. Check the backend health."}
              </p>
              <a href="/?view=compare">Open the search lab</a>
            </div>
          )}
          {error && (
            <p className="shop-error" role="alert">
              {error}
            </p>
          )}
          {notice && (
            <p className="shop-notice" role="status">
              {notice}
            </p>
          )}
          {restoreFailed && (
            <p className="shop-small">
              Your saved conversation is still available to retry.{" "}
              <button
                disabled={busy || loading}
                className="shop-secondary"
                onClick={retryRestoration}
              >
                Retry restoring conversation
              </button>
            </p>
          )}
          <ConversationLog
            shopper={shopper}
            session={session}
            pending={pending}
            busy={busy}
            restoreFailed={restoreFailed}
          />
        </div>
        <MessageComposer
          message={message}
          disabled={busy || !ready || restoreFailed}
          settingsTrigger={settingsTrigger}
          onMessageChange={setMessage}
          onSend={send}
        />
      </section>
      {inspect && ready && (
        <ShopInspector
          shopper={shopper}
          session={session}
          revision={revision}
          cacheReady={!!status?.cache_ready}
          busy={busy}
          onClose={() => {
            setInspect(false);
            settingsTrigger.current?.focus();
          }}
        />
      )}
    </main>
  );
}

function ConversationLog({
  shopper,
  session,
  pending,
  busy,
  restoreFailed,
}: {
  shopper: Shopper;
  session: Session | null;
  pending: string;
  busy: boolean;
  restoreFailed: boolean;
}) {
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (session?.turns.length || pending)
      bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [session?.turns.length, pending]);

  return (
    <div
      className="shop-conversation"
      role="log"
      aria-label="Conversation"
      aria-live="polite"
      aria-busy={busy}
    >
      {!session?.turns.length && !pending && !restoreFailed && (
        <div className="shop-welcome">
          <h2>What would you like to do today?</h2>
        </div>
      )}
      {session?.turns.map((turn, index) => (
        <ConversationTurn key={index} shopper={shopper} turn={turn} />
      ))}
      {pending && (
        <>
          <div className="shop-user">
            <span>{shopper}</span>
            <p>{pending}</p>
          </div>
          <p className="shop-thinking" role="status">
            Your adviser is gathering a little context…
          </p>
        </>
      )}
      <div ref={bottom} />
    </div>
  );
}

function MessageComposer({
  message,
  disabled,
  settingsTrigger,
  onMessageChange,
  onSend,
}: {
  message: string;
  disabled: boolean;
  settingsTrigger: RefObject<HTMLButtonElement | null>;
  onMessageChange: (message: string) => void;
  onSend: () => Promise<void>;
}) {
  return (
    <form
      className="shop-composer"
      onSubmit={(event) => {
        event.preventDefault();
        void onSend();
      }}
    >
      <label className="sr-only" htmlFor="shop-message">
        Message your camera adviser
      </label>
      <textarea
        id="shop-message"
        value={message}
        maxLength={4000}
        rows={2}
        placeholder="Type your message…"
        disabled={disabled}
        onChange={(event) => onMessageChange(event.target.value)}
        onKeyDown={(event) => {
          if (
            event.key === "Enter" &&
            !event.shiftKey &&
            !event.nativeEvent.isComposing
          ) {
            event.preventDefault();
            void onSend();
          }
        }}
      />
      <div>
        <button
          type="button"
          ref={settingsTrigger}
          className="shop-settings-trigger"
          popoverTarget="shop-settings"
          aria-label="Chat settings"
          title="Chat settings"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <circle cx="5" cy="12" r="1.7" />
            <circle cx="12" cy="12" r="1.7" />
            <circle cx="19" cy="12" r="1.7" />
          </svg>
        </button>
        <span className="shop-small">
          Check product details before buying.
        </span>
        <button
          className="primary-button"
          type="submit"
          disabled={disabled || !message.trim()}
          aria-label="Send message"
        >
          Send ↑
        </button>
      </div>
    </form>
  );
}

function ConversationTurn({ shopper, turn }: { shopper: Shopper; turn: Turn }) {
  return (
    <div className="shop-turn">
      <div className="shop-user">
        <span>{shopper}</span>
        <p>{turn.user}</p>
      </div>
      <div className="shop-assistant">
        <span className="adviser-avatar">S</span>
        <div className="assistant-content">
          <span className="eyebrow">Sam’s adviser</span>
          <p className="reply-text">{turn.assistant}</p>
          <ProductCards products={turn.products} />
          {turn.inspector.cache?.status !== "hit" && (
            <ModelEvidence request={turn.inspector.answer_request} />
          )}
        </div>
      </div>
    </div>
  );
}

function ProductCards({ products }: { products: Turn["products"] }) {
  if (!products.length) return null;
  return (
    <div className="shop-products">
      {products.map((product, index) => (
        <article className="shop-product" key={product.product_id}>
          <ProductPhotoView photo={product.photo} compact />
          <div>
            <span className="eyebrow">
              {index + 1} / {product.brand || "From our catalogue"}
            </span>
            <h3>{product.title}</h3>
            <a href={product.url} target="_blank" rel="noreferrer">
              View gear details <span aria-hidden="true">↗</span>
            </a>
          </div>
        </article>
      ))}
    </div>
  );
}
