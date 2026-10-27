import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { PhotoCapture, type InterpretationContext, type PhotoInterpretation } from "../index";

function Demo() {
  const [buildingType, setBuildingType] = useState("W1");
  const [performanceLevel, setPerformanceLevel] = useState<"CP" | "IO">("CP");
  const [itemId, setItemId] = useState("");
  const [itemTitle, setItemTitle] = useState("");
  const [itemText, setItemText] = useState("");
  const [note, setNote] = useState("");
  const [last, setLast] = useState<PhotoInterpretation | null>(null);
  const [accepted, setAccepted] = useState<string | null>(null);

  const context: InterpretationContext = {
    buildingType,
    performanceLevel,
    userNote: note || undefined,
    checklistItem: itemTitle ? { id: itemId || "item", title: itemTitle, text: itemText || undefined } : undefined,
  };

  return (
    <main style={{ display: "grid", gap: 12 }}>
      <h1 style={{ fontSize: "1.3em" }}>Field capture demo</h1>
      <label>
        Building type
        <input value={buildingType} onChange={(e) => setBuildingType(e.target.value)} />
      </label>
      <label>
        Performance level
        <select value={performanceLevel} onChange={(e) => setPerformanceLevel(e.target.value as "CP" | "IO")}>
          <option value="CP">CP</option>
          <option value="IO">IO</option>
        </select>
      </label>
      <label>
        Checklist item id (optional)
        <input value={itemId} onChange={(e) => setItemId(e.target.value)} />
      </label>
      <label>
        Checklist item title (optional)
        <input value={itemTitle} onChange={(e) => setItemTitle(e.target.value)} />
      </label>
      <label>
        Checklist item statement (optional)
        <textarea rows={3} value={itemText} onChange={(e) => setItemText(e.target.value)} />
      </label>
      <label>
        Note (optional)
        <input value={note} onChange={(e) => setNote(e.target.value)} />
      </label>

      <PhotoCapture
        context={context}
        prepare={{ withLocation: true }}
        onCaptured={(p) => console.log("captured", p)}
        onInterpreted={(_p, r) => setLast(r)}
        onAcceptStatus={(s) => setAccepted(s)}
      />

      {accepted && <p>Accepted status: <strong>{accepted}</strong></p>}
      {last && (
        <details>
          <summary>Raw result JSON</summary>
          <pre>{JSON.stringify(last, null, 2)}</pre>
        </details>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Demo />
  </StrictMode>,
);
