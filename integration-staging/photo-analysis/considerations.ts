import type { FieldObservation } from "./field-log";
import type { Confidence, Severity } from "./types";

const SEVERITY_WEIGHT: Record<Severity, number> = {
  info: 1,
  minor: 2,
  moderate: 4,
  severe: 8,
};

const CONFIDENCE_WEIGHT: Record<Confidence, number> = {
  low: 0.4,
  medium: 0.7,
  high: 1,
};

const SEVERITY_ORDER: Severity[] = ["info", "minor", "moderate", "severe"];

export interface OngoingConsideration {
  description: string;
  severity: Severity;
  confidence: Confidence;
  priorityScore: number;
  priority: "urgent" | "high" | "monitor" | "routine";
  supportingPhotos: number;
  locations: string[];
  kinds: Array<"finding" | "follow-up">;
}

interface Candidate {
  description: string;
  severity: Severity;
  confidence: Confidence;
  observationId: string;
  location: string;
  kind: "finding" | "follow-up";
}

function normalizedSeverity(value: unknown): Severity {
  return value === "info" || value === "minor" || value === "moderate" || value === "severe"
    ? value
    : "moderate";
}

function normalizedConfidence(value: unknown): Confidence {
  return value === "low" || value === "medium" || value === "high" ? value : "medium";
}

function normalizedKey(value: string): string {
  return value.toLocaleLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function riskScore(severity: Severity, confidence: Confidence): number {
  return SEVERITY_WEIGHT[severity] * CONFIDENCE_WEIGHT[confidence];
}

function priorityBand(score: number): OngoingConsideration["priority"] {
  if (score >= 6) return "urgent";
  if (score >= 3) return "high";
  if (score >= 1.5) return "monitor";
  return "routine";
}

/** Rebuilds the ranked field watchlist from all currently analyzed photos. */
export function buildOngoingConsiderations(
  observations: FieldObservation[],
): OngoingConsideration[] {
  const candidates: Candidate[] = [];

  for (const observation of observations) {
    const interpretation = observation.interpretation;
    if (!interpretation) continue;

    for (const finding of interpretation.observations) {
      candidates.push({
        description: finding.description,
        severity: normalizedSeverity(finding.severity),
        confidence: normalizedConfidence(finding.confidence),
        observationId: observation.id,
        location: observation.locationInBuilding,
        kind: "finding",
      });
    }

    for (const deficiency of interpretation.possibleDeficiencies) {
      candidates.push({
        description: deficiency.description,
        severity: normalizedSeverity(deficiency.severity),
        confidence: normalizedConfidence(deficiency.confidence),
        observationId: observation.id,
        location: observation.locationInBuilding,
        kind: "finding",
      });
    }

    const relatedFindings = [
      ...interpretation.observations,
      ...interpretation.possibleDeficiencies,
    ];
    const strongestFinding = relatedFindings.reduce<
      { severity: Severity; confidence: Confidence; score: number } | undefined
    >((strongest, finding) => {
      const severity = normalizedSeverity(finding.severity);
      const confidence = normalizedConfidence(finding.confidence);
      const score = riskScore(severity, confidence);
      return !strongest || score > strongest.score
        ? { severity, confidence, score }
        : strongest;
    }, undefined);

    for (const followUp of interpretation.followUp) {
      candidates.push({
        description: followUp,
        severity: strongestFinding?.severity ?? "minor",
        confidence: strongestFinding?.confidence ?? "low",
        observationId: observation.id,
        location: observation.locationInBuilding,
        kind: "follow-up",
      });
    }
  }

  const grouped = new Map<string, Candidate[]>();
  for (const candidate of candidates) {
    const key = normalizedKey(candidate.description);
    if (!key) continue;
    const group = grouped.get(key) ?? [];
    group.push(candidate);
    grouped.set(key, group);
  }

  return [...grouped.values()]
    .map((group) => {
      const bestEvidence = group.reduce((best, candidate) =>
        riskScore(candidate.severity, candidate.confidence) >
        riskScore(best.severity, best.confidence)
          ? candidate
          : best,
      );
      const supportingPhotos = new Set(group.map((candidate) => candidate.observationId)).size;
      const recurrenceMultiplier = Math.min(1.8, 1 + 0.2 * (supportingPhotos - 1));
      const priorityScore = Math.round(
        riskScore(bestEvidence.severity, bestEvidence.confidence) * recurrenceMultiplier * 100,
      ) / 100;

      return {
        description: bestEvidence.description,
        severity: bestEvidence.severity,
        confidence: bestEvidence.confidence,
        priorityScore,
        priority: priorityBand(priorityScore),
        supportingPhotos,
        locations: [...new Set(group.map((candidate) => candidate.location.trim()).filter(Boolean))],
        kinds: [...new Set(group.map((candidate) => candidate.kind))],
      };
    })
    .sort((left, right) => right.priorityScore - left.priorityScore || left.description.localeCompare(right.description));
}
