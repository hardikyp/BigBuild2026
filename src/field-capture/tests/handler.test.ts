import { describe, expect, it, vi } from "vitest";
import {
  ANTHROPIC_URL,
  base64ByteLength,
  createInterpretHandler,
  MAX_IMAGE_BYTES,
  validateRequestBody,
} from "../server/handler";
import { buildUserPrompt, TOOL_NAME } from "../prompt";
import { fitWithin } from "../capture";
import { interpretPhoto, InterpretError } from "../interpret";

const TINY_JPEG_B64 = "/9j/4AAQSkZJRgABAQ=="; // not a real image; the API is mocked

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

function mockApi(response: unknown, status = 200) {
  return vi.fn(async (_url: string | URL | Request, _init?: RequestInit) =>
    new Response(JSON.stringify(response), { status, headers: { "content-type": "application/json" } }),
  );
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

describe("createInterpretHandler", () => {
  it("calls the API with image + context and returns a normalized result", async () => {
    const fetchImpl = mockApi({
      content: [{ type: "tool_use", name: TOOL_NAME, input: modelOutput }],
    });
    const handler = createInterpretHandler({ apiKey: "test-key", fetchImpl });
    const res = await handler(
      post({
        image: TINY_JPEG_B64,
        mediaType: "image/jpeg",
        context: { buildingType: "W1", checklistItem: { id: "W1-3", title: "Openings" } },
      }),
    );

    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.suggestedStatus).toBe("U");
    expect(body.model).toBe("claude-sonnet-5-5");
    expect(typeof body.createdAt).toBe("string");

    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe(ANTHROPIC_URL);
    const headers = init!.headers as Record<string, string>;
    expect(headers["x-api-key"]).toBe("test-key");
    const sent = JSON.parse(init!.body as string);
    expect(sent.tool_choice).toEqual({ type: "tool", name: TOOL_NAME });
    expect(sent.messages[0].content[0].source.data).toBe(TINY_JPEG_B64);
    expect(sent.messages[0].content[1].text).toContain("[W1-3] Openings");
  });

  it("returns 400 for invalid JSON", async () => {
    const handler = createInterpretHandler({ apiKey: "k", fetchImpl: mockApi({}) });
    const res = await handler(post("{not json"));
    expect(res.status).toBe(400);
    expect((await res.json()).code).toBe("bad_request");
  });

  it("returns 500 when the API key is missing", async () => {
    const handler = createInterpretHandler({ apiKey: "", fetchImpl: mockApi({}) });
    const res = await handler(post({ image: TINY_JPEG_B64, mediaType: "image/jpeg" }));
    expect(res.status).toBe(500);
    expect((await res.json()).code).toBe("server_misconfigured");
  });

  it("maps upstream errors to 502", async () => {
    const handler = createInterpretHandler({ apiKey: "k", fetchImpl: mockApi({ error: "overloaded" }, 529) });
    const res = await handler(post({ image: TINY_JPEG_B64, mediaType: "image/jpeg" }));
    expect(res.status).toBe(502);
    expect((await res.json()).code).toBe("upstream_error");
  });

  it("returns 502 when the model gives no tool call", async () => {
    const handler = createInterpretHandler({
      apiKey: "k",
      fetchImpl: mockApi({ content: [{ type: "text", text: "hello" }] }),
    });
    const res = await handler(post({ image: TINY_JPEG_B64, mediaType: "image/jpeg" }));
    expect(res.status).toBe(502);
    expect((await res.json()).code).toBe("invalid_model_output");
  });

  it("normalizes a bad suggestedStatus to null and fills missing arrays", async () => {
    const handler = createInterpretHandler({
      apiKey: "k",
      fetchImpl: mockApi({
        content: [{ type: "tool_use", name: TOOL_NAME, input: { summary: "x", suggestedStatus: "maybe" } }],
      }),
    });
    const body = await (await handler(post({ image: TINY_JPEG_B64, mediaType: "image/jpeg" }))).json();
    expect(body.suggestedStatus).toBeNull();
    expect(body.observations).toEqual([]);
    expect(body.imageQuality).toEqual({ usable: true, issues: [] });
  });
});

describe("client interpretPhoto", () => {
  it("round-trips through the handler", async () => {
    const handler = createInterpretHandler({
      apiKey: "k",
      fetchImpl: mockApi({ content: [{ type: "tool_use", name: TOOL_NAME, input: modelOutput }] }),
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
