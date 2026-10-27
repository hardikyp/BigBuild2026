import { describe, expect, it } from "vitest";
import { buildOngoingConsiderations } from "../considerations";
import type { FieldObservation } from "../field-log";
import type { PhotoInterpretation, Severity, Confidence } from "../types";

function observation(
  id: string,
  locationInBuilding: string,
  options: {
    findings?: Array<{ description: string; severity: Severity; confidence: Confidence }>;
    deficiencies?: Array<{ description: string; severity: Severity; confidence: Confidence }>;
    followUp?: string[];
  },
): FieldObservation {
  const interpretation: PhotoInterpretation = {
    summary: "Visible structural condition.",
    components: [],
    observations: options.findings ?? [],
    possibleDeficiencies: options.deficiencies ?? [],
    suggestedStatus: null,
    followUp: options.followUp ?? [],
    imageQuality: { usable: true, issues: [] },
    model: "test-model",
    createdAt: "2026-10-27T12:00:00.000Z",
  };
  return {
    id,
    createdAt: "2026-10-27T12:00:00.000Z",
    locationInBuilding,
    note: "",
    codeReference: "",
    interpretation,
  };
}

describe("ongoing considerations", () => {
  it("ranks severity and confidence transparently", () => {
    const items = buildOngoingConsiderations([
      observation("severe", "Level 1", {
        findings: [{ description: "Severe crack", severity: "severe", confidence: "low" }],
      }),
      observation("minor", "Level 2", {
        findings: [{ description: "Minor crack", severity: "minor", confidence: "high" }],
      }),
    ]);

    expect(items.map((item) => item.description)).toEqual(["Severe crack", "Minor crack"]);
    expect(items.map((item) => item.priorityScore)).toEqual([3.2, 2]);
    expect(items[0].priority).toBe("high");
    expect(items[1].priority).toBe("monitor");
  });

  it("deduplicates equivalent descriptions and raises priority for repeated photos", () => {
    const items = buildOngoingConsiderations([
      observation("photo-1", "Level 1", {
        findings: [{ description: "Diagonal crack at column", severity: "moderate", confidence: "medium" }],
      }),
      observation("photo-2", "Level 2", {
        findings: [{ description: "DIAGONAL crack at column!", severity: "moderate", confidence: "medium" }],
      }),
    ]);

    expect(items).toHaveLength(1);
    expect(items[0].supportingPhotos).toBe(2);
    expect(items[0].priorityScore).toBe(3.36);
    expect(items[0].locations).toEqual(["Level 1", "Level 2"]);
  });

  it("combines findings, possible deficiencies, and related follow-up checks", () => {
    const items = buildOngoingConsiderations([
      observation("photo-1", "North wall", {
        deficiencies: [{ description: "Missing wall anchorage", severity: "severe", confidence: "medium" }],
        followUp: ["Verify wall anchorage at adjacent bays"],
      }),
    ]);

    expect(items.map((item) => item.description)).toEqual([
      "Missing wall anchorage",
      "Verify wall anchorage at adjacent bays",
    ]);
    expect(items[1]).toMatchObject({
      severity: "severe",
      confidence: "medium",
      priorityScore: 5.6,
      priority: "high",
      kinds: ["follow-up"],
      locations: ["North wall"],
    });
  });

  it("ignores observations without photo interpretations", () => {
    const unanalyzed: FieldObservation = {
      id: "note-only",
      createdAt: "2026-10-27T12:00:00.000Z",
      locationInBuilding: "Level 1",
      note: "Check this later",
      codeReference: "",
    };
    expect(buildOngoingConsiderations([unanalyzed])).toEqual([]);
  });
});
