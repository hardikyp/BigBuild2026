/**
 * Default UI: a camera button, a preview, and the interpretation.
 *
 *   <PhotoCapture
 *     context={{ buildingType: "W1", performanceLevel: "CP", checklistItem }}
 *     onCaptured={savePhoto}
 *     onInterpreted={(photo, result) => attachToItem(item.id, photo, result)}
 *   />
 *
 * Styling: every element has an `fc-` class; there are minimal inline styles
 * only for layout. Override with your own CSS.
 */
import { useRef } from "react";
import type { ChecklistStatus, PhotoInterpretation } from "../types";
import { usePhotoInterpretation, type UsePhotoInterpretationOptions } from "./usePhotoInterpretation";

export interface PhotoCaptureProps extends UsePhotoInterpretationOptions {
  /** Called when the user accepts the suggested checklist status. */
  onAcceptStatus?: (status: ChecklistStatus) => void;
  label?: string;
  className?: string;
}

const STATUS_LABEL: Record<ChecklistStatus, string> = {
  C: "Compliant",
  NC: "Noncompliant",
  "N/A": "Not applicable",
  U: "Unknown",
};

export function PhotoCapture({ onAcceptStatus, label = "Take photo", className, ...options }: PhotoCaptureProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const { status, previewUrl, result, error, capture, interpret, reset } = usePhotoInterpretation(options);
  const busy = status === "preparing" || status === "interpreting";

  return (
    <div className={`fc-root ${className ?? ""}`} style={{ display: "grid", gap: 12 }}>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = ""; // allow re-selecting the same file
          if (file) void capture(file);
        }}
      />

      <div className="fc-actions" style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" className="fc-btn fc-btn-primary" disabled={busy} onClick={() => inputRef.current?.click()}>
          {previewUrl ? "Retake" : label}
        </button>
        {previewUrl && status === "error" && (
          <button type="button" className="fc-btn" onClick={() => void interpret()}>
            Retry interpretation
          </button>
        )}
        {previewUrl && !busy && (
          <button type="button" className="fc-btn" onClick={reset}>
            Clear
          </button>
        )}
      </div>

      {previewUrl && (
        <img
          className="fc-preview"
          src={previewUrl}
          alt="Captured site photo"
          style={{ maxWidth: "100%", maxHeight: 360, objectFit: "contain", borderRadius: 8 }}
        />
      )}

      {status === "preparing" && <p className="fc-status">Preparing photo…</p>}
      {status === "interpreting" && <p className="fc-status">Interpreting photo…</p>}
      {error && (
        <p className="fc-error" role="alert">
          {error.message}
        </p>
      )}

      {result && <InterpretationView result={result} onAcceptStatus={onAcceptStatus} />}
    </div>
  );
}

export function InterpretationView({
  result,
  onAcceptStatus,
}: {
  result: PhotoInterpretation;
  onAcceptStatus?: (status: ChecklistStatus) => void;
}) {
  return (
    <section className="fc-result" style={{ display: "grid", gap: 8 }}>
      <p className="fc-summary">{result.summary}</p>

      {!result.imageQuality.usable && (
        <p className="fc-warning" role="alert">
          Photo may not be usable: {result.imageQuality.issues.join("; ")}
        </p>
      )}

      {result.suggestedStatus && (
        <div className="fc-suggested-status">
          <strong>
            Suggested: {result.suggestedStatus} ({STATUS_LABEL[result.suggestedStatus]})
          </strong>
          {result.statusRationale && <p>{result.statusRationale}</p>}
          {onAcceptStatus && (
            <button type="button" className="fc-btn" onClick={() => onAcceptStatus(result.suggestedStatus!)}>
              Use this status
            </button>
          )}
          <p className="fc-disclaimer" style={{ fontSize: "0.85em", opacity: 0.75 }}>
            AI suggestion. Confirm on site before recording.
          </p>
        </div>
      )}

      {result.observations.length > 0 && (
        <details open className="fc-observations">
          <summary>Observations ({result.observations.length})</summary>
          <ul>
            {result.observations.map((o, i) => (
              <li key={i} data-severity={o.severity}>
                <span className="fc-severity">[{o.severity}]</span> {o.description}
              </li>
            ))}
          </ul>
        </details>
      )}

      {result.possibleDeficiencies.length > 0 && (
        <details open className="fc-deficiencies">
          <summary>Possible deficiencies ({result.possibleDeficiencies.length})</summary>
          <ul>
            {result.possibleDeficiencies.map((d, i) => (
              <li key={i}>
                {d.description} <em>({d.confidence} confidence)</em>
              </li>
            ))}
          </ul>
        </details>
      )}

      {result.components.length > 0 && (
        <details className="fc-components">
          <summary>Components ({result.components.length})</summary>
          <ul>
            {result.components.map((c, i) => (
              <li key={i}>
                {c.name}
                {c.material ? `, ${c.material}` : ""}
                {c.condition ? `: ${c.condition}` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}

      {result.followUp.length > 0 && (
        <details open className="fc-followup">
          <summary>Follow-up</summary>
          <ul>
            {result.followUp.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
