# Data

## Demo property

35 Victory Street, Reefton (Buller District). Verified 2026-10-28 against the
live LINZ and Buller services (issue #4). `demo-site/site.json` is the source
of truth; load it with `button_nz.demo_site.load_demo_site()`, which checks the
manifest's own claims.

- LINZ address ID 3213224. Address point NZTM2000 (1505941.6, 5336793.7), in
  Section 701.
- Valuation number 1905027200. Title 354613.
- The site is all four sections on that title: Sections 700, 701 and 702
  (309 m² each) and Section 1336 (30 m²) TN OF Reefton. Section 1336 adjoins all
  three, so together they form one contiguous polygon of about 986 m².
  Geometry: `demo-site/parcels.geojson` (EPSG:2193).
- Ground is flat: 189.25–191.26 m (NZVD2016). The LiDAR shows 91 one-metre
  cells more than 2 m above ground on the parcels, up to 14.3 m, but LINZ has no
  building outline on them. The outlines nearby were traced from 2015–2016
  aerials, so treat them as dated evidence, not current truth.

## Sources and provenance

Every layer is CC BY 4.0 except Buller District Council's parcels and zones,
which state no licence (see "Parcel licence" below). `site.json` records each one's collection, tile,
asset URL, capture dates, resolution and attribution.

| Layer | Dataset | Tile | Capture |
| --- | --- | --- | --- |
| DEM | West Coast LiDAR 1m DEM | BS21_10000_0503 | 2020-05 to 2024-07 |
| DSM | West Coast LiDAR 1m DSM | BS21_10000_0503 | 2020-05 to 2024-07 |
| Aerial | Buller 0.075m Urban Aerial Photos | BS21_1000_4730 | 2024-12 to 2025-09 |
| Aerial (rural) | West Coast 0.2m Rural Aerial Photos | BS21_5000_1006 | 2024-12 to 2026-03 |
| Parcels | Buller District Council property parcels | — | — |
| Buildings | LINZ NZ Building Outlines | — | 2015-12 to 2016-06 |

Elevation is NZTM2000 horizontally and NZVD2016 vertically (EPSG:7839). The
vertical datum is not recorded in the GeoTIFFs; LINZ's elevation specification
states it.

## Parcel licence

Buller District Council's property and zone layers state no licence on their
ArcGIS items, so none is claimed for them (`geo.property.BDC_LICENCE`). The
four demo parcels have the same ids as LINZ's
[NZ Primary Parcels](https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services/LINZ_NZ_Primary_Parcels/FeatureServer),
published under CC BY 4.0, and match them to within 7 mm (checked 1 November
2026). That is a fact about those four, not BDC's licence.

## Still open

- The owner's own survey of the site. The owner says nothing is built on it,
  so the two features the survey took for sheds are not buildings.

The owner gave permission on 31 October 2026 to publish imagery and renders
of the site.

Do not commit raw downloads until licensing and size are agreed. The manifest
pins exact tile URLs on LINZ's public S3, so fetch from there.
