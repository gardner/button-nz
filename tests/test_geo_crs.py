"""Tests for button_nz.geo.crs coordinate transforms."""

import pytest

from button_nz.geo.crs import LocalFrame, nztm_to_wgs84, wgs84_to_nztm

ADDRESS_NZTM = (1505941.6, 5336793.7)


def test_nztm_to_wgs84() -> None:
    assert nztm_to_wgs84(ADDRESS_NZTM) == pytest.approx((171.8622218, -42.1153178), abs=1e-7)


def test_round_trip() -> None:
    assert wgs84_to_nztm(nztm_to_wgs84(ADDRESS_NZTM)) == pytest.approx(ADDRESS_NZTM, abs=1e-6)


def test_local_frame_offsets_from_its_origin() -> None:
    frame = LocalFrame(origin=(1505926.13, 5336777.48))
    assert frame.to_local(ADDRESS_NZTM) == pytest.approx((15.47, 16.22))
    assert frame.to_nztm(frame.to_local(ADDRESS_NZTM)) == pytest.approx(ADDRESS_NZTM)


def test_local_frame_from_bbox_uses_its_centre() -> None:
    frame = LocalFrame.centred_on((0.0, 0.0, 10.0, 20.0))
    assert frame.origin == (5.0, 10.0)
