"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { Map as MapLibreMap } from "maplibre-gl";
import {
  Component,
  type ReactNode,
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import type { Bounds } from "@/lib/geo";

/** The aerial basemap, LINZ's, proxied by the API so its key stays there. */
export const AERIAL_TILES = "/api/tiles/aerial/{z}/{x}/{y}.webp";
/** Credits for what the map shows: LINZ's aerial basemap (Reefton's urban
 * photos are LINZ's, Aerial Surveys' and Buller District Council's), and the
 * sections, which the API serves from LINZ's NZ Primary Parcels (#86). */
export const ATTRIBUTION =
  "Aerial: Toitū Te Whenua LINZ basemap, CC BY 4.0 (Reefton: LINZ, Aerial Surveys, " +
  "Buller District Council) · Sections: LINZ NZ Primary Parcels, CC BY 4.0";

/** Room for the panel on the left of the map, so what is framed isn't under it. */
export function framing(right = 40): {
  top: number;
  bottom: number;
  left: number;
  right: number;
} {
  const width = typeof window === "undefined" ? 1440 : window.innerWidth;
  const left = width < 768 ? 24 : Math.min(500, width * 0.38);
  // The hero stands on the right from 1024 px; below that it is in the panel.
  return { top: 90, bottom: 40, left, right: width < 1024 ? 24 : right };
}

/** Reefton, the town the screen covers, framed. */
export const REEFTON: Bounds = [171.852, -42.125, 171.873, -42.107];

const WORKER = new URL(
  "maplibre-gl/dist/maplibre-gl-worker.mjs",
  import.meta.url,
).href;

const MapContext = createContext<MapLibreMap | null>(null);

/** The map the layers inside a BaseMap draw on, once it has loaded. */
export function useMap(): MapLibreMap | null {
  return useContext(MapContext);
}

/** A full-bleed aerial map, framed on `bounds`, with its children over it.
 * They always render; those that draw on the map (`useMap()`) wait for it to
 * load. MapLibre is loaded in the browser only, and needs WebGL: without it
 * the map says so, and everything over it still works. */
export function BaseMap({
  bounds,
  children,
}: {
  bounds: Bounds;
  children?: ReactNode;
}) {
  const [map, setMap] = useState<MapLibreMap | null>(null);
  return (
    <div className="relative h-full w-full">
      <MapBoundary>
        <MapCanvas bounds={bounds} onLoad={setMap} />
      </MapBoundary>
      <MapContext.Provider value={map}>{children}</MapContext.Provider>
    </div>
  );
}

function MapCanvas({
  bounds,
  onLoad,
}: {
  bounds: Bounds;
  onLoad: (map: MapLibreMap) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const loaded = useRef(onLoad);
  const [problem, setProblem] = useState<string | null>(null);
  const initial = useRef(bounds);
  useEffect(() => {
    let made: MapLibreMap | undefined;
    let cancelled = false;
    import("maplibre-gl").then(
      ({ Map, setWorkerUrl }) => {
        if (cancelled || !container.current) return;
        // The bundler serves MapLibre's worker as an asset: tell MapLibre where.
        setWorkerUrl(WORKER);
        try {
          made = new Map({
            container: container.current,
            style: {
              version: 8,
              sources: {
                aerial: {
                  type: "raster",
                  tiles: [AERIAL_TILES],
                  tileSize: 256,
                  maxzoom: 21,
                  attribution: ATTRIBUTION,
                },
              },
              layers: [{ id: "aerial", type: "raster", source: "aerial" }],
            },
            bounds: initial.current,
            fitBoundsOptions: { padding: framing() },
            maxZoom: 21,
          });
        } catch (error) {
          setProblem(error instanceof Error ? error.message : String(error));
          return;
        }
        made.on("load", () => made && loaded.current(made));
      },
      (error: Error) => setProblem(error.message),
    );
    return () => {
      cancelled = true;
      made?.remove();
    };
  }, []);
  return (
    <div className="absolute inset-0">
      <div ref={container} data-testid="map" className="h-full w-full" />
      {problem && <NoMap reason={problem} />}
    </div>
  );
}

function NoMap({ reason }: { reason: string }) {
  return (
    <div className="absolute inset-0 flex items-center justify-center bg-zinc-900 p-6 text-center text-zinc-200">
      <p>
        The map needs WebGL, which this browser can&apos;t give it ({reason}).
      </p>
    </div>
  );
}

/** Contains a map that throws while drawing, so the page around it stays. */
class MapBoundary extends Component<
  { children: ReactNode },
  { error: string | null }
> {
  state = { error: null as string | null };

  static getDerivedStateFromError(error: Error) {
    return { error: error.message };
  }

  render() {
    return this.state.error ? (
      <NoMap reason={this.state.error} />
    ) : (
      this.props.children
    );
  }
}
