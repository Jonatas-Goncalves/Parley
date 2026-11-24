from __future__ import annotations

from parley.core.scenarios import (
    BANDS,
    SCENARIO_BY_ID,
    SCENARIOS,
    get_scenario,
    scenarios_for_band,
)


def test_catalogue_has_the_requested_topics() -> None:
    assert len(SCENARIOS) == 19
    assert len(SCENARIO_BY_ID) == 19
    assert {scenario.band for scenario in SCENARIOS} == set(BANDS)


def test_bands_have_several_topics() -> None:
    for band in BANDS:
        assert len(scenarios_for_band(band)) >= 5


def test_ids_and_labels_are_unique() -> None:
    assert len({scenario.id for scenario in SCENARIOS}) == len(SCENARIOS)
    assert len({scenario.label for scenario in SCENARIOS}) == len(SCENARIOS)


def test_level_mapping() -> None:
    assert get_scenario("meeting_someone_new").level == "A2"
    assert get_scenario("plan_a_trip").level == "B1"
    assert get_scenario("ethical_dilemmas").level == "C1"


def test_unknown_scenario_falls_back_to_the_first() -> None:
    assert get_scenario("does-not-exist").id == SCENARIOS[0].id
