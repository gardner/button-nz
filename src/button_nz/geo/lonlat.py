"""NZTM2000 to lon/lat (EPSG:4326), for web maps."""

import numpy as np
import shapely
from numpy.typing import NDArray
from pyproj import Transformer
from shapely.geometry.base import BaseGeometry

TO_LONLAT = Transformer.from_crs(2193, 4326, always_xy=True)


def lonlat(geometry: BaseGeometry) -> BaseGeometry:
    """``geometry`` from NZTM to lon/lat."""

    def project(xy: NDArray[np.float64]) -> NDArray[np.float64]:
        lon, lat = TO_LONLAT.transform(xy[:, 0], xy[:, 1])
        return np.column_stack([lon, lat])

    return shapely.transform(geometry, project)
