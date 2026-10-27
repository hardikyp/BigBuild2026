import type { MessageOptions, SessionConfig } from "@github/copilot-sdk";
import { describe, expect, it, vi } from "vitest";
import {
  base64ByteLength,
  createInterpretHandler,
  interpretImage,
  MAX_IMAGE_BYTES,
  type CopilotRuntime,
  type CopilotSession,
  validateRequestBody,
} from "../server/handler";
import { buildUserPrompt, OUTPUT_SCHEMA } from "../prompt";
import { fitWithin } from "../capture";
import { interpretPhoto, InterpretError } from "../interpret";

const TINY_JPEG_B64 = "/9j/4AAQSkZJRgABAQ=="; // not a real image; the Copilot runtime is mocked

const modelOutput = {
  summary: "Wood stud wall with diagonal crack in gypsum board near window corner.",
  components: [{ name: "stud wall", material: "wood", condition: "fair" }],
  observations: [{ description: "Diagonal crack at window corner", severity: "minor" }],
  possibleDeficiencies: [{ description: "Possible inadequate sheathing at opening", confidence: "low" }],
  suggestedStatus: "U",
  statusRationale: "Sheathing and nailing not visible.",
  followUp: ["Photograph sheathing nailing from attic side"],
  imageQuality: { usable: true, issues: [] },
};

function mockCopilot(content?: string) {
  const session: CopilotSession = {
    sendAndWait: vi.fn(async (_options: MessageOptions, _timeout?: number) =>
      content === undefined ? undefined : { data: { content } },
    ),
    disconnect: vi.fn(async () => {}),
  };
  const client: CopilotRuntime = {
    start: vi.fn(async () => {}),
    createSession: vi.fn(async (_config: SessionConfig) => session),
    stop: vi.fn(async () => {}),
  };
  return { client, session, clientFactory: () => client };
}

function post(body: unknown) {
  return new Request("http://localhost/api/interpret-photo", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: typeof body === "string" ? body : JSON.stringify(body),
  });
}

describe("validateRequestBody", () => {
  it("accepts a valid body", () => {
    const b = validateRequestBody({ image: TINY_JPEG_B64, mediaType: "image/jpeg" });
    expect(b.context).toEqual({});
  });
  it("rejects data: URLs", () => {
    expect(() => validateRequestBody({ image: "data:image/jpeg;base64,AAA", mediaType: "image/jpeg" })).toThrow(/data:/);
  });
  it("rejects bad media types", () => {
    expect(() => validateRequestBody({ image: "AAA", mediaType: "image/heic" })).toThrow(/mediaType/);
  });
  it("rejects oversized images with 413", () => {
    const big = "A".repeat(Math.ceil((MAX_IMAGE_BYTES * 4) / 3) + 8);
    try {
      validateRequestBody({ image: big, mediaType: "image/jpeg" });
      expect.unreachable();
    } catch (e) {
      expect((e as { status: number }).status).toBe(413);
    }
  });
});

