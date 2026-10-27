import { StrictMode, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { usePhotoInterpretation } from "../react/usePhotoInterpretation";
import { createBackup, parseBackup } from "../backup";
import type { FieldObservation, FieldVisit } from "../field-log";
import { buildOngoingConsiderations } from "../considerations";
import { listVisits, saveVisit, saveVisits } from "../storage";
import type { CapturedPhoto, InterpretationContext, PhotoInterpretation } from "../types";
import "./field-log.css";

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `visit-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function newVisit(): FieldVisit {
  const now = new Date().toISOString();
  return {
    id: newId(),
    name: "",
    siteAddress: "",
    buildingType: "",
    seismicity: "",
    performanceLevel: "CP",
    startedAt: now,
    updatedAt: now,
    observations: [],
  };
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function messageFromError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function FieldNotesApp() {
  const [visits, setVisits] = useState<FieldVisit[]>([]);
  const visitsRef = useRef<FieldVisit[]>([]);
  const [activeVisitId, setActiveVisitId] = useState("");
  const [loading, setLoading] = useState(true);
  const [storageError, setStorageError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [observationNote, setObservationNote] = useState("");
  const [observationLocation, setObservationLocation] = useState("");
  const [observationCode, setObservationCode] = useState("");
  const importRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    listVisits()
      .then(async (savedVisits) => {
        if (!active) return;
        const sorted = savedVisits.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
        if (sorted.length === 0) {
          const visit = newVisit();
          await saveVisit(visit);
          if (!active) return;
          sorted.push(visit);
        }
        visitsRef.current = sorted;
        setVisits(sorted);
        setActiveVisitId(sorted[0].id);
      })
      .catch((error: unknown) => {
        if (active) setStorageError(messageFromError(error));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const activeVisit = visits.find((visit) => visit.id === activeVisitId);
  const ongoingConsiderations = activeVisit
    ? buildOngoingConsiderations(activeVisit.observations)
    : [];

  function commitVisit(updatedVisit: FieldVisit) {
    const nextVisits = visitsRef.current.some((visit) => visit.id === updatedVisit.id)
      ? visitsRef.current.map((visit) => (visit.id === updatedVisit.id ? updatedVisit : visit))
      : [updatedVisit, ...visitsRef.current];
    visitsRef.current = nextVisits;
    setVisits(nextVisits);
    void saveVisit(updatedVisit)
      .then(() => setStorageError(null))
      .catch((error: unknown) => setStorageError(messageFromError(error)));
  }

  function updateActiveVisit(update: (visit: FieldVisit) => FieldVisit) {
    const currentVisit = visitsRef.current.find((visit) => visit.id === activeVisitId);
    if (!currentVisit) return;
    commitVisit(update({ ...currentVisit, updatedAt: new Date().toISOString() }));
  }

  function patchVisit<K extends keyof FieldVisit>(key: K, value: FieldVisit[K]) {
    updateActiveVisit((visit) => ({ ...visit, [key]: value }));
  }

  function addObservation(photo?: FieldObservation["photo"], photoDescription?: string) {
    if (!activeVisit) return;
    const note = observationNote.trim();
    if (!note && !photo) {
      setActionError("Add a field note or capture a photo before saving an observation.");
      return;
    }
    const observation: FieldObservation = {
      id: newId(),
      createdAt: new Date().toISOString(),
      locationInBuilding: observationLocation.trim(),
      note,
      photoDescription: photoDescription?.trim() || undefined,
      codeReference: observationCode.trim(),
      photo,
    };
    updateActiveVisit((visit) => ({ ...visit, observations: [observation, ...visit.observations] }));
    setActionError(null);
    if (!photo) {
      setObservationNote("");
      setObservationLocation("");
      setObservationCode("");
    }
  }

  function saveInterpretation(photoId: string, interpretation: NonNullable<FieldObservation["interpretation"]>) {
    const visit = visitsRef.current.find((entry) =>
      entry.observations.some((observation) => observation.photo?.id === photoId),
    );
    if (!visit) return;
    commitVisit({
      ...visit,
      updatedAt: new Date().toISOString(),
      observations: visit.observations.map((observation) =>
        observation.photo?.id === photoId ? { ...observation, interpretation } : observation,
      ),
    });
  }

  function removeObservation(observationId: string) {
    updateActiveVisit((visit) => ({
      ...visit,
      observations: visit.observations.filter((observation) => observation.id !== observationId),
    }));
  }

  async function handleExport() {
    try {
      const content = await createBackup(visitsRef.current);
      const url = URL.createObjectURL(new Blob([content], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `morgan-field-notes-${new Date().toISOString().slice(0, 10)}.json`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setActionError(null);
    } catch (error) {
      setActionError(`Could not export the field notes: ${messageFromError(error)}`);
    }
  }

  async function handleImport(file: File | undefined) {
    if (!file) return;
    try {
      const imported = parseBackup(await file.text());
      await saveVisits(imported);
      const mergedById = new Map(visitsRef.current.map((visit) => [visit.id, visit]));
      for (const visit of imported) mergedById.set(visit.id, visit);
      const merged = [...mergedById.values()].sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
      visitsRef.current = merged;
      setVisits(merged);
      if (imported[0]) setActiveVisitId(imported[0].id);
      setActionError(null);
    } catch (error) {
      setActionError(`Could not import this backup: ${messageFromError(error)}`);
    } finally {
      if (importRef.current) importRef.current.value = "";
    }
  }

  function createVisit() {
    const visit = newVisit();
    commitVisit(visit);
    setActiveVisitId(visit.id);
    setObservationNote("");
    setObservationLocation("");
    setObservationCode("");
  }

  const interpretationContext: InterpretationContext = {
    buildingType: activeVisit?.buildingType || undefined,
    performanceLevel: activeVisit?.performanceLevel,
    seismicity: activeVisit?.seismicity || undefined,
    locationInBuilding: observationLocation.trim() || undefined,
    userNote: observationNote.trim() || undefined,
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand" aria-label="MORGAN Field Notes">
          <span className="brand-mark">M</span>
          <span>
            <strong>MORGAN</strong>
            <small>FIELD NOTES</small>
          </span>
        </div>
        <div className="topbar-actions">
          <span className="save-state" aria-live="polite">
            {storageError ? "Local save issue" : loading ? "Loading" : "Saved on this device"}
          </span>
          <button className="button button-quiet" type="button" onClick={() => void handleExport()} disabled={loading}>
            Export backup
          </button>
          <button className="button button-quiet" type="button" onClick={() => importRef.current?.click()} disabled={loading}>
            Import backup
          </button>
          <input
            ref={importRef}
            className="visually-hidden"
            type="file"
            accept="application/json,.json"
            onChange={(event) => void handleImport(event.target.files?.[0])}
          />
        </div>
      </header>

      <main className="page">
        <section className="intro">
          <div>
            <p className="eyebrow">SEISMIC SITE VISIT · ASCE 41</p>
            <h1>Observe first.<br />Evaluate with evidence.</h1>
            <p className="intro-copy">
              Capture site conditions as you walk. Keep engineer notes and photo-based follow-up suggestions together.
            </p>
          </div>
          <div className="visit-switcher">
            <label htmlFor="visit-select">Site visit</label>
            <div className="visit-select-row">
              <select
                id="visit-select"
                value={activeVisitId}
                onChange={(event) => {
                  setActiveVisitId(event.target.value);
                  setObservationNote("");
                  setObservationLocation("");
                  setObservationCode("");
                }}
                disabled={loading || visits.length === 0}
              >
                {visits.map((visit) => (
                  <option key={visit.id} value={visit.id}>
                    {visit.name.trim() || `Untitled visit · ${formatTime(visit.startedAt)}`}
                  </option>
                ))}
              </select>
              <button className="button button-light" type="button" onClick={createVisit} disabled={loading}>
                + New visit
              </button>
            </div>
          </div>
        </section>

        <section className="notice" aria-label="Data and AI privacy">
          <span className="notice-icon" aria-hidden="true">i</span>
          <p>
            <strong>Device-local notes.</strong> Visits and photos are stored in this browser. Photo interpretation
            sends the prepared image and visit context to GitHub Copilot through the server-side Copilot SDK.
            Use only with approved project photos and export a backup before clearing browser data.
          </p>
        </section>

        {storageError && (
          <div className="alert" role="alert">
            Local storage could not be used: {storageError}. Changes may not survive closing this page.
          </div>
        )}
        {actionError && (
          <div className="alert" role="alert">
            {actionError}
          </div>
        )}

        {loading ? (
          <div className="loading-panel">Opening your local field log…</div>
        ) : activeVisit ? (
          <>
            <section className="panel building-panel">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">VISIT SETUP</p>
                  <h2>Building context</h2>
                </div>
                <span className="local-badge"><span /> On this device</span>
              </div>
              <div className="field-grid">
                <label className="field field-wide">
                  Project / building name
                  <input
                    value={activeVisit.name}
                    onChange={(event) => patchVisit("name", event.target.value)}
                    placeholder="e.g. North campus library"
                  />
                </label>
                <label className="field field-wide">
                  Site address
                  <input
                    value={activeVisit.siteAddress}
                    onChange={(event) => patchVisit("siteAddress", event.target.value)}
                    placeholder="Street address or site identifier"
                  />
                </label>
                <label className="field">
                  Structural system / building type
                  <input
                    value={activeVisit.buildingType}
                    onChange={(event) => patchVisit("buildingType", event.target.value)}
                    placeholder="e.g. W1, S1, URM"
                  />
                </label>
                <label className="field">
                  Seismicity
                  <select value={activeVisit.seismicity} onChange={(event) => patchVisit("seismicity", event.target.value)}>
                    <option value="">Not recorded</option>
                    <option>Very Low</option>
                    <option>Low</option>
                    <option>Moderate</option>
                    <option>High</option>
                    <option>Very High</option>
                  </select>
                </label>
                <label className="field">
                  Performance objective
                  <select
                    value={activeVisit.performanceLevel}
                    onChange={(event) => patchVisit("performanceLevel", event.target.value as "CP" | "IO")}
                  >
                    <option value="CP">Collapse Prevention (CP)</option>
                    <option value="IO">Immediate Occupancy (IO)</option>
                  </select>
                </label>
              </div>
            </section>

            <div className="work-grid">
              <section className="panel capture-panel">
                <div className="section-heading">
                  <div>
                    <p className="eyebrow">FIELD ENTRY</p>
                    <h2>Record an observation</h2>
                  </div>
                  <span className="step-number">01</span>
                </div>
                <p className="section-copy">
                  Note what you can see. Keep possible failure mechanisms separate from confirmed conditions.
                </p>
                <div className="capture-fields">
                  <label className="field">
                    Location in building
                    <input
                      value={observationLocation}
                      onChange={(event) => setObservationLocation(event.target.value)}
                      placeholder="Level, grid, elevation, room…"
                    />
                  </label>
                  <label className="field">
                    Observation / concern
                    <textarea
                      value={observationNote}
                      onChange={(event) => setObservationNote(event.target.value)}
                      placeholder="Describe the visible condition, damage, or question to follow up."
                      rows={4}
                    />
                  </label>
                  <label className="field">
                    Relevant code or standard reference
                    <input
                      value={observationCode}
                      onChange={(event) => setObservationCode(event.target.value)}
                      placeholder="Standard + section/table, if known"
                    />
                    <span className="field-hint">Enter citations for engineer review; exact provisions are not inferred by the photo model.</span>
                  </label>
                  <button className="button button-dark" type="button" onClick={() => addObservation()}>
                    Add note to running log
                  </button>
                </div>

                <div className="photo-entry">
                  <div className="photo-entry-heading">
                    <span className="camera-icon" aria-hidden="true">+</span>
                    <div>
                      <strong>Attach a site photo</strong>
                      <p>Take a picture or choose one from your device. A field note is saved with it.</p>
                    </div>
                  </div>
                          <PhotoEntry
                            key={activeVisit.id}
                            context={interpretationContext}
                            onCaptured={(photo, photoDescription) => addObservation(photo, photoDescription)}
                            onInterpreted={(photo, result) => saveInterpretation(photo.id, result)}
                          />
                </div>
              </section>

              <aside className="panel standards-panel">
                <p className="eyebrow">REFERENCE DESK</p>
                <h2>Structural codes</h2>
                <div className="standard-card">
                  <span className="standard-chip">PRIMARY STANDARD</span>
                  <h3>ASCE/SEI 41-23</h3>
                  <p>Seismic Evaluation and Retrofit of Existing Buildings</p>
                  <p className="standard-note">
                    Confirm the governing edition, adopted jurisdictional requirements, and applicable provisions for each project.
                  </p>
                </div>
                <div className="reference-rule" />
                <h3 className="reference-subhead">Keep citations traceable</h3>
                <p className="section-copy">
                  Add verified section or table citations to each observation. The photo assistant suggests evidence to gather;
                  it does not determine which code provision governs.
                </p>
                <p className="standards-disclaimer">
                  This field log is an evidence aid, not a substitute for the licensed standard or professional judgment.
                </p>
              </aside>
            </div>

            <section className="panel considerations-panel" aria-labelledby="considerations-title">
              <div className="section-heading">
                <div>
                  <p className="eyebrow">CUMULATIVE PHOTO REVIEW</p>
                  <h2 id="considerations-title">
                    Ongoing considerations <span className="count-pill">{ongoingConsiderations.length}</span>
                  </h2>
                </div>
                <span className="local-badge"><span /> This site visit</span>
              </div>
              <p className="section-copy considerations-copy">
                Consolidates and deduplicates findings and follow-up checks across analyzed photos. Higher visual
                severity and confidence raise priority; repeated evidence modestly increases it.
              </p>
              {ongoingConsiderations.length === 0 ? (
                <div className="considerations-empty">
                  Analyze a saved photo with Copilot to start a visit-wide follow-up list.
                </div>
              ) : (
                <ol className="consideration-list">
                  {ongoingConsiderations.map((item) => (
                    <li className="consideration-item" key={item.description}>
                      <div className="consideration-topline">
                        <span className={`priority-badge priority-${item.priority}`}>{item.priority}</span>
                        <span className="consideration-risk">
                          {item.severity} severity · {item.confidence} confidence
                        </span>
                        <span className="consideration-score" title="Severity × confidence × recurrence factor">
                          Score {item.priorityScore.toFixed(2)}
                        </span>
                      </div>
                      <p className="consideration-description">{item.description}</p>
                      <div className="consideration-meta">
                        {item.kinds.includes("finding") && <span>Finding</span>}
                        {item.kinds.includes("follow-up") && <span>Suggested check</span>}
                        <span>{item.supportingPhotos} supporting {item.supportingPhotos === 1 ? "photo" : "photos"}</span>
                        {item.locations.length > 0 && <span>{item.locations.join(" · ")}</span>}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
              <p className="considerations-disclaimer">
                Triage aid only—not a diagnosis, ASCE 41 determination, or substitute for engineering judgment. Verify
                conditions in the field; priority is based on model-assessed visual severity and confidence.
              </p>
            </section>

            <section className="observations-section">
              <div className="section-heading observations-heading">
                <div>
                  <p className="eyebrow">SITE WALK</p>
                  <h2>Running observations <span className="count-pill">{activeVisit.observations.length}</span></h2>
                </div>
                <p className="section-copy">Newest entries appear first · saved locally</p>
              </div>
              {activeVisit.observations.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-mark">01</span>
                  <div>
                    <strong>Your site log is ready.</strong>
                    <p>Add a note or capture a photo to begin building an evidence trail.</p>
                  </div>
                </div>
              ) : (
                <div className="observation-list">
                  {activeVisit.observations.map((observation) => (
                    <ObservationCard
                      key={observation.id}
                      observation={observation}
                      context={{
                        buildingType: activeVisit.buildingType || undefined,
                        performanceLevel: activeVisit.performanceLevel,
                        seismicity: activeVisit.seismicity || undefined,
                        locationInBuilding: observation.locationInBuilding || undefined,
                        userNote: observation.note || undefined,
                        photoDescription: observation.photoDescription,
                      }}
                      onInterpreted={saveInterpretation}
                      onDelete={() => removeObservation(observation.id)}
                    />
                  ))}
                </div>
              )}
            </section>
          </>
        ) : (
          <div className="loading-panel">No visit is selected. Start a new visit to continue.</div>
        )}

        <footer className="page-footer">
          <span>MORGAN · FIELD OBSERVATION PROTOTYPE</span>
          <span>Engineer review required for all interpretations and code references.</span>
        </footer>
      </main>
    </div>
  );
}

function ObservationCard({
  observation,
  context,
  onInterpreted,
  onDelete,
}: {
  observation: FieldObservation;
  context: InterpretationContext;
  onInterpreted: (photoId: string, result: PhotoInterpretation) => void;
  onDelete: () => void;
}) {
  const [photoUrl, setPhotoUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!observation.photo) {
      setPhotoUrl(null);
      return;
    }
    const url = URL.createObjectURL(observation.photo.blob);
    setPhotoUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [observation.photo]);

  return (
    <article className="observation-card">
      <div className="observation-marker" aria-hidden="true" />
      <div className="observation-content">
        <div className="observation-meta">
          <time dateTime={observation.createdAt}>{formatTime(observation.createdAt)}</time>
          {observation.locationInBuilding && <span>{observation.locationInBuilding}</span>}
          <button className="text-button delete-button" type="button" onClick={onDelete}>Remove</button>
        </div>
        {observation.note ? <p className="observation-note">{observation.note}</p> : <p className="subtle-note">Photo captured; add an engineer note when convenient.</p>}
        {observation.photoDescription && (
          <div className="code-reference">
            <strong>Photo description sent to Copilot</strong>
            <span>{observation.photoDescription}</span>
          </div>
        )}
        {observation.codeReference && (
          <div className="code-reference">
            <strong>Code reference</strong>
            <span>{observation.codeReference}</span>
          </div>
        )}
        {photoUrl && <img className="observation-photo" src={photoUrl} alt="Site condition captured for this observation" />}
        {observation.interpretation && <InterpretationDetails result={observation.interpretation} />}
        {observation.photo && !observation.interpretation && (
          <SavedPhotoAnalysis
            photo={observation.photo}
            context={context}
            onInterpreted={onInterpreted}
          />
        )}
      </div>
    </article>
  );
}

function PhotoEntry({
  context,
  onCaptured,
  onInterpreted,
}: {
  context: InterpretationContext;
  onCaptured: (photo: CapturedPhoto, photoDescription: string) => void;
  onInterpreted: (photo: CapturedPhoto, result: PhotoInterpretation) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [photoDescription, setPhotoDescription] = useState("");
  const { status, photo, previewUrl, error, capture, interpret, reset } = usePhotoInterpretation({
    context: { ...context, photoDescription: photoDescription.trim() || undefined },
    prepare: { withLocation: false },
    autoInterpret: false,
    onCaptured: (capturedPhoto) => onCaptured(capturedPhoto, photoDescription.trim()),
    onInterpreted,
  });
  const busy = status === "preparing" || status === "interpreting";

  return (
    <div className="fc-root">
      <input
        ref={inputRef}
        className="visually-hidden"
        type="file"
        accept="image/*"
        capture="environment"
        onChange={(event) => {
          const file = event.target.files?.[0];
          event.target.value = "";
          if (file) void capture(file);
        }}
      />
      <label className="field">
        Description for Copilot
        <textarea
          value={photoDescription}
          onChange={(event) => setPhotoDescription(event.target.value)}
          placeholder="What should Copilot know about this photo? For example, where it was taken or what detail to focus on."
          rows={3}
          maxLength={2000}
          disabled={busy || status === "done"}
        />
        <span className="field-hint">This description is saved with the photo and sent with it for analysis.</span>
      </label>
      <div className="fc-actions">
        <button className="fc-btn fc-btn-primary" type="button" disabled={busy} onClick={() => inputRef.current?.click()}>
          {photo ? "Take or choose another" : "Take or upload photo"}
        </button>
        {photo && (
          <button
            className="fc-btn"
            type="button"
            disabled={busy || status === "done"}
            onClick={() => void interpret(photo)}
          >
            {status === "interpreting" ? "Reviewing photo…" : status === "done" ? "Analysis saved" : "Analyze with Copilot"}
          </button>
        )}
        {photo && !busy && (
          <button className="fc-btn" type="button" onClick={reset}>Clear</button>
        )}
      </div>
      {previewUrl && <img className="fc-preview" src={previewUrl} alt="Photo attached to the field observation" />}
      {status === "preparing" && <p className="fc-status">Preparing photo and saving it to this device…</p>}
      {photo && status === "idle" && <p className="fc-status">Photo saved locally. Choose Analyze with Copilot to request an advisory review.</p>}
      {error && <p className="fc-error" role="alert">{error.message}</p>}
    </div>
  );
}

function SavedPhotoAnalysis({
  photo,
  context,
  onInterpreted,
}: {
  photo: CapturedPhoto;
  context: InterpretationContext;
  onInterpreted: (photoId: string, result: PhotoInterpretation) => void;
}) {
  const { status, error, interpret } = usePhotoInterpretation({
    context,
    autoInterpret: false,
    onInterpreted: (capturedPhoto, result) => onInterpreted(capturedPhoto.id, result),
  });
  const busy = status === "preparing" || status === "interpreting";

  return (
    <div className="saved-photo-analysis">
      <button className="fc-btn" type="button" disabled={busy} onClick={() => void interpret(photo)}>
        {busy ? "Reviewing photo…" : error ? "Retry photo review" : "Request advisory photo review"}
      </button>
      {error && <p className="fc-error" role="alert">{error.message}</p>}
    </div>
  );
}

function InterpretationDetails({ result }: { result: NonNullable<FieldObservation["interpretation"]> }) {
  return (
    <div className="interpretation">
      <div className="interpretation-heading">
        <span className="ai-mark" aria-hidden="true">AI</span>
        <div>
          <strong>Photo review · advisory</strong>
          <span>{result.model} · {formatTime(result.createdAt)}</span>
        </div>
      </div>
      <p className="interpretation-summary">{result.summary}</p>
      {!result.imageQuality.usable && (
        <p className="quality-warning">Image limitations: {result.imageQuality.issues.join("; ") || "The model could not reliably assess this image."}</p>
      )}
      {result.observations.length > 0 && (
        <div className="ai-list">
          <strong>Visible observations</strong>
          <ul>
            {result.observations.map((item, index) => (
              <li key={`${item.description}-${index}`}>
                <span className={`severity severity-${item.severity}`}>{item.severity}</span>
                {item.description} <span className="confidence">({item.confidence} confidence)</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {result.possibleDeficiencies.length > 0 && (
        <div className="ai-list deficiency-list">
          <strong>Potential concerns to verify</strong>
          <ul>
            {result.possibleDeficiencies.map((item, index) => (
              <li key={`${item.description}-${index}`}>
                <span className={`severity severity-${item.severity}`}>{item.severity}</span>
                {item.description} <span className="confidence">({item.confidence} confidence)</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {result.followUp.length > 0 && (
        <div className="ai-list followup-list">
          <strong>Suggested further evaluation</strong>
          <ul>{result.followUp.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>
        </div>
      )}
      <p className="ai-disclaimer">
        Suggestions are based only on the submitted image and context. Verify conditions on site and in drawings/calculations;
        the engineer makes every determination.
      </p>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <FieldNotesApp />
  </StrictMode>,
);
