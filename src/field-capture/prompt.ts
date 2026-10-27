/**
 * Prompt and output schema for photo interpretation.
 * Server-side only in practice, but has no Node dependencies.
 */
import type { InterpretationContext } from "./types";

export const TOOL_NAME = "record_photo_interpretation";

export const SYSTEM_PROMPT = `You are assisting a licensed structural engineer during a seismic site visit of an existing building, using the ASCE 41 Tier 1 screening approach.

You will be shown one photo taken on site, plus whatever context the engineer has given (building type, performance level, the checklist item being evaluated, notes).

Your job:
- Describe what is actually visible. Identify structural and nonstructural components, materials and condition.
- Note observations relevant to seismic performance: damage, cracking, corrosion, deterioration, missing or inadequate connections, irregularities, pounding risk, unbraced elements, and similar.
- If a checklist item is given, say whether the photo supports Compliant (C), Noncompliant (NC), Not Applicable (N/A) or Unknown (U), and why. Use U whenever the photo alone cannot settle it. Most items need measurements, drawings or calculations, so U is often correct.
- Suggest concrete follow-up: what else to photograph, measure, or check in drawings.

Rules:
- Only report what the image shows. Do not invent dimensions, details or hidden conditions. Say when something is obscured or ambiguous.
- Be specific and terse, in the voice of a field note.
- Your output is advisory. The engineer makes every determination.
- Always respond by calling the ${TOOL_NAME} tool.`;

/** JSON Schema for the tool input; mirrors PhotoInterpretation minus model/createdAt. */
export const OUTPUT_SCHEMA = {
  type: "object",
  properties: {
    summary: {
      type: "string",
      description: "One or two sentences describing what the photo shows.",
    },
    components: {
      type: "array",
      items: {
        type: "object",
        properties: {
          name: { type: "string" },
          material: { type: "string" },
          condition: { type: "string" },
        },
        required: ["name"],
      },
    },
    observations: {
      type: "array",
      items: {
        type: "object",
        properties: {
          description: { type: "string" },
          severity: { type: "string", enum: ["info", "minor", "moderate", "severe"] },
        },
        required: ["description", "severity"],
      },
    },
    possibleDeficiencies: {
      type: "array",
      items: {
        type: "object",
        properties: {
          description: { type: "string" },
          relatedChecklistItemId: { type: "string" },
          confidence: { type: "string", enum: ["low", "medium", "high"] },
        },
        required: ["description", "confidence"],
      },
    },
    suggestedStatus: {
      type: ["string", "null"],
      enum: ["C", "NC", "N/A", "U", null],
      description: "Null if no checklist item was given.",
    },
    statusRationale: { type: "string" },
    followUp: { type: "array", items: { type: "string" } },
    imageQuality: {
      type: "object",
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

  return `Site-visit photo context:\n${lines.map((l) => `- ${l}`).join("\n")}\n\nInterpret the photo.`;
}