describe("Copilot photo interpretation", () => {
  it("sends the image, context, and response schema through the Copilot SDK", async () => {
    const { client, session, clientFactory } = mockCopilot(JSON.stringify(modelOutput));
    const handler = createInterpretHandler({ clientFactory });
    const res = await handler(
      post({
        image: TINY_JPEG_B64,
        mediaType: "image/jpeg",
        context: {
          buildingType: "W1",
          checklistItem: { id: "W1-3", title: "Openings" },
          photoDescription: "Focus on the diagonal crack above the north window.",
        },
      }),
    );

    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.suggestedStatus).toBe("U");
    expect(body.model).toBe("gpt-5.4");
    expect(typeof body.createdAt).toBe("string");

    expect(client.start).toHaveBeenCalledOnce();
    expect(client.createSession).toHaveBeenCalledWith(
      expect.objectContaining({
        model: "gpt-5.4",
        systemMessage: expect.objectContaining({ mode: "replace" }),
      }),
    );
    const [sent, timeout] = vi.mocked(session.sendAndWait).mock.calls[0];
    expect(timeout).toBe(120_000);
    expect(sent.prompt).toContain("[W1-3] Openings");
    expect(sent.prompt).toContain("Engineer's photo description: Focus on the diagonal crack above the north window.");
    expect(sent.responseSchema).toEqual(OUTPUT_SCHEMA);
    expect(sent.attachments).toEqual([
      {
        type: "blob",
        data: TINY_JPEG_B64,
        mimeType: "image/jpeg",
        displayName: "site-condition-photo",
      },
    ]);
    expect(session.disconnect).toHaveBeenCalledOnce();
    expect(client.stop).toHaveBeenCalledOnce();
  });

  it("surfaces Copilot authentication/runtime errors", async () => {
    const { client, clientFactory } = mockCopilot();
    client.start = vi.fn(async () => {
      throw new Error("Copilot authentication required");
    });
    const response = await createInterpretHandler({ clientFactory })(
      post({ image: TINY_JPEG_B64, mediaType: "image/jpeg" }),
    );
    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({
      code: "upstream_error",
      error: expect.stringContaining("Copilot authentication required"),
    });
    expect(client.stop).toHaveBeenCalledOnce();
  });

  it("returns 502 when Copilot has no response", async () => {
    const { clientFactory } = mockCopilot();
    const response = await createInterpretHandler({ clientFactory })(
      post({ image: TINY_JPEG_B64, mediaType: "image/jpeg" }),
    );
    expect(response.status).toBe(502);
    expect((await response.json()).code).toBe("invalid_model_output");
  });

  it("returns 502 when Copilot output is not valid JSON", async () => {
    const { clientFactory } = mockCopilot("not JSON");
    await expect(
      interpretImage(
        { image: TINY_JPEG_B64, mediaType: "image/jpeg" },
        { clientFactory },
      ),
    ).rejects.toMatchObject({ code: "invalid_model_output", status: 502 });
  });

  it("normalizes a bad suggestedStatus and fills missing arrays", async () => {
    const { clientFactory } = mockCopilot(JSON.stringify({ summary: "x", suggestedStatus: "maybe" }));
    const response = await createInterpretHandler({ clientFactory })(
      post({ image: TINY_JPEG_B64, mediaType: "image/jpeg" }),
    );
    const body = await response.json();
    expect(body.suggestedStatus).toBeNull();
    expect(body.observations).toEqual([]);
    expect(body.imageQuality).toEqual({ usable: true, issues: [] });
  });

  it("returns 400 for invalid JSON", async () => {
    const response = await createInterpretHandler()(post("{not json"));
    expect(response.status).toBe(400);
    expect((await response.json()).code).toBe("bad_request");
  });
});

describe("client interpretPhoto", () => {
  it("round-trips through the handler", async () => {
    const handler = createInterpretHandler({
      clientFactory: mockCopilot(JSON.stringify(modelOutput)).clientFactory,
    });
    const clientFetch = (async (url: string | URL | Request, init?: RequestInit) =>
      handler(new Request(new URL(String(url), "http://localhost"), init))) as typeof fetch;

    const blob = new Blob([Uint8Array.from(atob(TINY_JPEG_B64), (c) => c.charCodeAt(0))], { type: "image/jpeg" });
    const result = await interpretPhoto({ blob, mediaType: "image/jpeg" }, { buildingType: "W1" }, { fetchImpl: clientFetch });
    expect(result.summary).toContain("Wood stud wall");
  });

  it("throws InterpretError with the server's code", async () => {
    const clientFetch = (async () =>
      new Response(JSON.stringify({ error: "too big", code: "image_too_large" }), { status: 413 })) as typeof fetch;
    const blob = new Blob([new Uint8Array([1, 2, 3])], { type: "image/jpeg" });
    await expect(interpretPhoto({ blob, mediaType: "image/jpeg" }, {}, { fetchImpl: clientFetch })).rejects.toMatchObject({
      name: "InterpretError",
      code: "image_too_large",
      status: 413,
    });
    expect(InterpretError).toBeDefined();
  });
});

describe("helpers", () => {
  it("buildUserPrompt asks for null status without a checklist item", () => {
    expect(buildUserPrompt({})).toMatch(/suggestedStatus to null/);
    expect(buildUserPrompt({ performanceLevel: "IO" })).toContain("Immediate Occupancy");
    expect(buildUserPrompt({ photoDescription: "Focus on the diagonal crack above the window." })).toContain(
      "Engineer's photo description: Focus on the diagonal crack above the window.",
    );
  });
  it("fitWithin downsizes but never upscales", () => {
    expect(fitWithin(4032, 3024, 1568)).toEqual({ width: 1568, height: 1176 });
    expect(fitWithin(800, 600, 1568)).toEqual({ width: 800, height: 600 });
  });
  it("base64ByteLength accounts for padding", () => {
    expect(base64ByteLength(btoa("abcd"))).toBe(4);
    expect(base64ByteLength(btoa("abcde"))).toBe(5);
  });
});
