/**
 * Server-side interpretation: calls the Claude Messages API with the photo.
 *
 * Two entry points:
 *  - interpretImage(): plain async function, for any backend.
 *  - createInterpretHandler(): Web-standard (Request) => Response handler, which
 *    drops into Vercel/Netlify/Cloudflare functions, Hono, Next.js route
 *    handlers, or Express via toNodeMiddleware() in ./node.ts.
 *
 * Uses fetch directly (no SDK dependency). Requires Node 18+ or any runtime
 * with fetch.
 */
import { buildUserPrompt, OUTPUT_SCHEMA, SYSTEM_PROMPT, TOOL_NAME } from "../prompt";
import type {
  InterpretationContext,
  InterpretErrorBody,
  InterpretRequestBody,
  PhotoInterpretation,
} from "../types";

export const DEFAULT_MODEL = "claude-sonnet-5-5";
export const ANTHROPIC_URL = "https://api.anthropic.com/v1/messages";
/** API limit is 5 MB per image (decoded). */
export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;

const MEDIA_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "image/gif"]);

export interface InterpretServerOptions {
  apiKey: string;
  /** Defaults to DEFAULT_MODEL. */
  model?: string;
  maxTokens?: number;
  /** Injected for tests; defaults to global fetch. */
  fetchImpl?: typeof fetch;
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

/** Calls Claude with the image and returns a structured interpretation. */
export async function interpretImage(
  request: InterpretRequestBody,
  options: InterpretServerOptions,
): Promise<PhotoInterpretation> {
  const doFetch = options.fetchImpl ?? fetch;
  const model = options.model ?? DEFAULT_MODEL;

  const res = await doFetch(ANTHROPIC_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-api-key": options.apiKey,
      "anthropic-version": "2023-06-01",
    },
    body: JSON.stringify({
      model,
      max_tokens: options.maxTokens ?? 2048,
      system: SYSTEM_PROMPT,
      tools: [
        {
          name: TOOL_NAME,
          description: "Record the structured interpretation of the site-visit photo.",
          input_schema: OUTPUT_SCHEMA,
        },
      ],
      tool_choice: { type: "tool", name: TOOL_NAME },
      messages: [
        {
          role: "user",
          content: [
            {
              type: "image",
              source: { type: "base64", media_type: request.mediaType, data: request.image },
            },
            { type: "text", text: buildUserPrompt(request.context) },
          ],
        },
      ],
    }),
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new InterpretServerError(
      `Model API returned HTTP ${res.status}${detail ? `: ${detail.slice(0, 300)}` : ""}`,
      "upstream_error",
      502,
    );
  }

  const data = (await res.json()) as {
    content?: Array<{ type: string; name?: string; input?: unknown }>;
  };
  const toolUse = data.content?.find((c) => c.type === "tool_use" && c.name === TOOL_NAME);
  if (!toolUse || !toolUse.input || typeof toolUse.input !== "object") {
    throw new InterpretServerError("Model did not return a structured interpretation", "invalid_model_output", 502);
  }

  return normalizeInterpretation(toolUse.input as Record<string, unknown>, model);
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
    observations: arr(raw.observations),
    possibleDeficiencies: arr(raw.possibleDeficiencies),
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

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

/**
 * Web-standard handler. Mount at POST /api/interpret-photo.
 *
 *   export const POST = createInterpretHandler({ apiKey: process.env.ANTHROPIC_API_KEY! });
 */
export function createInterpretHandler(options: InterpretServerOptions) {
  return async function handle(req: Request): Promise<Response> {
    if (req.method !== "POST") {
      return json({ error: "Use POST", code: "bad_request" } satisfies InterpretErrorBody, 405);
    }
    if (!options.apiKey) {
      return json(
        { error: "ANTHROPIC_API_KEY is not set on the server", code: "server_misconfigured" } satisfies InterpretErrorBody,
        500,
      );
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
