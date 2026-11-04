"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

/** Which turn of `ms` the clock is in, moving on at each turn's end. Turning
 * with the clock, a list shown again carries on where it left off. */
export function useTurn(ms: number): number {
  const [turn, setTurn] = useState(() => Math.floor(Date.now() / ms));
  useEffect(() => {
    // Never the same turn again: a timer that fires a moment early would
    // otherwise stop the turning.
    const timer = setTimeout(
      () => setTurn((t) => Math.max(t + 1, Math.floor(Date.now() / ms))),
      ms - (Date.now() % ms),
    );
    return () => clearTimeout(timer);
  }, [turn, ms]);
  return turn;
}

const LESS_MOTION = "(prefers-reduced-motion: reduce)";

/** Whether the viewer asks for less motion (a video can't be stopped by
 * CSS, as an animation can). */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (changed) => {
      const query = window.matchMedia?.(LESS_MOTION);
      query?.addEventListener("change", changed);
      return () => query?.removeEventListener("change", changed);
    },
    () => window.matchMedia?.(LESS_MOTION).matches ?? false,
    () => false,
  );
}
