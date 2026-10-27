import { blobToBase64 } from "./capture";
import type { FieldObservation, FieldVisit } from "./field-log";
import type {
  CapturedPhoto,
  ChecklistStatus,
  Confidence,
  PhotoInterpretation,
  Severity,
} from "./types";

const BACKUP_FORMAT = "morgan-field-notes";
const BACKUP_VERSION = 1;

interface BackupPhoto extends Omit<CapturedPhoto, "blob"> {
  blobBase64: string;
}

interface BackupObservation extends Omit<FieldObservation, "photo"> {
  photo?: BackupPhoto;
}

interface BackupVisit extends Omit<FieldVisit, "observations"> {
  observations: BackupObservation[];
}

interface BackupDocument {
  format: typeof BACKUP_FORMAT;
  version: typeof BACKUP_VERSION;
  exportedAt: string;
  visits: BackupVisit[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requiredString(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string") throw new Error(`Backup is missing a valid "${key}" field.`);
  return value;
}

function isChecklistStatus(value: unknown): value is ChecklistStatus {
  return value === "C" || value === "NC" || value === "N/A" || value === "U";
}

function isSeverity(value: unknown): value is Severity {
  return value === "info" || value === "minor" || value === "moderate" || value === "severe";
}

function isConfidence(value: unknown): value is Confidence {
  return value === "low" || value === "medium" || value === "high";
}

function parseStringArray(value: unknown, label: string): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new Error(`Backup contains an invalid ${label} list.`);
  }
  return value;
}

function parseInterpretation(value: unknown): PhotoInterpretation {
  if (!isRecord(value)) throw new Error("Backup contains an invalid photo interpretation.");
  if (typeof value.summary !== "string") throw new Error("Backup contains an incomplete photo interpretation.");
  if (!Array.isArray(value.components) || !Array.isArray(value.observations) || !Array.isArray(value.possibleDeficiencies)) {
    throw new Error("Backup contains invalid interpretation details.");
  }
  const components = value.components.map((component) => {
    if (!isRecord(component) || typeof component.name !== "string") {
      throw new Error("Backup contains an invalid component description.");
    }
    if (component.material !== undefined && typeof component.material !== "string") {
      throw new Error("Backup contains invalid component material.");
    }
    if (component.condition !== undefined && typeof component.condition !== "string") {
      throw new Error("Backup contains invalid component condition.");
    }
    return {
      name: component.name,
      material: component.material,
      condition: component.condition,
    };
  });
  const observations = value.observations.map((observation) => {
    if (!isRecord(observation) || typeof observation.description !== "string" || !isSeverity(observation.severity)) {
      throw new Error("Backup contains an invalid photo observation.");
    }
    if (observation.confidence !== undefined && !isConfidence(observation.confidence)) {
      throw new Error("Backup contains an invalid photo observation confidence.");
    }
    return {
      description: observation.description,
      severity: observation.severity,
      confidence: isConfidence(observation.confidence) ? observation.confidence : "medium",
    };
  });
  const possibleDeficiencies = value.possibleDeficiencies.map((deficiency) => {
    if (!isRecord(deficiency) || typeof deficiency.description !== "string" || !isConfidence(deficiency.confidence)) {
      throw new Error("Backup contains an invalid possible deficiency.");
    }
    if (deficiency.relatedChecklistItemId !== undefined && typeof deficiency.relatedChecklistItemId !== "string") {
      throw new Error("Backup contains an invalid checklist item reference.");
    }
    if (deficiency.severity !== undefined && !isSeverity(deficiency.severity)) {
      throw new Error("Backup contains an invalid deficiency severity.");
    }
    return {
      description: deficiency.description,
      relatedChecklistItemId: deficiency.relatedChecklistItemId,
      severity: isSeverity(deficiency.severity) ? deficiency.severity : "moderate",
      confidence: deficiency.confidence,
    };
  });
  const suggestedStatus = value.suggestedStatus;
  if (suggestedStatus !== null && !isChecklistStatus(suggestedStatus)) {
    throw new Error("Backup contains an invalid suggested status.");
  }
  const quality = value.imageQuality;
  if (!isRecord(quality) || typeof quality.usable !== "boolean") {
    throw new Error("Backup contains invalid photo quality details.");
  }
  if (typeof value.model !== "string" || typeof value.createdAt !== "string") {
    throw new Error("Backup contains incomplete interpretation metadata.");
  }
  if (value.statusRationale !== undefined && typeof value.statusRationale !== "string") {
    throw new Error("Backup contains an invalid status rationale.");
  }
  return {
    summary: value.summary,
    components,
    observations,
    possibleDeficiencies,
    suggestedStatus,
    statusRationale: value.statusRationale,
    followUp: parseStringArray(value.followUp, "follow-up"),
    imageQuality: { usable: quality.usable, issues: parseStringArray(quality.issues, "image quality") },
    model: value.model,
    createdAt: value.createdAt,
  };
}

