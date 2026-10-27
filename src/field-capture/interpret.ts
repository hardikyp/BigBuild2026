/**
 * Browser-side client for the interpretation endpoint.
 *
 * The API key lives on the server; the browser only talks to your own
 * endpoint (see server/handler.ts).
 */
import { blobToBase64 } from "./capture";
import type {
  CapturedPhoto,
  InterpretationContext,
  InterpretErrorBody,
  InterpretRequestBody,
  PhotoInterpretation,
} from "./types";

export const DEFAULT_ENDPOINT = "/api/interpret-photo";

export interface InterpretOptions {
  endpoint?: string;
  signal?: AbortSignal;
  /** Injected for tests; defaults to global fetch. */
  fetchImpl?: typeof fetch;
}

export class InterpretError extends Error {
  constructor(
    message: string,
    public readonly code: InterpretErrorBody["code"] | "network_error",
    public readonly status?: number,
  ) {
    super(message);
    this.name = "InterpretError";
  }
}

/** Sends a captured photo plus context to the endpoint and returns the interpretation. */
export async function interpretPhoto(
  photo: Pick<CapturedPhoto, "blob" | "mediaType">,
  context: InterpretationContext = {},
  options: InterpretOptions = {},
): Promise<PhotoInterpretation> {
  const doFetch = options.fetchImpl ?? fetch;
  const body: InterpretRequestBody = {
    image: await blobToBase64(photo.blob),
    mediaType: photo.mediaType,
    context,
  };

  let res: Response;
  try {
    res = await doFetch(options.endpoint ?? DEFAULT_ENDPOINT, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: options.signal,
    });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") throw err;
    throw new InterpretError(
      "Could not reach the interpretation service. Check your connection; the photo is still saved.",
      "network_error",
    );
  }

  if (!res.ok) {
    let parsed: Partial<InterpretErrorBody> = {};
    try {
      parsed = await res.json();
    } catch {
      /* non-JSON error */
    }
    throw new InterpretError(
      parsed.error ?? `Interpretation failed (HTTP ${res.status})`,
      parsed.code ?? "upstream_error",
      res.status,
    );
  }

  return (await res.json()) as PhotoInterpretation;
}
