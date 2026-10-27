/**
 * Field-capture module — browser entry point.
 *
 * Server code is NOT exported here (it must never ship to the browser).
 * Import it from "./server/handler" and "./server/node" in backend code only.
 */
export * from "./types";
export { preparePhoto, getLocation, blobToBase64, fitWithin, DEFAULT_MAX_EDGE } from "./capture";
export type { PreparePhotoOptions } from "./capture";
export { interpretPhoto, InterpretError, DEFAULT_ENDPOINT } from "./interpret";
export type { InterpretOptions } from "./interpret";
export { usePhotoInterpretation } from "./react/usePhotoInterpretation";
export type { CaptureStatus, UsePhotoInterpretationOptions } from "./react/usePhotoInterpretation";
export { PhotoCapture, InterpretationView } from "./react/PhotoCapture";
export type { PhotoCaptureProps } from "./react/PhotoCapture";
