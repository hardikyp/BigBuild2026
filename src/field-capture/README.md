# Field capture (workstream 5)

The user takes a photo on site, and an LLM interprets it in the context of the building and the Tier 1 checklist item being evaluated. The result is a structured interpretation: summary, observations, possible deficiencies, an **advisory** C / NC / N/A / U suggestion, and follow-up actions.

```
phone camera ──► preparePhoto() ──► interpretPhoto() ──► POST /api/interpret-photo ──► Claude API
                 resize to 1568px     browser client       server handler (holds API key)
                 JPEG, orientation                         structured output via tool call
```

## Try it

```bash
cd src/field-capture
npm install
cp .env.example .env.local     # add your ANTHROPIC_API_KEY
npm run demo                   # opens on http://localhost:5173, plus a LAN URL for your phone
npm test
```

Open the LAN URL on your phone, which must be on the same Wi-Fi, to use the real camera. Location tagging only works over HTTPS or localhost, so over a LAN IP the photo is simply saved without a location.

## Integrating into the main app

### 1. Browser: drop in the component

```tsx
import { PhotoCapture } from "./field-capture";

<PhotoCapture
  context={{
    buildingType: visit.buildingType,          // "W1", "C2", ...
    performanceLevel: visit.performanceLevel,  // "CP" | "IO"
    seismicity: visit.seismicity,
    checklistItem: { id: item.id, title: item.title, text: item.text },
    locationInBuilding: "Level 2, grid C/4",
  }}
  prepare={{ withLocation: true }}
  onCaptured={(photo) => storage.savePhoto(visit.id, item.id, photo)}            // workstream 6
  onInterpreted={(photo, result) => storage.saveInterpretation(photo.id, result)}
  onAcceptStatus={(status) => checklist.setStatus(item.id, status)}               // workstream 4
/>
```

- `onCaptured` fires **before** interpretation. Save the photo there, so it is kept even if the user is offline or the LLM call fails.
- Want your own UI? Use the headless `usePhotoInterpretation()` hook, or the plain functions `preparePhoto()` and `interpretPhoto()`.
- To re-interpret a stored photo later (e.g. after regaining signal), call `interpretPhoto(storedPhoto, context)`.

### 2. Server: mount the endpoint

The API key must stay on the server. Pick whichever backend the app uses:

```ts
// Next.js route handler / Vercel / Netlify / Cloudflare / Hono
import { createInterpretHandler } from "./field-capture/server/handler";
export const POST = createInterpretHandler({ apiKey: process.env.ANTHROPIC_API_KEY! });
```

```ts
// Express
import { createInterpretHandler } from "./field-capture/server/handler";
import { toNodeMiddleware } from "./field-capture/server/node";
app.post("/api/interpret-photo",
  toNodeMiddleware(createInterpretHandler({ apiKey: process.env.ANTHROPIC_API_KEY! })));
// Don't put express.json() in front of this route.
```

If you mount it somewhere other than `/api/interpret-photo`, pass `interpret={{ endpoint: "/your/path" }}` to the component.

### 3. Don't import server code into the browser

`index.ts` exports only browser code. Server code lives in `server/` and is imported by path.

## Contract (`types.ts`)

Other workstreams should depend only on these types:

| Type | Used by |
|---|---|
| `CapturedPhoto`: blob, size, timestamp, location | Storage (6), reports (7) |
| `InterpretationContext`: building type, CP/IO, checklist item, notes | Checklist UI (4), project setup (3) |
| `PhotoInterpretation`: summary, observations, deficiencies, suggested status, follow-up | Checklist UI (4), reports (7) |
| `ChecklistStatus`: `"C" \| "NC" \| "N/A" \| "U"` | Everyone |

Changes to these types go through the integrator.

## Design notes

- **Advisory only.** The suggested status is shown as a suggestion, and the engineer must tap "Use this status" to apply it. The prompt tells the model to default to U when a photo can't settle an item, which is the usual case.
- **Structured output.** The model is forced to answer through a tool call with a JSON schema (`prompt.ts`), and the server normalizes the result, so every field is always present.
- **No checklist text in code.** Checklist wording is passed in at runtime from the app's checklist data, so ASCE content is not embedded in this module.
- **Model:** defaults to `claude-sonnet-5-5`. Override with `ANTHROPIC_MODEL` or the `model` option.
- **Image prep:** 1568 px long edge, JPEG q0.85, EXIF orientation applied, metadata stripped. A typical phone photo goes from 3–8 MB to a few hundred KB.
- **Errors:** the client throws `InterpretError` with a `code` (`network_error`, `bad_request`, `image_too_large`, `upstream_error`, `invalid_model_output`, `server_misconfigured`).

## Files

```
types.ts                  shared contract
prompt.ts                 system prompt, output schema, context → prompt text
capture.ts                preparePhoto, getLocation, blobToBase64 (browser)
interpret.ts              interpretPhoto client (browser)
react/                    usePhotoInterpretation hook, <PhotoCapture>, <InterpretationView>
server/handler.ts         interpretImage, createInterpretHandler (server)
server/node.ts            toNodeMiddleware adapter for Express/Connect
demo/                     standalone demo page (npm run demo)
tests/handler.test.ts     validation, API call shape, normalization, error mapping, client round-trip
```

When the main app's skeleton lands, its root `package.json` takes over the dependencies, and this folder's `package.json` can be deleted.

## Possible next steps

- Offline queue: store photos taken offline and interpret them when the connection is back (with workstream 6).
- Multiple photos per interpretation, e.g. a wide shot plus a close-up.
- Markup: draw on the photo before sending.
- Per-building-type prompt hints, e.g. what to look for in URM vs. tilt-up.
