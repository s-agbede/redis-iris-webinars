import { useEffect, useState } from "react";
import { errorMessage, requestJSON } from "./api";
import { chatFailureMessage, shouldForgetSession } from "./shop-evidence";
import {
  shopPost,
  type MemoryMode,
  type Session,
  type Shopper,
  type ShopStatus,
  type Turn,
} from "./shop-api";

// Own the saved conversation and its requests. The screen owns display choices.
export function useShopConversation(
  shopper: Shopper,
  mode: MemoryMode,
  useCache: boolean,
) {
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
  const [revision, setRevision] = useState(0);
  const storageKey = `sams-camera-shop-session-${shopper}`;

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setError("");
      setNotice("");
      try {
        const data = await requestJSON<ShopStatus>("/shop/status", {
          signal: controller.signal,
        });
        if (controller.signal.aborted) return;
        setStatus(data);
        const saved = localStorage.getItem(storageKey);
        if (saved && data.configured && data.catalogue_ready) {
          try {
            const restored = await requestJSON<Session>(
              `/shop/sessions/${encodeURIComponent(saved)}?shopper_id=${shopper}`,
              { signal: controller.signal },
            );
            if (!controller.signal.aborted) {
              setSession(restored);
              setRestoreFailed(false);
            }
          } catch (cause) {
            if (!controller.signal.aborted) {
              // A temporary outage must not discard the saved conversation ID.
              if (shouldForgetSession(cause)) {
                localStorage.removeItem(storageKey);
                setRestoreFailed(false);
              } else setRestoreFailed(true);
              setNotice(
                `Previous conversation could not be restored: ${errorMessage(cause)}`,
              );
            }
          }
        } else if (!saved) setRestoreFailed(false);
      } catch (cause) {
        if (!controller.signal.aborted) setError(errorMessage(cause));
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [shopper, storageKey, restoreAttempt]);

  function rememberSession(value: Session) {
    setSession(value);
    localStorage.setItem(storageKey, value.session_id);
  }

  async function newConversation() {
    setBusy(true);
    setError("");
    try {
      rememberSession(
        await shopPost<Session>("sessions", { shopper_id: shopper }),
      );
      setRestoreFailed(false);
      setNotice("New conversation. Your long-term memories remain available.");
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function send(text = message) {
    if (busy || restoreFailed || !text.trim()) return;
    setBusy(true);
    setError("");
    setNotice("");
    setPending(text.trim());
    setMessage("");
    try {
      const active =
        session ??
        (await shopPost<Session>("sessions", { shopper_id: shopper }));
      // Remember a newly created session even if its first reply fails.
      if (!session) rememberSession(active);
      const turn = await shopPost<Turn>("chat", {
        shopper_id: shopper,
        session_id: active.session_id,
        message: text.trim(),
        mode,
        use_cache: useCache,
      });
      rememberSession({ ...active, turns: [...active.turns, turn] });
      setRevision((value) => value + 1);
    } catch (cause) {
      setMessage(text);
      setError(chatFailureMessage(cause));
    } finally {
      setPending("");
      setBusy(false);
    }
  }

  const ready = !!status?.configured && status.catalogue_ready && !loading;

  function retryRestoration() {
    setRestoreAttempt((value) => value + 1);
  }

  return {
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
  };
}
