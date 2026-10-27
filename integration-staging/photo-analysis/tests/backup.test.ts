import { describe, expect, it } from "vitest";
import { createBackup, parseBackup } from "../backup";
import type { FieldVisit } from "../field-log";
import type { PhotoInterpretation } from "../types";

const visit: FieldVisit = {
  id: "visit-1",
  name: "North campus",
  siteAddress: "1 Main Street",
  buildingType: "W1",
  seismicity: "Moderate",
  performanceLevel: "CP",
  startedAt: "2026-10-27T12:00:00.000Z",
  updatedAt: "2026-10-27T12:00:00.000Z",
  observations: [
    {
      id: "observation-1",
      createdAt: "2026-10-27T12:01:00.000Z",
      locationInBuilding: "Level 1, north wall",
      note: "Hairline crack at the window corner.",
      photoDescription: "Close-up of the diagonal crack above the north window.",
      codeReference: "ASCE/SEI 41-23; verify applicable provision.",
      photo: {
        id: "photo-1",
        blob: new Blob(["photo-bytes"], { type: "image/jpeg" }),
        mediaType: "image/jpeg",
        width: 10,
        height: 8,
        takenAt: "2026-10-27T12:01:00.000Z",
      },
    },
  ],
};

describe("field-notes backup", () => {
  it("round-trips observations and photo bytes", async () => {
    const result = parseBackup(await createBackup([visit]));
    expect(result).toHaveLength(1);
    expect(result[0].observations[0].note).toBe(visit.observations[0].note);
    expect(result[0].observations[0].photoDescription).toBe(visit.observations[0].photoDescription);
    expect(result[0].observations[0].photo?.blob.type).toBe("image/jpeg");
    expect(await result[0].observations[0].photo?.blob.text()).toBe("photo-bytes");
  });

  it("fills conservative defaults for older interpretations in saved backups", async () => {
    const interpretation: PhotoInterpretation = {
      summary: "A crack is visible.",
      components: [],
      observations: [{ description: "Crack at opening", severity: "moderate", confidence: "medium" }],
      possibleDeficiencies: [{
        description: "Potential missing anchorage",
        relatedChecklistItemId: "item-1",
        severity: "moderate",
        confidence: "low",
      }],
      suggestedStatus: null,
      followUp: [],
      imageQuality: { usable: true, issues: [] },
      model: "test-model",
      createdAt: "2026-10-27T12:01:00.000Z",
    };
    const visitWithInterpretation: FieldVisit = {
      ...visit,
      observations: [{ ...visit.observations[0], interpretation }],
    };
    const backup = JSON.parse(await createBackup([visitWithInterpretation])) as {
      visits: Array<{
        observations: Array<{
          interpretation: {
            observations: Array<Record<string, unknown>>;
            possibleDeficiencies: Array<Record<string, unknown>>;
          };
        }>;
      }>;
    };
    const oldInterpretation = backup.visits[0].observations[0].interpretation;
    delete oldInterpretation.observations[0].confidence;
    delete oldInterpretation.possibleDeficiencies[0].severity;

    const [restored] = parseBackup(JSON.stringify(backup));
    expect(restored.observations[0].interpretation?.observations[0].confidence).toBe("medium");
    expect(restored.observations[0].interpretation?.possibleDeficiencies[0].severity).toBe("moderate");
  });

  it("rejects malformed or unsupported backup files", () => {
    expect(() => parseBackup("{invalid")).toThrow("not valid JSON");
    expect(() => parseBackup(JSON.stringify({ format: "other", version: 1, visits: [] }))).toThrow(
      "not a supported MORGAN",
    );
  });
});
