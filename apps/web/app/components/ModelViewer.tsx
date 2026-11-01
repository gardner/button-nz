"use client";

import { Bounds, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Suspense, useEffect, useState } from "react";

/** One design's GLB (the measured site plus the dwelling), framed to fit and
 * orbitable. Blender exports glTF y-up, as three.js expects. ``data-model``
 * says whether this URL's model has loaded (the canvas shows before it has). */
export function ModelViewer({
  url,
  height = "h-[480px]",
}: {
  url: string;
  height?: string; // a Tailwind height class
}) {
  const [loaded, setLoaded] = useState<string | null>(null);
  return (
    <div
      data-model={loaded === url ? "loaded" : "loading"}
      className={`${height} w-full overflow-hidden rounded border border-zinc-200 bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900`}
    >
      <Canvas camera={{ position: [0, 40, 60], fov: 45 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[30, 60, 20]} intensity={1.5} />
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.1}>
            <Model url={url} onLoaded={setLoaded} />
          </Bounds>
        </Suspense>
        <OrbitControls makeDefault />
      </Canvas>
    </div>
  );
}

function Model({
  url,
  onLoaded,
}: {
  url: string;
  onLoaded: (url: string) => void;
}) {
  const { scene } = useGLTF(url); // suspends until the GLB has loaded
  useEffect(() => onLoaded(url), [url, onLoaded]);
  return <primitive object={scene} />;
}
