"""Integration tests for set_metadata_album (track splitting + fallback)."""

import os

import music_tag

from nts import downloader
from tests.conftest import make_ogg, has_artwork, make_parsed, requires_ffmpeg


# tracks + timestamps that carve a 12s file into an intro and three tracks:
#   intro  0..2   (offset of first track is non-zero)
#   Lullaby 2..5
#   Second  5..8
#   Third   8..end
ALBUM_TRACKS = [
    {"name": "Lullaby", "artist": "De Fabriek"},
    {"name": "Second", "artist": "Someone"},
    {"name": "Third", "artist": "Third Artist"},
]
ALBUM_TS = [
    {"offset": 2, "duration": 3},
    {"offset": 5, "duration": 3},
    {"offset": 8, "duration": 3},
]


def _load_album(tmp_path):
    files = {p.name: music_tag.load_file(str(p))
             for p in (tmp_path / "Optimo").iterdir()}
    return files


@requires_ffmpeg
def test_albumize_splits_into_intro_and_tracks(tmp_path, image_bytes):
    parsed = make_parsed(tracks=ALBUM_TRACKS, timestamps=ALBUM_TS)
    make_ogg(str(tmp_path / "ep.ogg"), 12)

    downloader.set_metadata_album(str(tmp_path), "ep.ogg", parsed, image_bytes, "image/png")

    album_dir = tmp_path / "Optimo"  # named after safe_title
    assert album_dir.is_dir()
    # intro + 3 tracks
    names = sorted(p.name for p in album_dir.iterdir())
    assert names == ["Lullaby.ogg", "Second.ogg", "Third.ogg", "intro.ogg"]
    # source file is consumed once split succeeds
    assert not (tmp_path / "ep.ogg").exists()


@requires_ffmpeg
def test_albumize_track_metadata_and_numbering(tmp_path, image_bytes):
    parsed = make_parsed(tracks=ALBUM_TRACKS, timestamps=ALBUM_TS)
    make_ogg(str(tmp_path / "ep.ogg"), 12)
    downloader.set_metadata_album(str(tmp_path), "ep.ogg", parsed, image_bytes, "image/png")

    files = _load_album(tmp_path)

    # intro
    intro = files["intro.ogg"]
    assert str(intro["tracktitle"]) == "NTS Intro"
    assert str(intro["artist"]) == "NTS"
    assert int(intro["tracknumber"]) == 1

    # tracks tagged with album-level fields and sequential numbers
    lullaby = files["Lullaby.ogg"]
    assert str(lullaby["tracktitle"]) == "Lullaby"
    assert str(lullaby["artist"]) == "De Fabriek"
    assert str(lullaby["album"]) == "Optimo - 08.08.2023"  # get_title
    assert str(lullaby["albumartist"]) == "Optimo"          # get_show
    assert int(lullaby["tracknumber"]) == 2
    assert int(files["Second.ogg"]["tracknumber"]) == 3
    assert int(files["Third.ogg"]["tracknumber"]) == 4

    # totaltracks counts intro + tracks (regression: it used to be len + 2)
    for f in files.values():
        assert int(f["totaltracks"]) == 4

    # every split carries artwork
    for name in files:
        assert has_artwork(str(tmp_path / "Optimo" / name))


@requires_ffmpeg
def test_albumize_streams_are_copied_not_reencoded(tmp_path, image_bytes):
    """Middle tracks used to be re-encoded; all splits should stay Opus."""
    parsed = make_parsed(tracks=ALBUM_TRACKS, timestamps=ALBUM_TS)
    make_ogg(str(tmp_path / "ep.ogg"), 12)
    downloader.set_metadata_album(str(tmp_path), "ep.ogg", parsed, image_bytes, "image/png")

    for f in _load_album(tmp_path).values():
        assert str(f["#codec"]) == "Ogg Opus"


