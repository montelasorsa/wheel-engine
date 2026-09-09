"""Tests for the enrichment step: contract shape, coercion, selection, cache.

`tests/golden/enrichment_records.json` freezes the exact record
`build_enrichment` produces for every case in
`tests/fixtures/enrichment_info_cases.json`. A field added, renamed, dropped,
or coerced differently fails here with a readable diff. Regenerate with:

    PYTHONPATH=src python tests/test_enrich.py --regenerate

The cases are chosen to cover the three shapes a provider actually returns: a
complete response, a mostly-empty one, and one carrying type damage (NaN,
booleans where numbers belong, empty strings, a string epoch, more officers
than the cap).
"""

from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import sys
import tempfile
import unittest

from wheel.enrich import (
    ENRICHMENT_SCHEMA_VERSION,
    OFFICER_CAP,
    SECTIONS,
    EnrichmentConfig,
    build_enrichment,
    empty_enrichment,
    enrichment_config_from_config,
    enrichment_dir,
    enrichment_path,
    extract_officers,
    read_enrichment,
    read_enrichment_set,
    section_keys,
    select_enrichment_targets,
    write_enrichment,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "enrichment_info_cases.json"
GOLDEN_PATH = Path(__file__).parent / "golden" / "enrichment_records.json"
FETCHED_ON = date(2026, 9, 6)


def load_cases() -> dict[str, dict]:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return {key: value for key, value in payload.items() if not key.startswith("_")}


def build_all() -> dict[str, dict]:
    return {
        ticker: build_enrichment(ticker, info, fetched_on=FETCHED_ON)
        for ticker, info in sorted(load_cases().items())
    }


class GoldenRecordTests(unittest.TestCase):
    """The frozen contract. This is the test the task calls the golden file."""

    def test_every_case_matches_the_frozen_record(self) -> None:
        expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        actual = build_all()
        self.assertEqual(sorted(actual), sorted(expected))
        for ticker in sorted(actual):
            with self.subTest(ticker=ticker):
                self.assertEqual(actual[ticker], expected[ticker])

    def test_every_contract_field_lands_for_a_complete_response(self) -> None:
        """A full provider response fills every key -- no silent omission."""

        record = build_all()["FULL"]
        for section, _ in SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(
                    sorted(record[section]), sorted(section_keys(section))
                )
                self.assertTrue(
                    all(value is not None for value in record[section].values()),
                    f"{section} carries a null on a complete response",
                )
        self.assertTrue(record["officers"])

    def test_every_key_is_present_even_when_nothing_is(self) -> None:
        """§4.4: missing renders as a null in place, never a missing key."""

        record = build_all()["EMPTY"]
        for section, _ in SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(
                    sorted(record[section]), sorted(section_keys(section))
                )
                self.assertTrue(
                    all(value is None for value in record[section].values())
                )
        self.assertEqual(record["officers"], [])
        self.assertEqual(record["schema_version"], ENRICHMENT_SCHEMA_VERSION)
        self.assertEqual(record["ticker"], "EMPTY")
        self.assertEqual(record["fetched_on"], "2026-09-06")


class CoercionTests(unittest.TestCase):
    def test_type_damage_degrades_to_null_rather_than_raising(self) -> None:
        record = build_all()["MESSY"]
        self.assertIsNone(record["ratios"]["trailing_pe"])   # "not-a-number"
        self.assertIsNone(record["ratios"]["price_to_book"])  # True is not 1.0
        self.assertIsNone(record["revenue"]["total_revenue"])  # NaN is missing
        self.assertIsNone(record["business"]["long_name"])   # whitespace only
        self.assertIsNone(record["business"]["website"])     # empty string
        self.assertIsNone(record["analyst"]["recommendation_key"])

    def test_zero_is_a_value_not_a_missing_field(self) -> None:
        """§4.4: null is not zero, and zero is not null."""

        record = build_all()["MESSY"]
        self.assertEqual(record["ratios"]["debt_to_equity"], 0.0)
        self.assertEqual(record["dividend"]["dividend_rate"], 0.0)
        self.assertEqual(record["dividend"]["payout_ratio"], 0.0)

    def test_numeric_strings_and_floats_coerce(self) -> None:
        record = build_all()["MESSY"]
        self.assertEqual(record["ratios"]["profit_margins"], 0.0815)
        self.assertEqual(record["business"]["full_time_employees"], 4212)
        self.assertEqual(record["analyst"]["number_of_analyst_opinions"], 7)

    def test_summary_whitespace_is_stripped(self) -> None:
        self.assertEqual(
            build_all()["MESSY"]["business"]["long_business_summary"],
            "A summary with surrounding whitespace.",
        )

    def test_ex_dividend_epoch_becomes_an_iso_date(self) -> None:
        self.assertEqual(build_all()["FULL"]["dividend"]["ex_dividend_date"], "2026-11-05")

    def test_ex_dividend_accepts_a_string_date(self) -> None:
        self.assertEqual(build_all()["MESSY"]["dividend"]["ex_dividend_date"], "2026-05-14")

    def test_a_null_info_dictionary_still_produces_a_record(self) -> None:
        record = build_enrichment("ABC", None, fetched_on=FETCHED_ON)
        self.assertEqual(record, empty_enrichment("abc", fetched_on=FETCHED_ON))
        self.assertEqual(record["ticker"], "ABC")


class OfficerTests(unittest.TestCase):
    def test_only_name_and_title_survive(self) -> None:
        officers = build_all()["FULL"]["officers"]
        self.assertEqual(
            officers[0], {"name": "Mr. William Clay Ford Jr.", "title": "Executive Chairman"}
        )
        for officer in officers:
            self.assertEqual(sorted(officer), ["name", "title"])

    def test_entries_are_capped_and_junk_is_dropped(self) -> None:
        officers = build_all()["MESSY"]["officers"]
        self.assertEqual(len(officers), OFFICER_CAP)
        self.assertEqual(officers[1], {"name": None, "title": "Chief Financial Officer"})
        self.assertEqual(officers[2], {"name": "Officer Three", "title": None})
        # The age-only entry and the bare string carry nothing renderable.
        self.assertNotIn({"name": None, "title": None}, officers)

    def test_a_non_list_officer_field_is_not_an_error(self) -> None:
        self.assertEqual(extract_officers({"companyOfficers": "CEO"}), [])
        self.assertEqual(extract_officers({}), [])


class ConfigTests(unittest.TestCase):
    def test_defaults_when_the_section_is_absent(self) -> None:
        settings = enrichment_config_from_config({})
        self.assertEqual(settings.top_n, 50)
        self.assertTrue(settings.include_locked_zones)

    def test_values_are_read_and_coerced(self) -> None:
        settings = enrichment_config_from_config(
            {"enrichment": {"top_n": 3, "include_locked_zones": False}}
        )
        self.assertEqual(settings, EnrichmentConfig(top_n=3, include_locked_zones=False))

    def test_the_example_config_carries_the_section(self) -> None:
        import yaml

        example = yaml.safe_load(
            (Path(__file__).parent.parent / "config" / "example.yaml").read_text()
        )
        self.assertEqual(
            enrichment_config_from_config(example),
            EnrichmentConfig(top_n=50, include_locked_zones=True),
        )


SIDECAR = {
    "run_date": "2026-09-06",
    "entries": {
        "AAA": {"score": 71.0, "zone": "Zone 1", "thesis_backed": False},
        "BBB": {"score": 88.5, "zone": "Zone 2", "thesis_backed": True},
        "CCC": {"score": 88.5, "zone": "Zone 1", "thesis_backed": False},
        "DDD": {"score": 64.2, "zone": "Beyond zones", "thesis_backed": False},
    },
}


class TargetSelectionTests(unittest.TestCase):
    def test_highest_score_first_ties_broken_alphabetically(self) -> None:
        targets = select_enrichment_targets(SIDECAR, EnrichmentConfig(top_n=10))
        self.assertEqual(targets, ["BBB", "CCC", "AAA", "DDD"])

    def test_top_n_truncates(self) -> None:
        self.assertEqual(
            select_enrichment_targets(SIDECAR, EnrichmentConfig(top_n=2)),
            ["BBB", "CCC"],
        )

    def test_locked_zones_can_be_excluded(self) -> None:
        self.assertEqual(
            select_enrichment_targets(
                SIDECAR, EnrichmentConfig(top_n=10, include_locked_zones=False)
            ),
            ["CCC", "AAA"],
        )

    def test_a_missing_or_malformed_sidecar_selects_nothing(self) -> None:
        for sidecar in (None, {}, {"entries": []}, {"entries": {"AAA": "junk"}}):
            with self.subTest(sidecar=sidecar):
                self.assertEqual(
                    select_enrichment_targets(sidecar, EnrichmentConfig()), []
                )

    def test_a_null_score_sorts_last_rather_than_raising(self) -> None:
        sidecar = {"entries": {"AAA": {"score": None}, "BBB": {"score": 10.0}}}
        self.assertEqual(
            select_enrichment_targets(sidecar, EnrichmentConfig()), ["BBB", "AAA"]
        )


class CacheLayoutTests(unittest.TestCase):
    def test_path_is_dated_folder_then_ticker(self) -> None:
        path = enrichment_path("/tmp/ops", date(2026, 9, 6), "aapl")
        self.assertEqual(path.name, "AAPL.json")
        self.assertEqual(path.parent, enrichment_dir("/tmp/ops", "2026-09-06"))
        self.assertEqual(path.parent.parent.name, "enrichment")

    def test_write_then_read_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            record = build_all()["FULL"]
            written = write_enrichment(temporary, FETCHED_ON, record)
            self.assertTrue(written.is_file())
            self.assertEqual(read_enrichment(temporary, FETCHED_ON, "full"), record)

    def test_no_temporary_file_is_left_behind(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            write_enrichment(temporary, FETCHED_ON, build_all()["FULL"])
            leftovers = list(enrichment_dir(temporary, FETCHED_ON).glob("*.tmp"))
            self.assertEqual(leftovers, [])

    def test_reading_an_absent_record_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertIsNone(read_enrichment(temporary, FETCHED_ON, "NOPE"))

    def test_read_set_collects_and_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            for record in build_all().values():
                write_enrichment(temporary, FETCHED_ON, record)
            everything = read_enrichment_set(temporary, FETCHED_ON)
            self.assertEqual(sorted(everything), ["EMPTY", "FULL", "MESSY", "SPARSE"])
            some = read_enrichment_set(temporary, FETCHED_ON, ["full", "nope"])
            self.assertEqual(sorted(some), ["FULL"])

    def test_read_set_skips_corrupt_files_rather_than_raising(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            write_enrichment(temporary, FETCHED_ON, build_all()["FULL"])
            directory = enrichment_dir(temporary, FETCHED_ON)
            (directory / "BROKEN.json").write_text("{not json", encoding="utf-8")
            self.assertEqual(
                sorted(read_enrichment_set(temporary, FETCHED_ON)), ["FULL"]
            )

    def test_read_set_on_a_missing_run_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(read_enrichment_set(temporary, "1999-01-01"), {})


def regenerate() -> None:
    GOLDEN_PATH.write_text(
        json.dumps(build_all(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Wrote {GOLDEN_PATH}")


if __name__ == "__main__":
    if "--regenerate" in sys.argv:
        regenerate()
    else:
        unittest.main()
