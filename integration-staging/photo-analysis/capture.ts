/**
 * Browser-side photo preparation.
 *
 * Phone photos are often 4000+ px and 3-8 MB. We downscale to a long edge of
 * 1568 px (the size vision models handle without further downscaling), apply
 * EXIF orientation, and re-encode as JPEG. This also strips most metadata.
 */
import type { CapturedPhoto, GeoLocation } from "./types";

export interface PreparePhotoOptions {
  /** Longest edge in pixels. Default 1568. */
  maxEdge?: number;
  /** JPEG quality, 0-1. Default 0.85. */
  quality?: number;
  /** Try to attach device location. Default false. */
  withLocation?: boolean;
}

export const DEFAULT_MAX_EDGE = 1568;

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `photo-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/** Target size that fits within maxEdge while keeping aspect ratio. Never upscales. */
export function fitWithin(width: number, height: number, maxEdge: number) {
  const scale = Math.min(1, maxEdge / Math.max(width, height));
  return { width: Math.round(width * scale), height: Math.round(height * scale) };
}

/** Resolves to the device location, or undefined if unavailable/denied (never rejects). */
export function getLocation(timeoutMs = 5000): Promise<GeoLocation | undefined> {
  if (typeof navigator === "undefined" || !navigator.geolocation) return Promise.resolve(undefined);
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracyM: pos.coords.accuracy,
        }),
      () => resolve(undefined),
      { enableHighAccuracy: true, timeout: timeoutMs, maximumAge: 60_000 },
    );
  });
}

/** Turns a File/Blob from a camera or file picker into a CapturedPhoto. */
export async function preparePhoto(
  file: Blob,
  options: PreparePhotoOptions = {},
): Promise<CapturedPhoto> {
  const maxEdge = options.maxEdge ?? DEFAULT_MAX_EDGE;
  const quality = options.quality ?? 0.85;

  const locationPromise = options.withLocation ? getLocation() : Promise.resolve(undefined);

  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const { width, height } = fitWithin(bitmap.width, bitmap.height, maxEdge);

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D context unavailable");
  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();

  const blob = await new Promise<Blob>((resolve, reject) =>
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("Image encoding failed"))),
      "image/jpeg",
      quality,
    ),
  );

  return {
    id: newId(),
    blob,
    mediaType: "image/jpeg",
    width,
    height,
    takenAt: new Date().toISOString(),
    location: await locationPromise,
    originalName: file instanceof File ? file.name : undefined,
  };
}

/** Base64-encodes a Blob (no data: prefix). */
export async function blobToBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}
