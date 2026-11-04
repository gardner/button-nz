# Relief views: how soon each is ready (#149)

The demo site, 35 Victory Street, Reefton; code 42d6d4f. Reading its DEM, DSM and aerial
from LINZ took 4.9 s, before any tier ran; a built site in the app
has them on disk. **Ready after** counts from when the tiers start, so it
is how long an owner waits for each view.

| Tier | Status | Ready after (s) | Took (s) |
|---|---|---|---|
| depth | ready | 0.08 | 0.08 |
| parallax | ready | 2.12 | 2.04 |
| flyover | ready | 23.40 | 21.29 |

![depth](depth.png)

![parallax](parallax.png)

![flyover](flyover.png)

