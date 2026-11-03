# Relief views: how soon each is ready (#149)

The demo site, 35 Victory Street, Reefton; code a1a3326. Reading its DEM, DSM and aerial
from LINZ took 5.2 s, before any tier ran; a built site in the app
has them on disk. **Ready after** counts from when the tiers start, so it
is how long an owner waits for each view.

| Tier | Status | Ready after (s) | Took (s) |
|---|---|---|---|
| depth | ready | 0.08 | 0.08 |
| parallax | ready | 1.95 | 1.86 |
| flyover | ready | 9.71 | 7.77 |

![depth](depth.png)

![parallax](parallax.png)

![flyover](flyover.png)