function parsePhoto(value: unknown): CapturedPhoto {
  if (!isRecord(value)) throw new Error("Backup contains an invalid photo.");
  const blobBase64 = requiredString(value, "blobBase64");
  if (blobBase64.length % 4 !== 0 || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(blobBase64)) {
    throw new Error("Backup contains an invalid photo encoding.");
  }
  const id = requiredString(value, "id");
  const takenAt = requiredString(value, "takenAt");
  const width = value.width;
  const height = value.height;
  const mediaType = value.mediaType;
  if (
    typeof width !== "number" ||
    typeof height !== "number" ||
    width <= 0 ||
    height <= 0 ||
    mediaType !== "image/jpeg"
  ) {
    throw new Error("Backup contains invalid photo metadata.");
  }
  if (value.originalName !== undefined && typeof value.originalName !== "string") {
    throw new Error("Backup contains an invalid original photo name.");
  }
  let location: CapturedPhoto["location"];
  if (value.location !== undefined) {
    if (
      !isRecord(value.location) ||
      typeof value.location.lat !== "number" ||
      typeof value.location.lon !== "number" ||
      (value.location.accuracyM !== undefined && typeof value.location.accuracyM !== "number")
    ) {
      throw new Error("Backup contains invalid photo location metadata.");
    }
    location = {
      lat: value.location.lat,
      lon: value.location.lon,
      accuracyM: value.location.accuracyM,
    };
  }
  const bytes = Uint8Array.from(atob(blobBase64), (character) => character.charCodeAt(0));
  return {
    id,
    takenAt,
    width,
    height,
    mediaType,
    originalName: value.originalName,
    location,
    blob: new Blob([bytes], { type: mediaType }),
  };
}

function parseObservation(value: unknown): FieldObservation {
  if (!isRecord(value)) throw new Error("Backup contains an invalid observation.");
  const observation: FieldObservation = {
    id: requiredString(value, "id"),
    createdAt: requiredString(value, "createdAt"),
    locationInBuilding: requiredString(value, "locationInBuilding"),
    note: requiredString(value, "note"),
    codeReference: requiredString(value, "codeReference"),
  };
  if (value.photoDescription !== undefined) {
    if (typeof value.photoDescription !== "string") {
      throw new Error("Backup contains an invalid photo description.");
    }
    observation.photoDescription = value.photoDescription;
  }
  if (value.photo !== undefined) observation.photo = parsePhoto(value.photo);
  if (value.interpretation !== undefined) {
    observation.interpretation = parseInterpretation(value.interpretation);
  }
  return observation;
}

function parseVisit(value: unknown): FieldVisit {
  if (!isRecord(value) || !Array.isArray(value.observations)) {
    throw new Error("Backup contains an invalid site visit.");
  }
  const performanceLevel = value.performanceLevel;
  if (performanceLevel !== "CP" && performanceLevel !== "IO") {
    throw new Error("Backup contains an invalid performance objective.");
  }
  return {
    id: requiredString(value, "id"),
    name: requiredString(value, "name"),
    siteAddress: requiredString(value, "siteAddress"),
    buildingType: requiredString(value, "buildingType"),
    seismicity: requiredString(value, "seismicity"),
    performanceLevel,
    startedAt: requiredString(value, "startedAt"),
    updatedAt: requiredString(value, "updatedAt"),
    observations: value.observations.map(parseObservation),
  };
}

export async function createBackup(visits: FieldVisit[]): Promise<string> {
  const backupVisits: BackupVisit[] = await Promise.all(
    visits.map(async (visit) => {
      const observations: BackupObservation[] = await Promise.all(
        visit.observations.map(async (observation): Promise<BackupObservation> => {
          const { photo, ...metadata } = observation;
          if (!photo) return metadata;
          const { blob, ...photoMetadata } = photo;
          return {
            ...metadata,
            photo: { ...photoMetadata, blobBase64: await blobToBase64(blob) },
          };
        }),
      );
      return { ...visit, observations };
    }),
  );
  const backup: BackupDocument = {
    format: BACKUP_FORMAT,
    version: BACKUP_VERSION,
    exportedAt: new Date().toISOString(),
    visits: backupVisits,
  };
  return JSON.stringify(backup, null, 2);
}

export function parseBackup(text: string): FieldVisit[] {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    throw new Error("This file is not valid JSON.");
  }
  if (!isRecord(value) || value.format !== BACKUP_FORMAT || value.version !== BACKUP_VERSION) {
    throw new Error("This is not a supported MORGAN field-notes backup.");
  }
  if (!Array.isArray(value.visits)) throw new Error("Backup does not contain a visits list.");
  return value.visits.map(parseVisit);
}
