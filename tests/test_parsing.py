"""Unit tests for the pure parsing/formatting helpers (no I/O)."""

import datetime

import pytest

from nts import downloader
from tests.conftest import make_parsed


# --- small string helpers ---------------------------------------------------

@pytest.mark.parametrize("day,suffix", [
    (1, "st"), (2, "nd"), (3, "rd"), (4, "th"),
    (11, "th"), (12, "th"), (13, "th"),
    (21, "st"), (22, "nd"), (23, "rd"), (28, "th"),
])
def test_get_suffix(day, suffix):
    assert downloader.get_suffix(day) == suffix


def test_unsafe_char_replaces_slash_and_colon():
    assert downloader.unsafe_char("AC/DC: Live") == "AC-DC- Live"


# --- timestamp parsing (regression: null coalescing) ------------------------

def test_parse_timestamps_uses_estimate_when_value_null(api_data):
    ts = downloader.parse_timestamps(api_data)
    # first track: offset present (8), duration null -> falls back to estimate
    assert ts[0] == {"offset": 8, "duration": 198}
    # second track: both present, passed through
    assert ts[1] == {"offset": 206, "duration": 100}


def test_parse_timestamps_all_null_coalesces_to_zero():
    api = {"embeds": {"tracklist": {"results": [
        {"offset": None, "duration": None,
         "offset_estimate": None, "duration_estimate": None},
    ]}}}
    ts = downloader.parse_timestamps(api)
    # the bug was .get(key, 0) returning None for present-but-null keys
    assert ts == [{"offset": 0, "duration": 0}]


def test_parse_timestamps_empty_tracklist():
    assert downloader.parse_timestamps({"embeds": {}}) == []


def test_parse_tracklist_extracts_name_and_artist(api_data):
    tracks = downloader.parse_tracklist(api_data)
    assert tracks == [
        {"name": "Lullaby", "artist": "De Fabriek"},
        {"name": "Second", "artist": "Someone"},
    ]


# --- formatting helpers over a parsed dict ----------------------------------

def test_get_title_zero_pads_date(parsed):
    assert downloader.get_title(parsed) == "Optimo - 08.08.2023"


def test_get_date_isoformat(parsed):
    assert downloader.get_date(parsed) == "2023-08-08"


def test_get_genres_joined(parsed):
    assert downloader.get_genres(parsed) == "Electro; Dub"


def test_get_tracklist(parsed):
    assert downloader.get_tracklist(parsed) == "Lullaby by De Fabriek\nSecond by Someone"


def test_get_comment_with_description(parsed):
    assert downloader.get_comment(parsed) == (
        "Two hours of Optimo.\n"
        "Station Location: Glasgow\n"
        "https://www.nts.live/shows/optimo/episodes/optimo-8th-august-2023"
    )


def test_get_comment_without_description():
    parsed = make_parsed(description="")
    comment = downloader.get_comment(parsed)
    assert comment.startswith("Station Location: Glasgow\n")
    assert "\n\n" not in comment  # no empty leading description line


def test_get_artists_dedupes_case_insensitively():
    parsed = make_parsed(artists=["Floating Points"],
                         parsed_artists=["floating points", "David Wrench"])
    # case-insensitive dedup, first spelling wins, order preserved
    assert downloader.get_artists(parsed) == "Floating Points; David Wrench"


# --- parse_artists / parse_nts_data -----------------------------------------

def test_parse_artists_from_title(empty_soup):
    artists, parsed_artists = downloader.parse_artists("Optimo w/ JG Wilkes", empty_soup)
    assert artists == []  # no .bio-artists in an empty document
    assert "JG Wilkes" in parsed_artists


def test_parse_nts_data_shape(empty_soup, api_data):
    parsed = downloader.parse_nts_data(empty_soup, api_data)
    assert parsed["title"] == "Optimo"
    assert parsed["station"] == "Glasgow"
    assert parsed["safe_title"] == "Optimo"
    assert parsed["show_alias"] == "Optimo"  # dash->space + titlecased
    assert parsed["genres"] == ["Electro", "Dub"]  # blank value filtered
    assert isinstance(parsed["date"], datetime.datetime)
    assert parsed["date"].year == 2023 and parsed["date"].month == 8
    assert parsed["image_url"] == "https://example.com/art.jpg"
    assert len(parsed["timestamps"]) == 2


def test_parse_nts_data_titlecases_dashed_show_alias(empty_soup, api_data):
    api_data["show_alias"] = "carlos-rene"
    parsed = downloader.parse_nts_data(empty_soup, api_data)
    assert parsed["show_alias"] == "Carlos Rene"
