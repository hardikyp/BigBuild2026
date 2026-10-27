/**
 * Prompt and output schema for photo interpretation.
 * Server-side only in practice, but has no Node dependencies.
 */
import type { InterpretationContext } from "./types";

export const SYSTEM_PROMPT = `You are assisting a licensed structural engineer during a seismic site visit of an existing building, using the ASCE 41 Tier 1 screening approach.

You will be shown one photo taken on site, plus whatever context the engineer has given (building type, performance level, the checklist item being evaluated, notes).

Your job:
- Describe what is actually visible. Identify structural and nonstructural components, materials and condition.
- Note observations relevant to seismic performance: damage, cracking, corrosion, deterioration, missing or inadequate connections, irregularities, pounding risk, unbraced elements, and similar.
- For each observation, estimate how confidently the condition itself is visible in the photo: low, medium, or high. Keep this confidence separate from severity.
- For each possible deficiency, provide both a visual severity (info, minor, moderate, or severe) and confidence (low, medium, or high). Use low confidence for suspected hidden conditions that need verification.
- If a checklist item is given, say whether the photo supports Compliant (C), Noncompliant (NC), Not Applicable (N/A) or Unknown (U), and why. Use U whenever the photo alone cannot settle it. Most items need measurements, drawings or calculations, so U is often correct.
- Suggest concrete follow-up: what else to photograph, measure, or check in drawings.

Rules:
- Only report what the image shows. Do not invent dimensions, details or hidden conditions. Say when something is obscured or ambiguous.
- Be specific and terse, in the voice of a field note.
- Your output is advisory. The engineer makes every determination.
- Return only a JSON object matching the supplied response schema.`;

/** JSON Schema for the tool input; mirrors PhotoInterpretation minus model/createdAt. */
export const OUTPUT_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    summary: {
      type: "string",
      description: "One or two sentences describing what the photo shows.",
    },
    components: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          name: { type: "string" },
          material: { type: ["string", "null"] },
          condition: { type: ["string", "null"] },
        },
        required: ["name", "material", "condition"],
      },
    },
    observations: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          description: { type: "string" },
          severity: { type: "string", enum: ["info", "minor", "moderate", "severe"] },
          confidence: { type: "string", enum: ["low", "medium", "high"] },
        },
        required: ["description", "severity", "confidence"],
      },
    },
    possibleDeficiencies: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          description: { type: "string" },
          relatedChecklistItemId: { type: ["string", "null"] },
          severity: { type: "string", enum: ["info", "minor", "moderate", "severe"] },
          confidence: { type: "string", enum: ["low", "medium", "high"] },
        },
        required: ["description", "relatedChecklistItemId", "severity", "confidence"],
      },
    },
    suggestedStatus: {
      type: ["string", "null"],
      enum: ["C", "NC", "N/A", "U", null],
      description: "Null if no checklist item was given.",
    },
    statusRationale: { type: ["string", "null"] },
    followUp: { type: "array", items: { type: "string" } },
    imageQuality: {
      type: "object",
      additionalProperties: false,
      properties: {
        usable: { type: "boolean" },
        issues: { type: "array", items: { type: "string" } },
      },
      required: ["usable", "issues"],
    },
  },
  required: [
    "summary",
    "components",
    "observations",
    "possibleDeficiencies",
    "suggestedStatus",
    "statusRationale",
    "followUp",
    "imageQuality",
  ],
} as const;

/** Turns the app's context into the text that accompanies the image. */
export function buildUserPrompt(context: InterpretationContext = {}): string {
  const lines: string[] = [];
  if (context.buildingType) lines.push(`Building type: ${context.buildingType}`);
  if (context.performanceLevel) {
    const name =
      context.performanceLevel === "CP" ? "Collapse Prevention" : "Immediate Occupancy";
    lines.push(`Performance level: ${context.performanceLevel} (${name})`);
  }
  if (context.seismicity) lines.push(`Level of seismicity: ${context.seismicity}`);
  if (context.locationInBuilding) lines.push(`Location in building: ${context.locationInBuilding}`);
  if (context.checklistItem) {
    const item = context.checklistItem;
    lines.push(`Checklist item being evaluated: [${item.id}] ${item.title}`);
    if (item.text) lines.push(`Item statement: ${item.text}`);
  } else {
    lines.push("No specific checklist item: give a general seismic-relevant interpretation and set suggestedStatus to null.");
  }
  if (context.userNote) lines.push(`Engineer's note: ${context.userNote}`);
  if (context.photoDescription) lines.push(`Engineer's photo description: ${context.photoDescription}`);

  return `Site-visit photo context:\n${lines.map((l) => `- ${l}`).join("\n")}\n\nInterpret the photo.`;
}
