"""Integration tests for set_metadata (tags + artwork on a real file)."""

import os

import music_tag
import pytest

from nts import downloader
from tests.conftest import make_ogg, make_audio, has_artwork, make_parsed, requires_ffmpeg


@requires_ffmpeg
def test_set_metadata_writes_tags_and_artwork(tmp_path, parsed, image_bytes):
    path = make_ogg(str(tmp_path / "ep.ogg"), 2)
    downloader.set_metadata(path, parsed, image_bytes, "image/png")

    f = music_tag.load_file(path)
    assert str(f["title"]) == "Optimo - 08.08.2023"
    assert str(f["album"]) == "NTS"
    assert str(f["artist"]) == "JD Twitch; JG Wilkes"
    assert str(f["genre"]) == "Electro; Dub"
    assert int(f["compilation"]) == 1
    assert "Lullaby by De Fabriek" in str(f["lyrics"])
    assert "Station Location: Glasgow" in str(f["comment"])
    assert has_artwork(path)


@requires_ffmpeg
def test_set_metadata_artwork_regression(tmp_path, parsed, image_bytes):
    """Guards the e7b3df6 regression where artwork stopped being embedded."""
    path = make_ogg(str(tmp_path / "ep.ogg"), 2)
    downloader.set_metadata(path, parsed, image_bytes, "image/png")
    assert has_artwork(path)


@requires_ffmpeg
def test_set_metadata_handles_missing_artwork(tmp_path, image_bytes):
    """image=None must not crash and must leave no artwork behind."""
    parsed = make_parsed(image_url="")
    path = make_ogg(str(tmp_path / "ep.ogg"), 2)
    downloader.set_metadata(path, parsed, None, "")  # must not raise
    assert not has_artwork(path)
    # other tags still applied
    assert str(music_tag.load_file(path)["title"]) == "Optimo - 08.08.2023"


@requires_ffmpeg
@pytest.mark.parametrize("ext", [".ogg", ".m4a", ".mp3"])
def test_set_metadata_across_formats(tmp_path, parsed, image_bytes, ext):
    """Tags + artwork must land regardless of container (issue #48: episodes
    can come down as .m4a as well as .ogg)."""
    path = make_audio(str(tmp_path / f"ep{ext}"), 2)
    downloader.set_metadata(path, parsed, image_bytes, "image/png")

    f = music_tag.load_file(path)
    assert str(f["title"]) == "Optimo - 08.08.2023"
    assert str(f["artist"]) == "JD Twitch; JG Wilkes"
    assert has_artwork(path)
