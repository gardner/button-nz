/** A stand-in for MapLibre's Map in tests (jsdom has no WebGL): it records
 * what the app asks of it and lets a test click a layer's feature. */

type Handler = (event: unknown) => void;

export class FakeMap {
  static last: FakeMap | null = null;
  sources = new Map<
    string,
    { data?: unknown; setData: (d: unknown) => void; [key: string]: unknown }
  >();
  layers = new Map<string, object>();
  fitted: unknown[] = [];
  pitch = 0;
  bearing = 0;
  terrain: object | null = null; // never set: the 3D view has no terrain
  private handlers: { type: string; layer?: string; handler: Handler }[] = [];

  constructor(public options: object) {
    FakeMap.last = this;
    queueMicrotask(() => this.fire("load"));
  }

  on(type: string, layerOrHandler: string | Handler, handler?: Handler) {
    if (typeof layerOrHandler === "function")
      this.handlers.push({ type, handler: layerOrHandler });
    else if (handler)
      this.handlers.push({ type, layer: layerOrHandler, handler });
    return this;
  }

  off(type: string, layerOrHandler: string | Handler, handler?: Handler) {
    const [layer, fn] =
      typeof layerOrHandler === "function"
        ? [undefined, layerOrHandler]
        : [layerOrHandler, handler];
    this.handlers = this.handlers.filter(
      (h) => !(h.type === type && h.layer === layer && h.handler === fn),
    );
    return this;
  }

  once(type: string, handler: Handler) {
    const one: Handler = (event) => {
      this.off(type, one);
      handler(event);
    };
    return this.on(type, one);
  }

  fire(type: string, layer?: string, event: unknown = {}) {
    for (const h of this.handlers)
      if (h.type === type && h.layer === layer) h.handler(event);
  }

  /** A click on feature `index` of layer `layer`. */
  click(layer: string, index: number) {
    this.fire("click", layer, {
      features: [{ properties: { index } }],
      lngLat: { lng: 0, lat: 0 },
    });
  }

  addSource(id: string, source: { data?: unknown }) {
    const entry = {
      ...source,
      setData: (d: unknown) => (entry.data = d),
    };
    this.sources.set(id, entry);
  }
  getSource(id: string) {
    if (!this.style) throw new TypeError("the map has been removed");
    return this.sources.get(id);
  }
  removeSource(id: string) {
    this.sources.delete(id);
  }
  /** The layers' ids, bottom first, as MapLibre stacks them. */
  order: string[] = [];
  addLayer(layer: { id: string }) {
    this.layers.set(layer.id, layer);
    this.order.push(layer.id);
  }
  getLayer(id: string) {
    if (!this.style) throw new TypeError("the map has been removed");
    return this.layers.get(id);
  }
  removeLayer(id: string) {
    this.layers.delete(id);
    this.order = this.order.filter((layer) => layer !== id);
  }
  setPaintProperty(layer: string, key: string, value: unknown) {
    const found = this.layers.get(layer) as
      { paint?: Record<string, unknown> } | undefined;
    if (found) found.paint = { ...found.paint, [key]: value };
  }
  getCanvas() {
    return { style: { cursor: "" } };
  }
  fitOptions: unknown[] = [];
  /** The fits that landed, not stopped by a later move. */
  landed: unknown[] = [];
  zoom = 14;
  private moving: object | null = null;
  /** As MapLibre's camera: a move lands a moment later, unless another move
   * (an ease or a fit) starts first and stops it where it is. */
  private move(
    target: { pitch?: number; bearing?: number; zoom?: number },
    landed?: () => void,
  ) {
    const move = { ...target };
    this.moving = move;
    queueMicrotask(() => {
      if (this.moving !== move) return; // stopped by a later move
      this.moving = null;
      if (move.pitch !== undefined) this.pitch = move.pitch;
      if (move.bearing !== undefined) this.bearing = move.bearing;
      if (move.zoom !== undefined) this.zoom = move.zoom;
      landed?.();
      this.fire("moveend");
    });
  }
  fitBounds(bounds: unknown, options?: { pitch?: number; bearing?: number }) {
    this.fitted.push(bounds);
    this.fitOptions.push(options);
    this.move({ ...options, zoom: 14 }, () => this.landed.push(bounds));
  }
  easeTo(options: { pitch?: number; bearing?: number; zoom?: number }) {
    this.move(options);
  }
  /** Jumps, at once: what each jump asked for. */
  jumps: unknown[] = [];
  jumpTo(options: { zoom?: number; pitch?: number }) {
    this.jumps.push(options);
    this.moving = null; // as MapLibre's: a jump stops a move on its way
    if (options.zoom !== undefined) this.zoom = options.zoom;
    if (options.pitch !== undefined) this.pitch = options.pitch;
    queueMicrotask(() => this.fire("moveend"));
  }
  getPitch() {
    return this.pitch;
  }
  getZoom() {
    return this.zoom;
  }
  getBearing() {
    return this.bearing;
  }
  setBearing(bearing: number) {
    this.bearing = bearing;
  }
  cameraForBounds() {
    return { center: [171.862, -42.1159], zoom: 19.5 };
  }
  /** As MapLibre's: removing it drops its style, so later calls throw. */
  style: object | undefined = {};
  remove() {
    this.style = undefined;
  }
}

/** A stand-in for MapLibre's Marker: its element goes into the document. */
export class FakeMarker {
  constructor(public options: { element: HTMLElement }) {}
  setLngLat() {
    return this;
  }
  addTo() {
    document.body.appendChild(this.options.element);
    return this;
  }
  remove() {
    this.options.element.remove();
  }
}
