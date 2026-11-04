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
  const [asked, setAsked] = useState(false);
  const { relief, problem } = useRelief(siteId, asked, pollMs);
  if (!asked)
    return (
      <button
        type="button"
        onClick={() => setAsked(true)}
        className="self-start rounded-xl bg-zinc-950/85 px-4 py-2 text-sm font-medium text-emerald-300 shadow-xl backdrop-blur hover:bg-zinc-900"
      >
        See it in 3D
      </button>
    );
  return <Shown relief={relief} problem={problem} />;
}

/** The best clip made so far, captioned, and each view that couldn't be. */
function Shown({
  relief,
  problem,
}: {
  relief: Relief | null;
  problem: string | null;
}) {
  const clip = relief && shownClip(relief);
  const flying = relief?.making === true && clip?.tier === "parallax";
  return (
    <figure className="rounded-2xl bg-zinc-950/85 p-3 shadow-2xl backdrop-blur">
      {clip ? (
        <ClipVideo clip={clip} />
      ) : (
        <div className="flex aspect-video items-center justify-center rounded-xl bg-zinc-900 text-sm text-zinc-400">
          {problem ? "Not shown" : "Lifting its aerial photo onto its LiDAR…"}
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
    </figure>
  );
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

/** Once `asked`, the relief started, then asked for every `pollMs` while
 * it's being made. */
function useRelief(siteId: string, asked: boolean, pollMs: number) {
  const [relief, setRelief] = useState<Relief | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    if (!asked) return;
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
        },
        (e: Error) => {
          if (gone) return;
          setProblem(e.message);
          if (passing(e)) timer = setTimeout(() => attempt(ask), pollMs);
        },
      );
    const follow = () => getRelief(siteId);
    attempt(() => startRelief(siteId));
    return () => {
      gone = true;
      clearTimeout(timer);
    };
  }, [siteId, asked, pollMs]);
  return { relief, problem };
}
