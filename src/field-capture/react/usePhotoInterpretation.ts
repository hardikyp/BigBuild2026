/**
 * Headless React hook: capture -> prepare -> interpret, with state.
 * Use this if you want your own UI; use <PhotoCapture> for the default one.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { preparePhoto, type PreparePhotoOptions } from "../capture";
import { interpretPhoto, type InterpretOptions } from "../interpret";
import type { CapturedPhoto, InterpretationContext, PhotoInterpretation } from "../types";

export type CaptureStatus = "idle" | "preparing" | "interpreting" | "done" | "error";

export interface UsePhotoInterpretationOptions {
  context?: InterpretationContext;
  prepare?: PreparePhotoOptions;
  interpret?: Omit<InterpretOptions, "signal">;
  /** Interpret right after capture. Default true. */
  autoInterpret?: boolean;
  /** Fires as soon as the photo is prepared, before interpretation. Save it here. */
  onCaptured?: (photo: CapturedPhoto) => void;
  onInterpreted?: (photo: CapturedPhoto, result: PhotoInterpretation) => void;
  onError?: (error: Error) => void;
}

export function usePhotoInterpretation(options: UsePhotoInterpretationOptions = {}) {
  const [status, setStatus] = useState<CaptureStatus>("idle");
  const [photo, setPhoto] = useState<CapturedPhoto | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [result, setResult] = useState<PhotoInterpretation | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Keep latest options without re-creating callbacks.
  const optsRef = useRef(options);
  optsRef.current = options;

  useEffect(() => () => abortRef.current?.abort(), []);
  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const fail = useCallback((err: unknown) => {
    if ((err as Error)?.name === "AbortError") return;
    const e = err instanceof Error ? err : new Error(String(err));
    setError(e);
    setStatus("error");
    optsRef.current.onError?.(e);
  }, []);

  const interpret = useCallback(
    async (target?: CapturedPhoto) => {
      const p = target ?? photo;
      if (!p) return;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setStatus("interpreting");
      setError(null);
      try {
        const r = await interpretPhoto(p, optsRef.current.context, {
          ...optsRef.current.interpret,
          signal: controller.signal,
        });
        setResult(r);
        setStatus("done");
        optsRef.current.onInterpreted?.(p, r);
      } catch (err) {
        fail(err);
      }
    },
    [photo, fail],
  );

  const capture = useCallback(
    async (file: Blob) => {
      abortRef.current?.abort();
      setStatus("preparing");
      setError(null);
      setResult(null);
      try {
        const p = await preparePhoto(file, optsRef.current.prepare);
        setPhoto(p);
        setPreviewUrl(URL.createObjectURL(p.blob));
        optsRef.current.onCaptured?.(p);
        if (optsRef.current.autoInterpret !== false) {
          await interpret(p);
        } else {
          setStatus("idle");
        }
      } catch (err) {
        fail(err);
      }
    },
    [interpret, fail],
  );

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setPhoto(null);
    setPreviewUrl(null);
    setResult(null);
    setError(null);
    setStatus("idle");
  }, []);

  return { status, photo, previewUrl, result, error, capture, interpret, reset };
}