@requires_ffmpeg
def test_albumize_existing_dir_does_not_crash(tmp_path, image_bytes):
    """Regression: os.mkdir -> os.makedirs(exist_ok=True)."""
    parsed = make_parsed(tracks=ALBUM_TRACKS, timestamps=ALBUM_TS)
    (tmp_path / "Optimo").mkdir()  # pre-existing album dir
    make_ogg(str(tmp_path / "ep.ogg"), 12)
    # must not raise FileExistsError
    downloader.set_metadata_album(str(tmp_path), "ep.ogg", parsed, image_bytes, "image/png")
    assert (tmp_path / "Optimo" / "Lullaby.ogg").exists()


@requires_ffmpeg
def test_albumize_falls_back_when_timestamps_all_null(tmp_path, image_bytes):
    """No usable timestamps -> single tagged file, no album dir, no crash."""
    parsed = make_parsed(
        tracks=ALBUM_TRACKS,
        timestamps=[{"offset": 0, "duration": 0}] * 3,
    )
    make_ogg(str(tmp_path / "ep.ogg"), 4)

    downloader.set_metadata_album(str(tmp_path), "ep.ogg", parsed, image_bytes, "image/png")

    assert not (tmp_path / "Optimo").exists()      # no album produced
    assert (tmp_path / "ep.ogg").exists()          # original kept
    f = music_tag.load_file(str(tmp_path / "ep.ogg"))
    assert str(f["album"]) == "NTS"                # single-file metadata applied


@requires_ffmpeg
def test_albumize_falls_back_when_no_timestamps(tmp_path, image_bytes):
    parsed = make_parsed(tracks=ALBUM_TRACKS, timestamps=[])
    make_ogg(str(tmp_path / "ep.ogg"), 4)
    downloader.set_metadata_album(str(tmp_path), "ep.ogg", parsed, image_bytes, "image/png")
    assert not (tmp_path / "Optimo").exists()
    assert (tmp_path / "ep.ogg").exists()


@requires_ffmpeg
def test_albumize_no_intro_when_first_offset_zero(tmp_path, image_bytes):
    """First track at offset 0 -> no intro file, numbering starts at 1."""
    parsed = make_parsed(
        tracks=ALBUM_TRACKS,
        timestamps=[{"offset": 0, "duration": 3},
                    {"offset": 3, "duration": 3},
                    {"offset": 6, "duration": 3}],
    )
    make_ogg(str(tmp_path / "ep.ogg"), 10)

    downloader.set_metadata_album(str(tmp_path), "ep.ogg", parsed, image_bytes, "image/png")

    names = sorted(p.name for p in (tmp_path / "Optimo").iterdir())
    assert names == ["Lullaby.ogg", "Second.ogg", "Third.ogg"]  # no intro.ogg
    files = _load_album(tmp_path)
    assert int(files["Lullaby.ogg"]["tracknumber"]) == 1
    assert int(files["Third.ogg"]["tracknumber"]) == 3
    for f in files.values():
        assert int(f["totaltracks"]) == 3  # no intro counted


@requires_ffmpeg
def test_albumize_single_track_keeps_full_audio(tmp_path, image_bytes):
    """Regression: the last-track start used ts[i-1], which wraps to ts[-1]
    for a single track and dropped the start of the only track."""
    parsed = make_parsed(
        tracks=[{"name": "Only", "artist": "Solo"}],
        timestamps=[{"offset": 2, "duration": 3}],  # intro 0..2, track 2..end
    )
    make_ogg(str(tmp_path / "ep.ogg"), 8)

    downloader.set_metadata_album(str(tmp_path), "ep.ogg", parsed, image_bytes, "image/png")

    only = music_tag.load_file(str(tmp_path / "Optimo" / "Only.ogg"))
    # track starts at offset 2 of an 8s file -> ~6s, not ~3s (which the
    # wrap-around bug would have produced by starting at 2+3=5)
    assert float(only["#length"].value) > 5.0
