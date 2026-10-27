/**
 * Field-capture module: shared types.
 *
 * These are the contract between the field-capture module and the rest of the
 * app. Other workstreams (checklist UI, offline storage, reports) should depend
 * only on these types, not on module internals.
 */

/** Tier 1 checklist status values. */
export type ChecklistStatus = "C" | "NC" | "N/A" | "U";

export type PerformanceLevel = "CP" | "IO";

export interface GeoLocation {
  lat: number;
  lon: number;
  /** Horizontal accuracy in metres, as reported by the device. */
  accuracyM?: number;
}

/** A photo after capture and preparation (resized, re-encoded as JPEG). */
export interface CapturedPhoto {
  /** Unique id, safe to use as a storage key. */
  id: string;
  /** Prepared image, ready to store or upload. */
  blob: Blob;
  mediaType: "image/jpeg";
  width: number;
  height: number;
  /** ISO 8601 timestamp of capture. */
  takenAt: string;
  location?: GeoLocation;
  /** Original file name, if the photo came from a file picker. */
  originalName?: string;
}

/**
 * What the app knows about where this photo fits. Everything is optional, but
 * the more context you pass, the more useful the interpretation.
 *
 * Checklist text comes from the app's checklist data at runtime; this module
 * never embeds checklist wording itself.
 */
export interface InterpretationContext {
  /** ASCE 41 building type code, e.g. "W1", "S2", "C2", "URM". */
  buildingType?: string;
  performanceLevel?: PerformanceLevel;
  /** Level of seismicity, e.g. "Very Low", "Low", "Moderate", "High". */
  seismicity?: string;
  /** The checklist item the user is evaluating when they took the photo. */
  checklistItem?: {
    id: string;
    title: string;
    /** Full statement of the item, from the app's checklist data. */
    text?: string;
  };
  /** Location in the building, e.g. "Level 2, grid C/4, north wall". */
  locationInBuilding?: string;
  /** Free-text note from the engineer. */
  userNote?: string;
}

export type Severity = "info" | "minor" | "moderate" | "severe";
export type Confidence = "low" | "medium" | "high";

/** Structured LLM interpretation of one photo. Advisory only. */
export interface PhotoInterpretation {
  /** One- or two-sentence description of what the photo shows. */
  summary: string;
  /** Structural and nonstructural components visible. */
  components: Array<{
    name: string;
    material?: string;
    condition?: string;
  }>;
  /** Notable observations (damage, deterioration, configuration). */
  observations: Array<{
    description: string;
    severity: Severity;
  }>;
  /** Possible seismic deficiencies suggested by the photo. */
  possibleDeficiencies: Array<{
    description: string;
    relatedChecklistItemId?: string;
    confidence: Confidence;
  }>;
  /**
   * Suggested status for the checklist item in context, or null when no item
   * was given or the photo can't support a call. The engineer decides; the app
   * should present this as a suggestion only.
   */
  suggestedStatus: ChecklistStatus | null;
  /** Rationale for the suggested status. */
  statusRationale?: string;
  /** What to photograph, measure or verify next. */
  followUp: string[];
  imageQuality: {
    usable: boolean;
    issues: string[];
  };
  /** Model that produced this interpretation. */
  model: string;
  /** ISO 8601 timestamp. */
  createdAt: string;
}

/** JSON body the client sends to the interpretation endpoint. */
export interface InterpretRequestBody {
  /** Base64 image data, without the data: URL prefix. */
  image: string;
  mediaType: "image/jpeg" | "image/png" | "image/webp" | "image/gif";
  context?: InterpretationContext;
}

/** JSON body the endpoint returns on error. */
export interface InterpretErrorBody {
  error: string;
  code:
    | "bad_request"
    | "image_too_large"
    | "upstream_error"
    | "invalid_model_output"
    | "server_misconfigured";
}
