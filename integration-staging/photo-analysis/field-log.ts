import type { CapturedPhoto, PhotoInterpretation } from "./types";

export interface FieldObservation {
  id: string;
  createdAt: string;
  locationInBuilding: string;
  note: string;
  photoDescription?: string;
  codeReference: string;
  photo?: CapturedPhoto;
  interpretation?: PhotoInterpretation;
}

export interface FieldVisit {
  id: string;
  name: string;
  siteAddress: string;
  buildingType: string;
  seismicity: string;
  performanceLevel: "CP" | "IO";
  startedAt: string;
  updatedAt: string;
  observations: FieldObservation[];
}
