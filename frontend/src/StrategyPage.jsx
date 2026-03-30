import { useEffect, useState, useRef } from "react";
import { enrichKeyword, createStrategyJob, getJobStatus } from "./lib/api/strategy";

const T = {
  purple: "#7F77DD",
  purpleLight: "#EEEDFE",
  purpleDark: "#534AB7",
  teal: "#1D9E75",
  red: "#DC2626",
  gray: "#888780",
  grayLight: "#F1EFE8",
  amber: "#D97706",
};

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

function Btn({ children, onClick, disabled, loading, variant = "primary", style = {} }) {
  const styles = {
    primary: { background: "#4B3EB1", color: "#fff", border: "1px solid #4336A5" },
    secondary: { background: "#E6EAF5", color: "#2E3A5A", border: "1px solid #C4CAEB" },
    neutral: { background: "#F1F3F5", color: "#444", border: "1px solid #D6D9DD" },
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      style={{
        padding: "8px 14px",
        borderRadius: 8,
        cursor: disabled || loading ? "not-allowed" : "pointer",
        opacity: disabled || loading ? 0.6 : 1,
        fontWeight: 600,
        ...styles[variant],
        ...style,
      }}
    >
      {loading ? "…" : children}
    </button>
  );
}

function Card({ children, style = {} }) {
  return (
    <div
      style={{
        background: "#fff",
        border: "0.6px solid rgba(0,0,0,0.08)",
        borderRadius: 12,
        padding: 16,
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function ConsoleView({ events, progress, status }) {
  const scrollRef = useRef(null);
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [events]);

  const barColor = status === "error" ? T.red : status === "completed" ? T.teal : T.purple;

  return (
    <div style={{ marginTop: 16 }}>
      {/* Progress bar */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <div style={{ fontSize: 12, color: T.gray }}>Execution Progress</div>
          <div style={{ fontSize: 12, fontWeight: 600, color: barColor }}>{progress}%</div>
        </div>
        <div style={{ background: "#e5e7eb", height: 6, borderRadius: 3, overflow: "hidden" }}>
          <div style={{
            background: barColor,
            height: "100%",
            width: `${progress}%`,
            transition: "width 0.3s ease",
          }} />
        </div>
      </div>

      {/* Console */}
      <div style={{
        background: "#0d0d0d",
        color: "#0f0",
        fontFamily: "monospace",
        fontSize: 11,
        padding: 12,
        borderRadius: 6,
        height: 300,
        overflowY: "auto",
        lineHeight: 1.5,
        border: "1px solid #333",
      }} ref={scrollRef}>
        {events.length === 0 && <div style={{ color: "#666" }}>Waiting for pipeline to start...</div>}
        {events.map((e, i) => {
          let color = "#0f0";
          let icon = "→";
          if (e.type === "error") { color = "#f00"; icon = "✗"; }
          else if (e.type === "complete" || e.type === "success") { color = "#0f0"; icon = "✓"; }
          else if (e.type === "phase") { color = "#ffff00"; icon = "◆"; }
          else if (e.type === "status") { color = "#0f0"; icon = "•"; }

          return (
            <div key={i} style={{ marginBottom: 1, color }}>
              <span style={{ color: "#888" }}>
                {e.ts && `[${e.ts}] `}
              </span>
              <span>{icon} {e.phase || e.message || e.step || JSON.stringify(e).substring(0, 80)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function StrategyPage({ projectId, setPage }) {
  const [keyword, setKeyword] = useState("");
  const [state, setState] = useState("idle");
  const [enrichment, setEnrichment] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [events, setEvents] = useState([]);
  const [progress, setProgress] = useState(0);
  const [jobError, setJobError] = useState(null);
  const [result, setResult] = useState({});
  const esRef = useRef(null);

  useEffect(() => {
    if (!keyword) {
      setState("idle");
      setEnrichment(null);
      return;
    }

    setState("typing");
    const timeout = setTimeout(async () => {
      try {
        setState("enriching");
        const payload = await enrichKeyword(keyword);
        setEnrichment(payload);
        setState("ready");
      } catch (e) {
        setState("error");
        setEnrichment(null);
      }
    }, 500);

    return () => clearTimeout(timeout);
  }, [keyword]);

  const startSSE = (rid) => {
    if (esRef.current) esRef.current.close();
    const es = new EventSource(`${API}/api/runs/${rid}/stream`);
    esRef.current = es;
    es.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data);
        ev.ts = new Date().toLocaleTimeString();
        setEvents(prev => [...prev, ev]);
        if (ev.progress) setProgress(ev.progress);
        if (ev.type === "complete" || ev.status === "completed") {
          setState("completed");
          setProgress(100);
          if (ev.data) setResult(ev.data);
          es.close();
        } else if (ev.type === "error" || ev.status === "failed") {
          setState("error");
          setJobError(ev.message || "Pipeline failed");
          es.close();
        }
      } catch (err) {
        console.error("SSE parse error:", err);
      }
    };
    es.onerror = () => {
      setState("error");
      setJobError("Connection lost");
      es.close();
    };
  };

  const handleRun = async () => {
    if (!projectId || !keyword) return;
    try {
      setEvents([]);
      setProgress(0);
      setResult({});
      setState("running");
      setJobError(null);
      const resp = await createStrategyJob(projectId, {
        pillar: keyword,
        region: "india",
        language: "english",
      });
      const rid = resp.job_id || resp.id;
      if (!rid) {
        setState("error");
        setJobError("No job ID returned");
        return;
      }
      setJobId(rid);
      startSSE(rid);
    } catch (e) {
      setState("error");
      setJobError(e.message || "Job creation failed");
    }
  };

  const isRunReady = state === "ready" || state === "completed";
  const score = result.scores || {};

  return (
    <div style={{ padding: 20, maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 24 }}>Strategy Workspace</h1>
        <p style={{ margin: "6px 0 0", color: T.gray }}>
          Input keywords, auto-enrich, run pipeline with live console, and review analytics.
        </p>
      </div>

      <div style={{ marginBottom: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <Card>
          <h2 style={{ fontSize: 16, margin: "0 0 10px" }}>Input</h2>
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={e => e.key === "Enter" && isRunReady && handleRun()}
            placeholder="Enter main keyword"
            style={{ width: "100%", padding: 10, border: "1px solid #d5d7dc", borderRadius: 8, fontSize: 14 }}
          />
          <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 8 }}>
            <Btn onClick={handleRun} disabled={!isRunReady || !projectId} loading={state === "running"}>
              Run Strategy
            </Btn>
            <span style={{ color: T.gray, fontSize: 12 }}>
              {state === "idle" && "Ready"}
              {state === "typing" && "Typing…"}
              {state === "enriching" && "Enriching…"}
              {state === "ready" && "Ready to run"}
              {state === "running" && "Running…"}
              {state === "completed" && "✓ Completed"}
              {state === "error" && "✗ Error"}
            </span>
          </div>
          {jobError && <div style={{ marginTop: 8, color: T.red, fontSize: 12 }}>⚠ {jobError}</div>}
        </Card>

        <Card>
          <h2 style={{ fontSize: 16, margin: "0 0 10px" }}>Intelligence</h2>
          {state === "enriching" && <p style={{ color: T.gray }}>Analyzing SERP and competitors…</p>}
          {!enrichment && state !== "enriching" && <p style={{ color: T.gray }}>Enter keyword above to enrich.</p>}

          {enrichment && (
            <>
              <div style={{ marginBottom: 10 }}>
                <strong>Win Probability:</strong> {(enrichment.win_probability ?? 0).toFixed(2)}
              </div>
              <div style={{ marginBottom: 10 }}>
                <strong>Clusters:</strong>
                <ul style={{ paddingLeft: 18, margin: "4px 0", fontSize: 12 }}>
                  {(enrichment.clusters || []).slice(0, 5).map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </div>
              <div>
                <strong>Top Competitors:</strong>
                <ul style={{ paddingLeft: 18, margin: "4px 0", fontSize: 12, color: T.gray }}>
                  {(enrichment.competitors || []).slice(0, 5).map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </Card>
      </div>

      {/* Live Console & Results */}
      {(state === "running" || state === "completed" || state === "error") && (
        <Card>
          <h2 style={{ fontSize: 16, margin: "0 0 14px" }}>Pipeline Execution</h2>
          <ConsoleView events={events} progress={progress} status={state} />

          {state === "completed" && (
            <>
              <div style={{ marginTop: 20, display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 10 }}>
                <Card style={{ background: "#eef8ff", borderColor: "#c6e2ff" }}>
                  <p style={{ margin: 0, fontSize: 11, color: T.gray }}>Rank Probability</p>
                  <p style={{ margin: "6px 0 0", fontSize: 20, fontWeight: 700 }}>{(score.win_probability ?? 0).toFixed(2)}</p>
                </Card>
                <Card style={{ background: "#f2fdf4", borderColor: "#d3eed5" }}>
                  <p style={{ margin: 0, fontSize: 11, color: T.gray }}>Strategy Score</p>
                  <p style={{ margin: "6px 0 0", fontSize: 20, fontWeight: 700 }}>{(score.composite_score ?? 0).toFixed(2)}</p>
                </Card>
                <Card style={{ background: "#fff7eb", borderColor: "#fee2b1" }}>
                  <p style={{ margin: 0, fontSize: 11, color: T.gray }}>SERP Gaps</p>
                  <p style={{ margin: "6px 0 0", fontSize: 20, fontWeight: 700 }}>{(result.serp?.gaps || []).length ?? 0}</p>
                </Card>
              </div>
              <div style={{ marginTop: 14 }}>
                <h3 style={{ margin: "0 0 8px", fontSize: 13 }}>Full Results</h3>
                <pre style={{
                  maxHeight: 250, overflowY: "auto", background: "#f8f9fb", padding: 10, borderRadius: 6, fontSize: 11,
                }}>
                  {JSON.stringify(result, null, 2)}
                </pre>
              </div>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
