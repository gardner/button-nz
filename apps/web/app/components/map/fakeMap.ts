/** A stand-in for MapLibre's Map in tests (jsdom has no WebGL): it records
 * what the app asks of it and lets a test click a layer's feature. */

type Handler = (event: unknown) => void;

export class FakeMap {
  static last: FakeMap | null = null;
  sources = new Map<string, { data: unknown; setData: (d: unknown) => void }>();
  layers = new Map<string, object>();
  fitted: unknown[] = [];
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

  off(type: string, layer: string, handler: Handler) {
    this.handlers = this.handlers.filter(
      (h) => !(h.type === type && h.layer === layer && h.handler === handler),
    );
    return this;
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

  addSource(id: string, source: { data: unknown }) {
    const entry = {
      data: source.data,
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
  addLayer(layer: { id: string }) {
    this.layers.set(layer.id, layer);
  }
  getLayer(id: string) {
    if (!this.style) throw new TypeError("the map has been removed");
    return this.layers.get(id);
  }
  removeLayer(id: string) {
    this.layers.delete(id);
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
  fitBounds(bounds: unknown, options?: unknown) {
    this.fitted.push(bounds);
    this.fitOptions.push(options);
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
