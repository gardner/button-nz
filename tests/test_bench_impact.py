"""Tests for button_nz.bench.impact: what the town screen means for housing."""

from pathlib import Path

from button_nz.bench.impact import CENSUS_FILE, Census, property_counts, scenarios


def row(parcel: int, prop: int, room: bool, clear: bool, buildings: int = 1) -> dict[str, object]:
    return {
        "parcel_id": parcel,
        "property_id": prop,
        "buildings": buildings,
        "fits_eaves": ["p"] if room else [],
        "clear_eaves": ["p"] if clear else [],
    }


def test_backyards_are_properties_with_a_home_and_room_counted_once() -> None:
    rows = [
        row(1, 1, False, False, buildings=1),  # a house on one parcel...
        row(2, 1, True, False, buildings=0),  # ...and room on the other: a backyard
        row(3, 3, True, True),
        row(4, 4, False, False),
        row(5, 5, True, True, buildings=0),  # an empty section: a first home, not a flat
    ]
    assert property_counts(rows) == {
        "properties": 4,
        "backyards": 3,
        "backyard_room": 2,
        "backyard_clear": 1,
        "empty_room": 1,
    }


CENSUS = Census(year=2023, population=1026, households=489, dwellings=603, household_size=1.9)


def test_each_scenario_gives_homes_the_increase_and_people_housed() -> None:
    (ten, half) = scenarios(439, CENSUS, (0.10, 0.50))
    assert (ten.share, ten.homes) == (0.10, 43)  # 10% of 439, rounded down: whole homes
    assert round(ten.increase, 3) == round(43 / 603, 3)
    assert (ten.people_low, ten.people_high) == (43, 81)  # 1 a flat, to the census's 1.9
    assert half.homes == 219 and round(half.increase * 100) == 36


def test_household_size_is_the_mean_of_stats_nzs_own_distribution(tmp_path: Path) -> None:
    census, _ = Census.read(CENSUS_FILE)
    assert census.household_size == round(
        900 / 462, 2
    )  # 1.95: households by size, not people/households
