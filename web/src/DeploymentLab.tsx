import { useEffect, useState } from "react";
import { errorMessage, requestJSON } from "./api";
import "./production.css";

type Deployment = {
  stage: string; active_index: string; candidate_index: string | null; previous_index: string | null;
  completed: number; total: number; error: string | null;
  validation: { name: string; passed: boolean; detail: string }[];
};

export function DeploymentLab() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Deployment | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!open || busy) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await requestJSON<Deployment>("/lab/deployment", {signal: controller.signal});
        if (!controller.signal.aborted) setStatus(result);
      } catch (cause) { if (!controller.signal.aborted) setError(errorMessage(cause)); }
      if (!controller.signal.aborted) timer = setTimeout(() => void poll(), 1000);
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [open, busy]);
  async function action(name: string) {
    setBusy(true); setError("");
    try { setStatus(await requestJSON<Deployment>(`/lab/deployment/${name}`, {method: "POST"})); }
    catch (cause) { setError(errorMessage(cause)); }
    finally { setBusy(false); }
  }
  const working = busy || status?.stage === "building";
  return <details className="production-lab" onToggle={e => setOpen(e.currentTarget.open)}>
    <summary><span>Safe deployment</span><span className="production-help">Build → validate → switch</span></summary>
    <div className="production-content deployment-content">
      <p>Build a replacement index while the shop keeps searching. This demo keeps the same embedding model and reuses unchanged vectors. Each index has its own passage records.</p>
      {error && <p role="alert" className="error-box">{error}</p>}
      {status?.error && <p role="alert" className="error-box">{status.error}</p>}
      {status && <>
        <p role="status"><strong>{status.stage}</strong> · {status.completed.toLocaleString()} / {status.total.toLocaleString()} products processed</p>
        {status.stage === "building" && <progress value={status.completed} max={Math.max(status.total, 1)} aria-label="Replacement index build" />}
        <dl><dt>Serving</dt><dd><code>{status.active_index}</code></dd><dt>Replacement</dt><dd><code>{status.candidate_index || "None"}</code></dd><dt>Rollback</dt><dd><code>{status.previous_index || "None"}</code></dd></dl>
        <div className="production-actions">
          <button type="button" disabled={working || !!status.candidate_index || !!status.previous_index} onClick={() => void action("build")}>Build replacement</button>
          <button type="button" disabled={working || !status.candidate_index || status.stage === "failed"} onClick={() => void action("validate")}>Validate replacement</button>
          <button type="button" disabled={working || status.stage !== "validated"} onClick={() => void action("switch")}>Switch index</button>
          <button type="button" disabled={working || !status.previous_index} onClick={() => void action("rollback")}>Roll back</button>
          <button type="button" disabled={working || (!status.candidate_index && !status.previous_index)} onClick={() => void action("reset")}>Clean up alternate</button>
        </div>
        {status.validation.length > 0 && <details><summary>{status.validation.filter(check => check.passed).length} / {status.validation.length} validation checks passed</summary><ul>{status.validation.map(check => <li key={check.name}><strong>{check.passed ? "Pass" : "Fail"}: {check.name}</strong> — {check.detail}</li>)}</ul></details>}
        <p>Switching requires successful validation and a synchronized catalogue. Both retained indexes receive changes for rollback. Cleanup removes the alternate version; it does not erase the catalogue.</p>
      </>}
    </div>
  </details>;
}
