import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage, requestJSON } from "./api";
import "./traffic.css";

type TrafficRun = {
  run_id: string;
  state: "running" | "completed" | "stopped" | "failed";
  concurrency: number;
  duration: number;
  cache_embedding: boolean;
  attempts: number;
  successful: number;
  errors: number;
  timeouts: number;
  p95_success_ms: number | null;
  p95_all_ms: number | null;
  completed_per_sec: number;
  elapsed_seconds: number;
  workload: string;
  measurement: string;
  error: string | null;
};

const latency = (value: number | null) => value === null ? "—" : `${value.toFixed(1)} ms`;

export function TrafficLab() {
  const [expanded, setExpanded] = useState(false);
  const [concurrency, setConcurrency] = useState(1);
  const [duration, setDuration] = useState(10);
  const [cacheEmbedding, setCacheEmbedding] = useState(false);
  const [current, setCurrent] = useState<TrafficRun | null>(null);
  const [previous, setPrevious] = useState<TrafficRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const generation = useRef(0);
  const latestCompleted = useRef<TrafficRun | null>(null);
  const mutation = useRef(false);
  const mounted = useRef(true);
  const running = current?.state === "running";

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const accept = useCallback((run: TrafficRun | null) => {
    if (run?.state === "completed" && run.run_id !== latestCompleted.current?.run_id) {
      setPrevious(latestCompleted.current);
      latestCompleted.current = run;
    }
    setCurrent(run);
  }, []);

  useEffect(() => {
    if (!expanded && !running) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      if (!mutation.current) {
        try {
          const observedGeneration = generation.current;
          const run = await requestJSON<TrafficRun | null>("/lab/traffic", { signal: controller.signal });
          if (!stopped && !mutation.current && observedGeneration === generation.current) { accept(run); setError(""); }
        } catch (err) {
          if (!stopped) setError(errorMessage(err));
        }
      }
      if (!stopped) timer = setTimeout(poll, 1000);
    }
    void poll();
    return () => { stopped = true; controller.abort(); clearTimeout(timer); };
  }, [expanded, running, accept]);

  async function act(stop: boolean) {
    mutation.current = true;
    generation.current += 1;
    setBusy(true);
    setActionError("");
    try {
      const result = await requestJSON<TrafficRun | null>(`/lab/traffic${stop ? "/stop" : ""}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        ...(stop ? {} : { body: JSON.stringify({ concurrency, duration, cache_embedding: cacheEmbedding }) }),
      });
      if (mounted.current) accept(result);
    } catch (err) {
      if (mounted.current) setActionError(errorMessage(err));
    } finally {
      mutation.current = false;
      if (mounted.current) setBusy(false);
    }
  }

  const comparable = current?.state === "completed" && previous !== null
    && current.concurrency === previous.concurrency && current.duration === previous.duration
    && current.workload === previous.workload;

  return <details className="production-lab traffic-lab" open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}>
    <summary>Performance details {running && <span>· Running</span>}</summary>
    <div className="production-content traffic-content">
      <p>Does search stay responsive when more shoppers arrive? Run the same queries with and without embedding reuse.</p>
      <div className="traffic-controls">
        <label>Concurrent requests<select value={concurrency} disabled={running || busy} onChange={(event) => setConcurrency(Number(event.target.value))}>{[1, 5, 10, 20].map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label>Duration (seconds)<input type="number" min={5} max={30} value={duration} disabled={running || busy} onChange={(event) => setDuration(Number(event.target.value))} /></label>
        <label>Query embeddings<select value={String(cacheEmbedding)} disabled={running || busy} onChange={(event) => setCacheEmbedding(event.target.value === "true")}><option value="false">Compute each time</option><option value="true">Reuse repeated queries</option></select></label>
        <button type="button" disabled={running || busy || duration < 5 || duration > 30 || !Number.isInteger(duration)} onClick={() => void act(false)}>Start traffic</button>
        <button type="button" disabled={!running || busy} onClick={() => void act(true)}>Stop</button>
      </div>
      {error && <p role="alert">{error}</p>}
      {actionError && <p role="alert">{actionError}</p>}
      {current && <div aria-live="polite">
        <p><strong>{current.state}</strong> · {current.concurrency} concurrent · {current.duration}s requested · {current.elapsed_seconds.toFixed(1)}s elapsed</p>
        {current.error && <p role="alert">{current.error}</p>}
        {running && <p>Metrics arrive when the run finishes. In-flight requests may take up to 3 extra seconds to settle.</p>}
        {current.state === "completed" && <>
          <div className="traffic-table-wrap"><table><thead><tr><th>Measure</th><th>Current run</th>{previous && <th>Previous completed</th>}</tr></thead><tbody>
            <tr><th>Embedding cache</th><td>{current.cache_embedding ? "On" : "Off"}</td>{previous && <td>{previous.cache_embedding ? "On" : "Off"}</td>}</tr>
            <tr><th>Completed attempts / sec</th><td>{current.completed_per_sec.toFixed(2)}</td>{previous && <td>{previous.completed_per_sec.toFixed(2)}</td>}</tr>
            <tr><th>Successful / all attempts</th><td>{current.successful} / {current.attempts}</td>{previous && <td>{previous.successful} / {previous.attempts}</td>}</tr>
            <tr><th>Errors / timeouts</th><td>{current.errors} / {current.timeouts}</td>{previous && <td>{previous.errors} / {previous.timeouts}</td>}</tr>
            <tr><th>p95 successful latency</th><td>{latency(current.p95_success_ms)}</td>{previous && <td>{latency(previous.p95_success_ms)}</td>}</tr>
            <tr><th>p95 all-attempt latency</th><td>{latency(current.p95_all_ms)}</td>{previous && <td>{latency(previous.p95_all_ms)}</td>}</tr>
          </tbody></table></div>
          {previous && <p>Previous: {previous.concurrency} concurrent, {previous.duration}s. {comparable ? "Same workload and settings; compare after changing one search setting." : "Settings differ, so this is not a like-for-like comparison."}</p>}
          <p>p95 is the latency at or below which 95% of measured requests finished. Completed attempts include successes, errors, and timeouts; errors exclude timeouts. Latency includes HTTP, embedding, and search. No warm-up is excluded.</p>
        </>}
        <p className="traffic-note">{current.workload}. {current.measurement}.</p>
      </div>}
      <details><summary>How this measurement works</summary><p className="traffic-note">A separate process sends HTTP requests on this machine, sharing CPU with search. Each worker waits for its response before sending another (closed-loop). The optional cache holds up to 256 exact query vectors per process, keyed by model revision. Search results remain live. This repeated-query mix benefits from caching; unique queries still require embedding. Query mix: Sony Alpha a7; lightweight camera for travel; Canon EOS filtered to Canon; wildlife photography filtered to Nikon. Six results per request. Use this for local comparisons, not production capacity estimates.</p></details>
    </div>
  </details>;
}
