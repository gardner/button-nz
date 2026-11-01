"""Tests for button_nz.bench.impact: what the town screen means for housing."""

from pathlib import Path

from button_nz.bench.impact import CENSUS_FILE, Census, property_counts, report, scenarios


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
    assert census.household_size == 900 / 462  # households by size, not people/households


def test_people_housed_use_the_unrounded_mean_and_the_report_shows_it() -> None:
    """900/462 = 1.948: 219 homes house 426, not the 427 a rounded 1.95 gives."""
    census, raw = Census.read(CENSUS_FILE)
    (half,) = scenarios(439, census, (0.50,))
    assert half.people_high == 426
    counts = {"properties": 4, "backyards": 3, "backyard_room": 2, "backyard_clear": 1}
    text = report(counts | {"empty_room": 1}, census, raw, "abc1234")
    assert "average household of 1.95" in text and "1.9 " not in text


def test_backyards_are_said_to_be_properties_with_a_linz_outline() -> None:
    """The outlines don't say which building is a home: a shed counts, and a
    house built since 2016 is missing."""
    census, raw = Census.read(CENSUS_FILE)
    counts = {"properties": 4, "backyards": 3, "backyard_room": 2, "backyard_clear": 1}
    text = report(counts | {"empty_room": 1}, census, raw, "abc1234")
    assert "LINZ building outline" in text and "shed" in text
    assert "{" not in text  # every figure filled in


def test_the_one_person_share_says_which_households_it_is_of() -> None:
    """The size table covers 462 of the 489 households: 195/462 is 42%."""
    census, raw = Census.read(CENSUS_FILE)
    counts = {"properties": 4, "backyards": 3, "backyard_room": 2, "backyard_clear": 1}
    text = report(counts | {"empty_room": 1}, census, raw, "abc1234")
    assert "42% are one person (of the 462 households whose size Stats NZ gives)" in text
