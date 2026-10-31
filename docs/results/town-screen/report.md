# Town screen: room for a real prefab in Reefton

Code `7b6fce0`. Envelope (NZTM2000) `(1505100.0, 5336200.0, 1506700.0, 5337700.0)`. 1320 residential sections: BDC parcels with a title whose point lies in a Residential zone (986 with more than 1 m² of a LINZ building outline on them). Left out: 633 titles outside a Residential zone, and parcels in one that aren't titles (Road: 2, Vesting on Deposit for Local Purpose Reserve: 3). A section counts if at least one real prefab with labelled dimensions fits on it, square to one of its walls.

| Count | Sections | Share |
|---|---|---|
| Room under LINZ outlines, stated dimensions | 928 | 70% |
| Room under LINZ outlines, with 0.6 m eaves | 849 | 64% |
| Room clear of everything over 2 m on the LiDAR, stated dimensions | 603 | 46% |
| Room clear of everything over 2 m on the LiDAR, with 0.6 m eaves | 506 | 38% |

## Backyards

A granny flat is usually built beside a home: these are the sections with a building on them, and those without.

| Sections | Count | Room under LINZ outlines, stated dimensions | Room under LINZ outlines, with 0.6 m eaves | Room clear of everything over 2 m on the LiDAR, stated dimensions | Room clear of everything over 2 m on the LiDAR, with 0.6 m eaves |
|---|---|---|---|---|---|
| With a building on them (a backyard) | 986 | 645 | 571 | 418 | 343 |
| With none | 334 | 283 | 278 | 185 | 163 |

## By section size

| Section area | Sections | With a building | Room under LINZ outlines, with 0.6 m eaves | Room clear of everything over 2 m on the LiDAR, with 0.6 m eaves |
|---|---|---|---|---|
| 0–300 m² | 295 | 199 | 92 | 41 |
| 300–600 m² | 498 | 401 | 243 | 107 |
| 600–1000 m² | 287 | 208 | 274 | 159 |
| 1000 m² and over | 240 | 178 | 240 | 199 |

## By product

| Product | Room under LINZ outlines, stated dimensions | Room under LINZ outlines, with 0.6 m eaves | Room clear of everything over 2 m on the LiDAR, stated dimensions | Room clear of everything over 2 m on the LiDAR, with 0.6 m eaves |
|---|---|---|---|---|
| South Peak Homes Okari (9 x 3.5 m) | 919 | 838 | 585 | 490 |
| South Peak Homes Nile (12 x 3.5 m) | 851 | 745 | 512 | 424 |
| AirHome Vista (12.2 x 4 m) | 820 | 723 | 484 | 390 |
| Russley Portables Frazer (12 x 5.4 m) | 763 | 522 | 414 | 255 |
| AirHome Pinnacle (15 x 4 m) | 753 | 648 | 441 | 327 |
| Living Little Oldham (14.4 x 4.2 m) | 750 | 657 | 433 | 329 |
| South Peak Homes Kendall (13.2 x 4.8 m) | 745 | 621 | 414 | 305 |
| Russley Portables Methven (15 x 4.2 m) | 741 | 641 | 425 | 311 |
| Russley Portables Kurow (13.45 x 5.4 m) | 724 | 510 | 380 | 239 |
| Living Little Cameron (16.6 x 4.2 m) | 684 | 589 | 377 | 283 |
| Lockwood Haven (concept) (9.04 x 6.64 m) | 594 | 529 | 337 | 260 |
| Lockwood Lakeview (concept) (10.54 x 6.65 m) | 581 | 508 | 313 | 235 |
| Lockwood Ara (concept) (13.59 x 6.24 m) | 564 | 474 | 275 | 207 |
| South Peak Homes Sefton (9.6 x 7.2 m) | 564 | 505 | 314 | 235 |

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

- **Buller District Council property parcels** (CC-BY-4.0 as recorded in data/demo-site/site.json; the layer's ArcGIS item states no licence; Buller District Council; LINZ, Crown copyright reserved). Retrieved 2026-10-31. https://services6.arcgis.com/Whb8vGWSmNkavSpL/arcgis/rest/services/BDC_Property_Master_Public_View/FeatureServer/1
- **Buller District Council zones (Residential)** (no licence stated on the layer's ArcGIS item; Buller District Council; LINZ, Crown copyright reserved). Retrieved 2026-10-31. https://services6.arcgis.com/Whb8vGWSmNkavSpL/arcgis/rest/services/BDC_Planning_Data_Public_View/FeatureServer/29
- **LINZ NZ Building Outlines** (CC-BY-4.0; Toitū Te Whenua Land Information New Zealand). Captured from aerial photos of 2015-12-26 to 2016-06-01. https://services.arcgis.com/xdsHIIxuCWByZiCB/arcgis/rest/services/LINZ_NZ_Building_Outlines/FeatureServer/0
- **West Coast LiDAR 1m DEM and DSM (2020-2024)** (CC-BY-4.0; Toitū Te Whenua Land Information New Zealand, Aerial Surveys, West Coast Regional Council). Captured 2020-05-15 to 2024-07-10. https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022/dem_1m/2193/BS21_10000_0503.tiff, https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022/dem_1m/2193/BS21_10000_0504.tiff, https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022/dsm_1m/2193/BS21_10000_0503.tiff, https://nz-elevation.s3.ap-southeast-2.amazonaws.com/west-coast/west-coast_2020-2022/dsm_1m/2193/BS21_10000_0504.tiff
