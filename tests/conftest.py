"""Shared fixtures and helpers for the nts test suite.

The suite is split into two layers:

* pure-function tests (parsing/formatting) that need no I/O, and
* integration tests for the metadata/album code that generate a small silent
  audio file with ffmpeg and read the resulting tags back with music_tag.

Integration tests are skipped automatically when ffmpeg is not on PATH.
"""

import datetime
import io
import os
import shutil
import subprocess

import pytest
from bs4 import BeautifulSoup

FFMPEG = shutil.which("ffmpeg")
requires_ffmpeg = pytest.mark.skipif(FFMPEG is None, reason="ffmpeg not installed")


_CODEC_BY_EXT = {".ogg": "libopus", ".m4a": "aac", ".mp3": "libmp3lame"}


def make_audio(path, seconds):
    """Generate a silent audio file; codec is inferred from the extension."""
    ext = os.path.splitext(path)[1].lower()
    subprocess.run(
        [
            FFMPEG, "-v", "quiet", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-t", str(seconds), "-c:a", _CODEC_BY_EXT[ext], path,
        ],
        check=True,
    )
    return path


def make_ogg(path, seconds):
    """Generate a silent Opus-in-Ogg file of the given length."""
    return make_audio(path, seconds)


def has_artwork(path):
    """Whether a file carries embedded artwork.

    music_tag raises KeyError when reading artwork from an Ogg that has no
    picture block, so we treat that as "no artwork" rather than letting it
    propagate.
    """
    import music_tag

    f = music_tag.load_file(path)
    try:
        art = f["artwork"]
    except KeyError:
        return False
    return len(art) > 0


@pytest.fixture
def image_bytes():
    """A tiny valid PNG to embed as artwork."""
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (16, 16), (200, 30, 30)).save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def api_data():
    """A trimmed but realistic NTS episode API payload.

    Mirrors the shape returned by
    https://www.nts.live/api/v2/shows/<show>/episodes/<episode>, including the
    real-world quirk of a track with a null duration backed by an estimate.
    """
    return {
        "name": "Optimo",
        "location_long": "Glasgow",
        "show_alias": "optimo",
        "broadcast": "2023-08-08T16:00:00+00:00",
        "description": "Two hours of Optimo.",
        "media": {"picture_large": "https://example.com/art.jpg"},
        "genres": [
            {"id": "g1", "value": "Electro"},
            {"id": "g2", "value": "Dub"},
            {"id": "g3", "value": ""},  # blank values get filtered out
        ],
        "embeds": {
            "tracklist": {
                "results": [
                    {
                        "title": "Lullaby",
                        "artist": "De Fabriek",
                        "offset": 8,
                        "duration": None,
                        "offset_estimate": None,
                        "duration_estimate": 198,
                    },
                    {
                        "title": "Second",
                        "artist": "Someone",
                        "offset": 206,
                        "duration": 100,
                        "offset_estimate": None,
                        "duration_estimate": None,
                    },
                ]
            }
        },
    }


@pytest.fixture
def empty_soup():
    """An empty BeautifulSoup document (parse_artists needs a soup object)."""
    return BeautifulSoup("", "html.parser")


def make_parsed(**overrides):
    """Build a parsed-episode dict like parse_nts_data returns."""
    parsed = {
        "safe_title": "Optimo",
        "date": datetime.datetime(2023, 8, 8, 16, 0, 0),
        "title": "Optimo",
        "artists": ["JD Twitch"],
        "parsed_artists": ["JG Wilkes"],
        "genres": ["Electro", "Dub"],
        "station": "Glasgow",
        "tracks": [
            {"name": "Lullaby", "artist": "De Fabriek"},
            {"name": "Second", "artist": "Someone"},
        ],
        "image_url": "https://example.com/art.jpg",
        "description": "Two hours of Optimo.",
        "timestamps": [{"offset": 8, "duration": 198}, {"offset": 206, "duration": 100}],
        "show_alias": "Optimo",
        "url": "https://www.nts.live/shows/optimo/episodes/optimo-8th-august-2023",
    }
    parsed.update(overrides)
    return parsed


@pytest.fixture
def parsed():
    return make_parsed()
