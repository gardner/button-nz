# Town screen: room for a real prefab in Reefton

Code `7136d87`. Envelope (NZTM2000) `(1505100.0, 5336200.0, 1506700.0, 5337700.0)`. 1320 residential sections: BDC parcels with a title whose point lies in a Residential zone (986 with more than 1 m² of a LINZ building outline on them). Left out: 207 titles outside a Residential zone in the envelope, and parcels in one that aren't titles (Road: 2, Vesting on Deposit for Local Purpose Reserve: 3). A section counts if at least one real prefab with labelled dimensions fits in its room (below).

The sections are 959 properties (titles): a title can cover several parcels, and is what's bought, sold and regulated. A property has room if any of its parcels does.

| Count | Properties | Share | Sections | Share |
|---|---|---|---|---|
| Room under LINZ outlines, stated dimensions | 698 | 73% | 859 | 65% |
| Room under LINZ outlines, with 0.6 m eaves | 622 | 65% | 762 | 58% |
| Room clear of everything over 2 m on the LiDAR, stated dimensions | 423 | 44% | 525 | 40% |
| Room clear of everything over 2 m on the LiDAR, with 0.6 m eaves | 326 | 34% | 409 | 31% |

## Backyards

A granny flat is usually built beside a home: these are the sections with a building on them, and those without.

| Sections | Count | Room under LINZ outlines, stated dimensions | Room under LINZ outlines, with 0.6 m eaves | Room clear of everything over 2 m on the LiDAR, stated dimensions | Room clear of everything over 2 m on the LiDAR, with 0.6 m eaves |
|---|---|---|---|---|---|
| With a building on them (a backyard) | 986 | 579 | 488 | 358 | 258 |
| With none | 334 | 280 | 274 | 167 | 151 |

## By section size

| Section area | Sections | With a building | Room under LINZ outlines, with 0.6 m eaves | Room clear of everything over 2 m on the LiDAR, with 0.6 m eaves |
|---|---|---|---|---|
| 0–300 m² | 295 | 199 | 78 | 35 |
| 300–600 m² | 498 | 401 | 201 | 91 |
| 600–1000 m² | 287 | 208 | 245 | 111 |
| 1000 m² and over | 240 | 178 | 238 | 172 |

## By product

| Product (properties) | Room under LINZ outlines, stated dimensions | Room under LINZ outlines, with 0.6 m eaves | Room clear of everything over 2 m on the LiDAR, stated dimensions | Room clear of everything over 2 m on the LiDAR, with 0.6 m eaves |
|---|---|---|---|---|
| South Peak Homes Okari (9 x 3.5 m) | 698 | 622 | 423 | 326 |
| South Peak Homes Nile (12 x 3.5 m) | 643 | 557 | 339 | 257 |
| AirHome Vista (12.2 x 4 m) | 612 | 529 | 311 | 229 |
| Russley Portables Frazer (12 x 5.4 m) | 564 | 392 | 250 | 166 |
| South Peak Homes Kendall (13.2 x 4.8 m) | 554 | 460 | 252 | 189 |
| Living Little Oldham (14.4 x 4.2 m) | 553 | 474 | 252 | 194 |
| AirHome Pinnacle (15 x 4 m) | 545 | 465 | 257 | 187 |
| Russley Portables Methven (15 x 4.2 m) | 536 | 455 | 243 | 180 |
| Russley Portables Kurow (13.45 x 5.4 m) | 524 | 376 | 219 | 155 |
| Living Little Cameron (16.6 x 4.2 m) | 486 | 417 | 210 | 163 |
| Lockwood Haven (concept) (9.04 x 6.64 m) | 447 | 403 | 228 | 178 |
| Lockwood Lakeview (concept) (10.54 x 6.65 m) | 433 | 388 | 199 | 159 |
| South Peak Homes Sefton (9.6 x 7.2 m) | 421 | 375 | 201 | 158 |
| Lockwood Ara (concept) (13.59 x 6.24 m) | 420 | 353 | 178 | 139 |

## What it checks

Schedule 1A's siting rules that need no site visit: the outline stands at least 2 m inside the section's boundary and at least 2 m from every LINZ building outline, each treated as a residential building, and stays on one parcel. The LiDAR count also keeps 2 m from every 1 m cell the nDSM shows over 2 m above the ground: buildings newer than the outlines, but also trees and hedges, so it counts room without removing anything. Products are tried square to each of the room's walls and to its minimum rotated rectangle (`catalogue.fit`): a fit can be missed, never invented. Most suppliers don't publish eaves, so each count is repeated with the outline grown by 0.6 m on every side.

## What it doesn't check

- **Hazards**: flooding (Reefton sits beside the Inangahua River), rockfall,
  and whatever a PIM would note. A site the PIM marks as likely hazard-affected
  may not suit the exemption.
- **Slope and floor level**: the exemption limits the floor to 1 m above the
  ground; the screen doesn't look at the ground's shape.
- **The district plan and the NES-DMRU**: zone rules, site coverage, the
  number of habitable buildings per site, and whether a resource consent is
  needed.
- **Services**: water, wastewater, stormwater and power.
- **What neither dataset shows**: structures too small for LINZ's outlines and
  under 2 m tall, and anything built or removed since the LiDAR (2020–24).
- **Lines between parcels on one title**: each parcel is screened alone, as if
  every parcel boundary were a legal boundary. A title of several parcels may
  have more room than this shows.
- **Height, design and the exemption's other conditions**: these depend on
  the building, not the section.

## Sources

- **Buller District Council property parcels** (not stated (the layer's ArcGIS item states none); Buller District Council). Retrieved 2026-11-01. https://services6.arcgis.com/Whb8vGWSmNkavSpL/arcgis/rest/services/BDC_Property_Master_Public_View/FeatureServer/1
- **Buller District Council zones (Residential)** (not stated (the layer's ArcGIS item states none); Buller District Council). Retrieved 2026-11-01. https://services6.arcgis.com/Whb8vGWSmNkavSpL/arcgis/rest/services/BDC_Planning_Data_Public_View/FeatureServer/29
- **LINZ NZ Building Outlines** (CC-BY-4.0; Toitū Te Whenua Land Information New Zealand). Captured from aerial photos of 2015-12-26 to 2016-06-01. https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services/LINZ_NZ_Building_Outlines/FeatureServer/0
- **West Coast LiDAR 1m DEM and DSM (2020-2024)** (CC-BY-4.0; Toitū Te Whenua Land Information New Zealand, Aerial Surveys, West Coast Regional Council). Captured 2020-05-15 to 2024-07-10. https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022/dem_1m/2193/BS21_10000_0503.tiff, https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022/dem_1m/2193/BS21_10000_0504.tiff, https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022/dsm_1m/2193/BS21_10000_0503.tiff, https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022/dsm_1m/2193/BS21_10000_0504.tiff
