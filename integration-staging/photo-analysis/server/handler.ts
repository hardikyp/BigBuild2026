/**
 * Server-side photo interpretation through the GitHub Copilot SDK.
 *
 * The SDK starts the Copilot runtime and uses the signed-in GitHub user's
 * Copilot access. Keep this handler on the server; never bundle the SDK into
 * browser code.
 */
import { CopilotClient, type MessageOptions, type SessionConfig } from "@github/copilot-sdk";
import { buildUserPrompt, OUTPUT_SCHEMA, SYSTEM_PROMPT } from "../prompt";
import type {
  InterpretationContext,
  InterpretErrorBody,
  InterpretRequestBody,
  PhotoInterpretation,
} from "../types";

export const DEFAULT_MODEL = "gpt-5.4";
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const RESPONSE_TIMEOUT_MS = 120_000;

const MEDIA_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);

export interface CopilotSession {
  sendAndWait(
    options: MessageOptions,
    timeout?: number,
  ): Promise<{ data: { content: string } } | undefined>;
  disconnect(): Promise<void>;
}

export interface CopilotRuntime {
  start(): Promise<void>;
  createSession(config: SessionConfig): Promise<CopilotSession>;
  stop(): Promise<void>;
}

export interface InterpretServerOptions {
  /** Defaults to DEFAULT_MODEL. */
  model?: string;
  /** Injected for tests; defaults to a new Copilot SDK client. */
  clientFactory?: () => CopilotRuntime;
}

export class InterpretServerError extends Error {
  constructor(
    message: string,
    public readonly code: InterpretErrorBody["code"],
    public readonly status: number,
  ) {
    super(message);
    this.name = "InterpretServerError";
  }
}

/** Approximate decoded size of a base64 string. */
export function base64ByteLength(b64: string): number {
  const padding = b64.endsWith("==") ? 2 : b64.endsWith("=") ? 1 : 0;
  return Math.floor((b64.length * 3) / 4) - padding;
}

/** Validates an untrusted request body. Throws InterpretServerError(400/413). */
export function validateRequestBody(body: unknown): InterpretRequestBody {
  if (!body || typeof body !== "object") {
    throw new InterpretServerError("Body must be a JSON object", "bad_request", 400);
  }
  const b = body as Record<string, unknown>;
  if (typeof b.image !== "string" || b.image.length === 0) {
    throw new InterpretServerError("'image' must be a non-empty base64 string", "bad_request", 400);
  }
  if (b.image.startsWith("data:")) {
    throw new InterpretServerError("'image' must be raw base64, without a data: prefix", "bad_request", 400);
  }
  if (typeof b.mediaType !== "string" || !MEDIA_TYPES.has(b.mediaType)) {
    throw new InterpretServerError(
      "'mediaType' must be image/jpeg, image/png, image/webp or image/gif",
      "bad_request",
      400,
    );
  }
  if (base64ByteLength(b.image) > MAX_IMAGE_BYTES) {
    throw new InterpretServerError(
      "Image exceeds 5 MB. Resize it before sending (preparePhoto does this).",
      "image_too_large",
      413,
    );
  }
  if (b.context !== undefined && (typeof b.context !== "object" || b.context === null)) {
    throw new InterpretServerError("'context' must be an object", "bad_request", 400);
  }
  return {
    image: b.image,
    mediaType: b.mediaType as InterpretRequestBody["mediaType"],
    context: (b.context as InterpretationContext) ?? {},
  };
}

