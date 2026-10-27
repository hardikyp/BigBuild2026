/**
 * Adapter: run the Web-standard handler as Node/Express/Connect middleware.
 *
 *   import express from "express";
 *   import { createInterpretHandler } from "./field-capture/server/handler";
 *   import { toNodeMiddleware } from "./field-capture/server/node";
 *
 *   app.post("/api/interpret-photo",
 *     toNodeMiddleware(createInterpretHandler({ model: process.env.COPILOT_MODEL })));
 *
 * Do NOT put express.json() in front of this route; it reads the raw body itself.
 */
import type { IncomingMessage, ServerResponse } from "node:http";

/** Largest request body accepted (base64 inflates a 5 MB image to ~6.7 MB). */
const MAX_BODY_BYTES = 8 * 1024 * 1024;

export function toNodeMiddleware(handler: (req: Request) => Promise<Response>) {
  return async (req: IncomingMessage, res: ServerResponse): Promise<void> => {
    const chunks: Buffer[] = [];
    let size = 0;
    for await (const chunk of req) {
      size += (chunk as Buffer).length;
      if (size > MAX_BODY_BYTES) {
        res.statusCode = 413;
        res.setHeader("content-type", "application/json");
        res.end(JSON.stringify({ error: "Request body too large", code: "image_too_large" }));
        return;
      }
      chunks.push(chunk as Buffer);
    }

    const url = `http://${req.headers.host ?? "localhost"}${req.url ?? "/"}`;
    const headers = new Headers();
    for (const [k, v] of Object.entries(req.headers)) {
      if (typeof v === "string") headers.set(k, v);
    }
    const method = req.method ?? "GET";
    const request = new Request(url, {
      method,
      headers,
      body: method === "GET" || method === "HEAD" ? undefined : Buffer.concat(chunks),
    });

    const response = await handler(request);
    res.statusCode = response.status;
    response.headers.forEach((value, key) => res.setHeader(key, value));
    res.end(Buffer.from(await response.arrayBuffer()));
  };
}
