# MORGAN Field Notes and Photo Capture

## Field-notes prototype

The standalone web app is a mobile-first site-visit log built on the field-capture module. It records building context, engineer-authored observations, photos, suggested follow-up evaluation, and engineer-entered code references. Use the existing MORGAN checklist workflow for formal Tier 1 item status.

Visit records and prepared photos are saved in the current browser with IndexedDB. They do not sync between devices or to a server. Use **Export backup** before clearing browser data; the versioned JSON backup includes photos and can be restored with **Import backup**.

Photo interpretation uses the GitHub Copilot SDK only when the engineer requests a review. The SDK runs server-side, sends the prepared image and visit context to a vision-capable Copilot model, and uses the signed-in GitHub user's Copilot access. Do not expose Copilot credentials to the browser. Only submit photos approved for external processing. Model output is advisory; the engineer must verify every observation, suggested follow-up, and code citation.

Each photo can include an engineer-entered description to direct the review. The description is saved with the observation and backup, then sent to Copilot as context alongside the image.

The demo also includes **Ongoing considerations**, a visit-wide list rebuilt from all saved photo interpretations. It groups descriptions that match after case/punctuation normalization, reports the number of supporting photos and their locations, and sorts by a transparent triage score:

```text
highest finding score × min(1.8, 1 + 0.2 × (supporting photos - 1))
finding score = severity weight × confidence weight
```

Severity weights are info 1, minor 2, moderate 4, severe 8; confidence weights are low 0.4, medium 0.7, high 1. Priority bands are urgent (6+), high (3+), monitor (1.5+), and routine (below 1.5). A suggested follow-up inherits the strongest finding's severity/confidence from its photo, or minor/low when that photo had no reported finding. Duplicate evidence within one photo counts once. Textually similar but differently worded conditions are not assumed to be the same. This score is a triage aid, not an engineering assessment.

## Run locally

Requires Node.js 20.19 or newer (or 22.12 or newer). From the repository root in PowerShell:

```powershell
Set-Location .\integration-staging\photo-analysis
npm ci
Copy-Item .env.example .env.local
npm run demo
```

Sign in to GitHub Copilot on the machine that runs the server. The SDK includes the Copilot runtime and can use stored Copilot CLI credentials or GitHub CLI authentication. If GitHub CLI (`gh`) is installed, sign in with `gh auth login --web` and verify with `gh auth status`; the account must have Copilot access. On Windows without administrator access, a portable GitHub CLI can be extracted to your user profile. For the portable copy used during this prototype:

```powershell
$ghDir = Join-Path $env:LOCALAPPDATA "Programs\GitHubCLI"
$env:PATH = "$ghDir;$env:PATH"
& (Join-Path $ghDir "gh.exe") auth login --web --hostname github.com --git-protocol https
& (Join-Path $ghDir "gh.exe") auth status
```

Complete sign-in in the GitHub browser page yourself; do not paste tokens into the app or repository. Start/restart the demo from the same PowerShell window so the Copilot SDK can find `gh`:

```powershell
Set-Location .\integration-staging\photo-analysis
npm run demo -- --host 127.0.0.1 --port 5187
```

No Anthropic API key is used. Optionally set `COPILOT_MODEL` in `.env.local` to override the default `gpt-5.4` model. The browser-only observation log, photo capture, and backup remain available without Copilot authentication. Run `npm test`, `npm run typecheck`, and `npm run build:demo` for validation.

For phone use over a trusted LAN, connect the phone and computer to the same Wi-Fi and open the LAN URL printed by Vite. The development server delegates AI requests using the machine's signed-in Copilot account, so do not expose it to untrusted networks or the public internet. A deployed site requires HTTPS and an authenticated application layer. The static build alone does not provide photo interpretation: deploy a server-side handler using `server/handler.ts` in an environment with the Copilot SDK runtime and Copilot authentication.

The photo-capture module can interpret an image in the context of a Tier 1 checklist item. The result is a structured interpretation: summary, observations, possible deficiencies, an **advisory** C / NC / N/A / U suggestion, and follow-up actions. The field-notes prototype instead requests a general advisory review without inferring a checklist status.

```
phone camera ──► preparePhoto() ──► interpretPhoto() ──► POST /api/interpret-photo ──► Copilot SDK
                 resize to 1568px     browser client       server handler
                 JPEG, orientation                         signed-in Copilot runtime
```

Open the LAN URL printed by Vite on a phone connected to the same Wi-Fi to use the device camera or photo picker. The field-notes prototype records the location-in-building as a manual note and does not collect GPS coordinates.

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

The Copilot runtime and authentication must stay on the server. Pick whichever backend the app uses:

```ts
// Next.js route handler / Vercel / Netlify / Cloudflare / Hono
import { createInterpretHandler } from "./field-capture/server/handler";
export const POST = createInterpretHandler({ model: process.env.COPILOT_MODEL });
```

```ts
// Express
import { createInterpretHandler } from "./field-capture/server/handler";
import { toNodeMiddleware } from "./field-capture/server/node";
app.post("/api/interpret-photo",
  toNodeMiddleware(createInterpretHandler({ model: process.env.COPILOT_MODEL })));
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
- **Structured output.** Copilot receives the strict JSON response schema (`prompt.ts`), and the server normalizes the result, so every field is always present.
- **No checklist text in code.** Checklist wording is passed in at runtime from the app's checklist data, so ASCE content is not embedded in this module.
- **Model:** defaults to `gpt-5.4`. Override with `COPILOT_MODEL` or the `model` option.
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
