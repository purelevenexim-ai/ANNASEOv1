import { useEffect, useState } from "react";
import { enrichKeyword, createStrategyJob, getJobStatus } from "./lib/api/strategy";

const T = {
  purple: "#7F77DD",
  purpleLight: "#EEEDFE",
  purpleDark: "#534AB7",
  teal: "#1D9E75",
  gray: "#888780",
  grayLight: "#F1EFE8",
};

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

export default function StrategyPage({ projectId, setPage }) {
  const [keyword, setKeyword] = useState("");
  const [state, setState] = useState("idle");
  const [enrichment, setEnrichment] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null);
  const [jobError, setJobError] = useState(null);

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

  const handleRun = async () => {
    if (!projectId || !keyword) return;

    try {
      setState("running");
      setJobError(null);
      const resp = await createStrategyJob(projectId, {
        pillar: keyword,
        region: "india",
        language: "english",
      });
      setJobId(resp.job_id || resp.id || null);
    } catch (e) {
      setState("error");
      setJobError(e.message || "Job creation failed");
    }
  };

  useEffect(() => {
    if (!jobId || !projectId) return;

    const interval = setInterval(async () => {
      try {
        const status = await getJobStatus(projectId, jobId);
        setJobStatus(status);

        if (status.status === "completed") {
          setState("completed");
          clearInterval(interval);
        } else if (status.status === "failed") {
          setState("error");
          setJobError(status.error || "Job failed");
          clearInterval(interval);
        } else {
          setState("running");
        }
      } catch (err) {
        setJobError(err.message || "Failed to poll job status");
        setState("error");
        clearInterval(interval);
      }
    }, 2200);

    return () => clearInterval(interval);
  }, [jobId, projectId]);

  const isRunReady = state === "ready" || state === "completed";

  const result = jobStatus?.outputs || {};
  const score = result.scores || {};

  return (
    <div style={{ padding: 20, maxWidth: 1100, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 24 }}>Strategy Workspace</h1>
        <p style={{ margin: "6px 0 0", color: T.gray }}>
          Input keywords, auto-enrich, run pipeline, and review strategy analytics.
        </p>
      </div>

      <div style={{ marginBottom: 16, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
        <Card>
          <h2 style={{ fontSize: 16, margin: "0 0 10px" }}>Input</h2>
          <input
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            placeholder="Enter main keyword"
            style={{ width: "100%", padding: 10, border: "1px solid #d5d7dc", borderRadius: 8, fontSize: 14 }}
          />
          <div style={{ marginTop: 12, display: "flex", alignItems: "center", gap: 8 }}>
            <Btn onClick={handleRun} disabled={!isRunReady || !projectId} loading={state === "running"}>
              Run Strategy
            </Btn>
            <span style={{ color: T.gray, fontSize: 12 }}>State: {state}</span>
          </div>
          {jobId && (
            <div style={{ marginTop: 8, fontSize: 12, color: "#555" }}>
              Job ID: <strong>{jobId}</strong>
            </div>
          )}
          {jobStatus && (
            <div style={{ marginTop: 8, fontSize: 12, color: T.gray }}>
              Progress: {jobStatus.progress ?? 0}% | Step: {jobStatus.current_step || "-"}
            </div>
          )}
          {jobError && <div style={{ marginTop: 8, color: "#bb2d3b", fontSize: 12 }}>{jobError}</div>}
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
                <strong>Keyword clusters:</strong>
                <ul style={{ paddingLeft: 18, margin: "4px 0" }}>
                  {(enrichment.clusters || []).slice(0, 6).map((c, i) => (
                    <li key={i} style={{ fontSize: 12 }}>{c}</li>
                  ))}
                </ul>
              </div>

              <div>
                <strong>Competitors:</strong>
                <ul style={{ paddingLeft: 18, margin: "4px 0" }}>
                  {(enrichment.competitors || []).slice(0, 8).map((c, i) => (
                    <li key={i} style={{ fontSize: 12, color: T.gray }}>{c}</li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </Card>
      </div>

      <div>
        {(state === "running" || state === "completed" || state === "error") && (
          <Card>
            <h2 style={{ fontSize: 16, margin: "0 0 14px" }}>Pipeline Results</h2>

            {state === "running" && <p style={{ color: T.gray }}>Pipeline running, polling status…</p>}
            {state === "completed" && (
              <>
                <div style={{ marginBottom: 12, display: "grid", gridTemplateColumns: "repeat(3, minmax(120px,1fr))", gap: 8 }}>
                  <Card style={{ background: "#eef8ff", borderColor: "#c6e2ff" }}>
                    <p style={{ margin: 0, fontSize: 11, color: T.gray }}>Rank Probability</p>
                    <p style={{ margin: 2, fontSize: 20, fontWeight: 700 }}>{(score.win_probability ?? 0).toFixed(2)}</p>
                  </Card>
                  <Card style={{ background: "#f2fdf4", borderColor: "#d3eed5" }}>
                    <p style={{ margin: 0, fontSize: 11, color: T.gray }}>Score</p>
                    <p style={{ margin: 2, fontSize: 20, fontWeight: 700 }}>{(score.composite_score ?? (score.win_probability ?? 0)).toFixed(2)}</p>
                  </Card>
                  <Card style={{ background: "#fff7eb", borderColor: "#fee2b1" }}>
                    <p style={{ margin: 0, fontSize: 11, color: T.gray }}>Gaps</p>
                    <p style={{ margin: 2, fontSize: 20, fontWeight: 700 }}>{(result.serp?.gaps || []).length ?? 0}</p>
                  </Card>
                </div>

                <div style={{ marginTop: 10 }}>
                  <h3 style={{ margin: "0 0 6px", fontSize: 14 }}>Raw Structured Output</h3>
                  <pre style={{ maxHeight: 260, overflowY: "auto", background: "#f8f9fb", padding: 10, borderRadius: 8 }}>
                    {JSON.stringify(result, null, 2)}
                  </pre>
                </div>
              </>
            )}

            {state === "error" && <p style={{ color: "#b02a37" }}>Pipeline error: {jobError || "Unknown"}</p>}
          </Card>
        )}
      </div>
    </div>
  );
}
