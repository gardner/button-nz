"use client";

import { useEffect, useState } from "react";

import { passing } from "@/lib/fields";
import {
  type Clip,
  type Relief,
  getRelief,
  shownClip,
  startRelief,
} from "@/lib/relief";

const TIER_NAMES: Record<string, string> = {
  depth: "depth map",
  parallax: "parallax view",
  flyover: "fly-over",
};

/** The site in 3D, when asked for: the parallax clip as soon as it's ready,
 * then the fly-over once Blender has rendered it. */
export function ReliefView({
  siteId,
  pollMs,
}: {
  siteId: string;
  pollMs: number;
}) {
  const [tries, setTries] = useState(0); // none until it's asked for
  const followed = useRelief(siteId, tries, pollMs);
  const again = () => setTries((t) => t + 1);
  if (tries === 0)
    return (
      <button type="button" onClick={again} className={BUTTON}>
        See it in 3D
      </button>
    );
  return <Shown {...followed} onRetry={again} />;
}

const BUTTON =
  "self-start rounded-xl bg-zinc-950/85 px-4 py-2 text-sm font-medium text-emerald-300 shadow-xl backdrop-blur hover:bg-zinc-900";

/** The best clip made so far, captioned, each view that couldn't be made,
 * and, once nothing is being made, a way to try those again. */
function Shown({
  relief,
  problem,
  following,
  onRetry,
}: {
  relief: Relief | null;
  problem: string | null;
  following: boolean;
  onRetry: () => void;
}) {
  const { clip, flying, retry } = shownState(relief, problem, following);
  return (
    <figure className="rounded-2xl bg-zinc-950/85 p-3 shadow-2xl backdrop-blur">
      {clip ? (
        <ClipVideo clip={clip} />
      ) : (
        <div className="flex aspect-video items-center justify-center rounded-xl bg-zinc-900 text-sm text-zinc-400">
          {following ? "Lifting its aerial photo onto its LiDAR…" : "Not shown"}
        </div>
      )}
      <figcaption className="mt-2 text-xs leading-relaxed text-zinc-300">
        Your site in 3D: its LINZ aerial photo on its own LiDAR heights; walls
        are not seen from above.
        {flying && (
          <span className="text-zinc-400">
            {" "}
            Blender is rendering the fly-over…
          </span>
        )}
      </figcaption>
      {relief && <Failures relief={relief} />}
      {problem && (
        <p role="alert" className="mt-1 text-xs text-red-300">
          Couldn&apos;t show it in 3D: {problem}
        </p>
      )}
      {retry && (
        <button type="button" onClick={onRetry} className={`mt-2 ${BUTTON}`}>
          Try again
        </button>
      )}
    </figure>
  );
}

/** The clip to play; whether the fly-over is still rendering behind the
 * parallax clip; and, once the relief is no longer followed, whether there's
 * anything to try again. */
function shownState(
  relief: Relief | null,
  problem: string | null,
  following: boolean,
) {
  const clip = relief && shownClip(relief);
  const failed = relief?.tiers.some((t) => t.status === "failed") ?? false;
  return {
    clip,
    flying: following && clip?.tier === "parallax",
    retry: !following && (failed || problem !== null),
  };
}

function ClipVideo({ clip }: { clip: Clip }) {
  return (
    <video
      key={clip.video} // a new clip starts from its first frame
      src={clip.video}
      poster={clip.still}
      autoPlay
      muted
      loop
      playsInline
      aria-label={`Your site, ${TIER_NAMES[clip.tier] ?? clip.tier}`}
      className="aspect-video w-full rounded-xl bg-zinc-900 object-contain"
    />
  );
}

/** Each view that couldn't be made, and why. */
function Failures({ relief }: { relief: Relief }) {
  return relief.tiers
    .filter((t) => t.status === "failed")
    .map((t) => (
      <p key={t.tier} className="mt-1 text-xs text-red-300">
        The {TIER_NAMES[t.tier] ?? t.tier} couldn&apos;t be made: {t.error}
      </p>
    ));
}

/** Each try (from 1), the relief started, then asked for every `pollMs` while
 * it's being made; `following` until it's made or asking has failed for good. */
function useRelief(siteId: string, tries: number, pollMs: number) {
  const [relief, setRelief] = useState<Relief | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [stopped, setStopped] = useState(0); // the last try no longer followed
  useEffect(() => {
    if (tries === 0) return;
    let gone = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // Each ask, and again if it fails in passing (the API restarting, say).
    const attempt = (ask: () => Promise<Relief>) =>
      ask().then(
        (found) => {
          if (gone) return;
          setRelief(found);
          setProblem(null);
          if (found.making) timer = setTimeout(() => attempt(follow), pollMs);
          else setStopped(tries);
        },
        (e: Error) => {
          if (gone) return;
          setProblem(e.message);
          if (passing(e)) timer = setTimeout(() => attempt(ask), pollMs);
          else setStopped(tries);
        },
      );
    const follow = () => getRelief(siteId);
    attempt(() => startRelief(siteId));
    return () => {
      gone = true;
      clearTimeout(timer);
    };
  }, [siteId, tries, pollMs]);
  return { relief, problem, following: stopped !== tries };
}