/** Sends the photo to GitHub Copilot and returns its structured interpretation. */
export async function interpretImage(
  request: InterpretRequestBody,
  options: InterpretServerOptions = {},
): Promise<PhotoInterpretation> {
  const client =
    options.clientFactory?.() ??
    new CopilotClient({ useLoggedInUser: true });
  let session: CopilotSession | undefined;

  try {
    await client.start();
    session = await client.createSession({
      model: options.model ?? DEFAULT_MODEL,
      systemMessage: { mode: "replace", content: SYSTEM_PROMPT },
    });

    const response = await session.sendAndWait(
      {
        prompt: buildUserPrompt(request.context),
        responseSchema: OUTPUT_SCHEMA,
        attachments: [
          {
            type: "blob",
            data: request.image,
            mimeType: request.mediaType,
            displayName: "site-condition-photo",
          },
        ],
      },
      RESPONSE_TIMEOUT_MS,
    );
    if (!response?.data.content) {
      throw new InterpretServerError(
        "Copilot did not return a photo interpretation",
        "invalid_model_output",
        502,
      );
    }

    let output: unknown;
    try {
      output = JSON.parse(response.data.content);
    } catch {
      throw new InterpretServerError(
        "Copilot returned a response that was not valid structured JSON",
        "invalid_model_output",
        502,
      );
    }
    if (!output || typeof output !== "object" || Array.isArray(output)) {
      throw new InterpretServerError(
        "Copilot returned an invalid structured interpretation",
        "invalid_model_output",
        502,
      );
    }
    return normalizeInterpretation(output as Record<string, unknown>, options.model ?? DEFAULT_MODEL);
  } catch (error) {
    if (error instanceof InterpretServerError) throw error;
    const detail = error instanceof Error ? `: ${error.message}` : "";
    throw new InterpretServerError(
      `Copilot photo interpretation failed${detail}`,
      "upstream_error",
      502,
    );
  } finally {
    try {
      await session?.disconnect();
    } finally {
      await client.stop();
    }
  }
}

/** Fills defaults so downstream code can rely on every field being present. */
export function normalizeInterpretation(
  raw: Record<string, unknown>,
  model: string,
): PhotoInterpretation {
  const arr = <T>(v: unknown): T[] => (Array.isArray(v) ? (v as T[]) : []);
  const quality = (raw.imageQuality ?? {}) as Partial<PhotoInterpretation["imageQuality"]>;
  const status = raw.suggestedStatus;
  return {
    summary: typeof raw.summary === "string" ? raw.summary : "",
    components: arr(raw.components),
    observations: arr<Record<string, unknown>>(raw.observations).flatMap((observation) =>
      typeof observation.description === "string" && isSeverity(observation.severity)
        ? [{
            description: observation.description,
            severity: observation.severity,
            confidence: isConfidence(observation.confidence) ? observation.confidence : "medium",
          }]
        : [],
    ),
    possibleDeficiencies: arr<Record<string, unknown>>(raw.possibleDeficiencies).flatMap((deficiency) =>
      typeof deficiency.description === "string"
        ? [{
            description: deficiency.description,
            relatedChecklistItemId:
              typeof deficiency.relatedChecklistItemId === "string"
                ? deficiency.relatedChecklistItemId
                : undefined,
            severity: isSeverity(deficiency.severity) ? deficiency.severity : "moderate",
            confidence: isConfidence(deficiency.confidence) ? deficiency.confidence : "low",
          }]
        : [],
    ),
    suggestedStatus:
      status === "C" || status === "NC" || status === "N/A" || status === "U" ? status : null,
    statusRationale: typeof raw.statusRationale === "string" ? raw.statusRationale : undefined,
    followUp: arr<string>(raw.followUp).filter((s) => typeof s === "string"),
    imageQuality: {
      usable: quality.usable !== false,
      issues: arr<string>(quality.issues),
    },
    model,
    createdAt: new Date().toISOString(),
  };
}

function isSeverity(value: unknown): value is PhotoInterpretation["observations"][number]["severity"] {
  return value === "info" || value === "minor" || value === "moderate" || value === "severe";
}

function isConfidence(value: unknown): value is PhotoInterpretation["observations"][number]["confidence"] {
  return value === "low" || value === "medium" || value === "high";
}

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/**
 * Web-standard handler. Mount at POST /api/interpret-photo.
 *
 *   export const POST = createInterpretHandler();
 */
export function createInterpretHandler(options: InterpretServerOptions = {}) {
  return async function handle(req: Request): Promise<Response> {
    if (req.method !== "POST") {
      return json({ error: "Use POST", code: "bad_request" } satisfies InterpretErrorBody, 405);
    }
    try {
      let body: unknown;
      try {
        body = await req.json();
      } catch {
        throw new InterpretServerError("Body must be valid JSON", "bad_request", 400);
      }
      const result = await interpretImage(validateRequestBody(body), options);
      return json(result, 200);
    } catch (err) {
      if (err instanceof InterpretServerError) {
        return json({ error: err.message, code: err.code } satisfies InterpretErrorBody, err.status);
      }
      return json(
        { error: "Unexpected error interpreting photo", code: "upstream_error" } satisfies InterpretErrorBody,
        500,
      );
    }
  };
}
