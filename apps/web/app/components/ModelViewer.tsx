"use client";

import { Bounds, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { Suspense } from "react";

/** One design's GLB (the measured site plus the dwelling), framed to fit and
 * orbitable. Blender exports glTF y-up, as three.js expects. */
export function ModelViewer({ url }: { url: string }) {
  return (
    <div className="h-[480px] w-full overflow-hidden rounded border border-zinc-200 bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-900">
      <Canvas camera={{ position: [0, 40, 60], fov: 45 }}>
        <ambientLight intensity={0.6} />
        <directionalLight position={[30, 60, 20]} intensity={1.5} />
        <Suspense fallback={null}>
          <Bounds fit clip observe margin={1.1}>
            <Model url={url} />
          </Bounds>
        </Suspense>
        <OrbitControls makeDefault />
      </Canvas>
    </div>
  );
}

function Model({ url }: { url: string }) {
  const { scene } = useGLTF(url);
  return <primitive object={scene} />;
}
