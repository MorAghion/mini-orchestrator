import { useEffect, useState } from "react";
import { api, ReviewReport } from "../api/client";

interface Props {
  projectId: string;
  // Re-fetch when the parent signals (e.g. on review:* events)
  tick: number;
}

export function ReviewPanel({ projectId, tick }: Props) {
  const [report, setReport] = useState<ReviewReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .getReview(projectId)
      .then(setReport)
      .catch((e) => {
        // 404 = review not written yet; suppress
        if (!String(e).includes("404")) setError(String(e));
      });
  }, [projectId, tick]);

  if (error) {
    return (
      <div className="panel">
        <h3>Review</h3>
        <div style={{ color: "var(--security)" }}>{error}</div>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="panel">
        <h3>Review</h3>
        <div style={{ color: "var(--text-muted)", fontSize: 12 }}>
          Review will appear here once all waves finish.
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <h3>Review</h3>
      <div className={`verdict ${report.overall_verdict}`}>
        {report.overall_verdict === "approved" ? "✓ Approved" : "⚠ Needs rework"}
      </div>
      <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "0 0 10px" }}>
        {report.summary}
      </p>
      {report.issues.map((issue, i) => (
        <div key={i} className={`issue ${issue.severity}`}>
          <span className="severity">[{issue.severity}]</span>
          <span className="category">{issue.category}</span>
          <div className="description">{issue.description}</div>
        </div>
      ))}
    </div>
  );
}
