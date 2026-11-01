"""Tests for button_nz.bench.impact: what the town screen means for housing."""

from button_nz.bench.impact import Census, property_counts, scenarios


def row(parcel: int, prop: int, room: bool, clear: bool) -> dict[str, object]:
    return {
        "parcel_id": parcel,
        "property_id": prop,
        "fits_eaves": ["p"] if room else [],
        "clear_eaves": ["p"] if clear else [],
    }


def test_properties_are_counted_once_with_room_if_any_parcel_has_it() -> None:
    rows = [
        row(1, 1, False, False),
        row(2, 1, True, False),
        row(3, 3, True, True),
        row(4, 4, False, False),
    ]
    assert property_counts(rows) == {"properties": 3, "room": 2, "clear": 1}


CENSUS = Census(year=2023, population=1026, households=489, dwellings=603)


def test_each_scenario_gives_homes_the_increase_and_people_housed() -> None:
    (ten, half) = scenarios(622, CENSUS, (0.10, 0.50))
    assert (ten.share, ten.homes) == (0.10, 62)  # 10% of 622, rounded down: whole homes
    assert round(ten.increase, 3) == round(62 / 603, 3)
    assert (ten.people_low, ten.people_high) == (62, 130)  # 1 a flat, to the census's 2.1
    assert half.homes == 311 and round(half.increase * 100) == 52


def test_people_per_household_is_the_census_own() -> None:
    assert round(CENSUS.people_per_household, 2) == 2.10
