"""Tests for the download() orchestration: multi-source fallback (#49),
de-duplication, albumize routing, and the webm->ogg conversion branch.

Network and yt-dlp are mocked, so these run without ffmpeg or connectivity.
"""

from unittest.mock import MagicMock

import pytest
from yt_dlp.utils import DownloadError

from nts import downloader

URL = "https://www.nts.live/shows/optimo/episodes/optimo-8th-august-2023"


def make_api(**over):
    api = {
        "name": "Optimo",
        "location_long": "Glasgow",
        "show_alias": "optimo",
        "broadcast": "2023-08-08T16:00:00+00:00",
        "description": "",
        "media": {"picture_large": ""},   # empty -> no artwork fetch (no urllib)
        "genres": [],
        "embeds": {"tracklist": {"results": []}},
        "mixcloud": "https://mixcloud/optimo",
        "audio_sources": [],
    }
    api.update(over)
    return api


class FakeResponse:
    def __init__(self, api):
        self.content = b"<html></html>"
        self._api = api

    def json(self):
        return self._api


class FakeRequests:
    """Stand-in for the requests module (download uses requests.get)."""
    def __init__(self, api):
        self._api = api

    def get(self, url):
        return FakeResponse(self._api)


def make_fake_ydl(attempted, ext="m4a"):
    """A YoutubeDL replacement that records attempts, fails on any link
    containing 'fail', and otherwise writes the expected output file."""
    class FakeYDL:
        def __init__(self, opts):
            self.opts = opts

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def download(self, links):
            link = links[0]
            attempted.append(link)
            if "fail" in link:
                raise DownloadError("simulated failure")
            open(self.opts["outtmpl"].replace("%(ext)s", ext), "w").close()

    return FakeYDL


@pytest.fixture
def patched(monkeypatch):
    """Patch requests + record set_metadata / set_metadata_album calls."""
    meta_calls, album_calls = [], []
    monkeypatch.setattr(downloader, "set_metadata",
                        lambda *a, **k: meta_calls.append(a))
    monkeypatch.setattr(downloader, "set_metadata_album",
                        lambda *a, **k: album_calls.append(a))
    return meta_calls, album_calls


def test_download_falls_back_to_second_source(tmp_path, monkeypatch, patched):
    meta_calls, _ = patched
    attempted = []
    api = make_api(mixcloud="https://mixcloud/fail",
                   audio_sources=[{"url": "https://host2/ok"}])
    monkeypatch.setattr(downloader, "requests", FakeRequests(api))
    monkeypatch.setattr(downloader, "YoutubeDL", make_fake_ydl(attempted))

    downloader.download(URL, quiet=True, save_dir=str(tmp_path), albumize=False)

    # first host failed, fell through to the second
    assert attempted == ["https://mixcloud/fail", "https://host2/ok"]
    assert len(meta_calls) == 1  # metadata applied once, on success


def test_download_all_sources_fail(tmp_path, monkeypatch, patched, capsys):
    meta_calls, _ = patched
    attempted = []
    api = make_api(mixcloud="https://mixcloud/fail1",
                   audio_sources=[{"url": "https://host/fail2"}])
    monkeypatch.setattr(downloader, "requests", FakeRequests(api))
    monkeypatch.setattr(downloader, "YoutubeDL", make_fake_ydl(attempted))

    parsed = downloader.download(URL, quiet=True, save_dir=str(tmp_path), albumize=False)

    assert attempted == ["https://mixcloud/fail1", "https://host/fail2"]
    assert meta_calls == []  # nothing downloaded -> no metadata
    assert isinstance(parsed, dict)
    assert "could not download" in capsys.readouterr().out


def test_download_dedupes_sources(tmp_path, monkeypatch, patched):
    attempted = []
    # same url appears as both mixcloud and an audio source
    api = make_api(mixcloud="https://host/dup-fail",
                   audio_sources=[{"url": "https://host/dup-fail"},
                                  {"url": "https://host/ok"}])
    monkeypatch.setattr(downloader, "requests", FakeRequests(api))
    monkeypatch.setattr(downloader, "YoutubeDL", make_fake_ydl(attempted))

    downloader.download(URL, quiet=True, save_dir=str(tmp_path), albumize=False)

    # the duplicate is attempted only once before moving on
    assert attempted == ["https://host/dup-fail", "https://host/ok"]


def test_download_routes_to_albumize(tmp_path, monkeypatch, patched):
    meta_calls, album_calls = patched
    attempted = []
    api = make_api(mixcloud="https://host/ok")
    monkeypatch.setattr(downloader, "requests", FakeRequests(api))
    monkeypatch.setattr(downloader, "YoutubeDL", make_fake_ydl(attempted))

    downloader.download(URL, quiet=True, save_dir=str(tmp_path), albumize=True)

    assert len(album_calls) == 1
    assert meta_calls == []


def test_download_converts_webm_to_ogg(tmp_path, monkeypatch, patched):
    meta_calls, _ = patched
    attempted = []
    api = make_api(mixcloud="https://host/ok")
    monkeypatch.setattr(downloader, "requests", FakeRequests(api))
    # source comes down as .webm -> should be converted before tagging
    monkeypatch.setattr(downloader, "YoutubeDL", make_fake_ydl(attempted, ext="webm"))
    fake_ffmpeg = MagicMock()
    monkeypatch.setattr(downloader, "ffmpeg", fake_ffmpeg)

    downloader.download(URL, quiet=True, save_dir=str(tmp_path), albumize=False)

    # ffmpeg was invoked to transcode, and metadata was applied to the .ogg
    assert fake_ffmpeg.input.called
    assert len(meta_calls) == 1
    assert meta_calls[0][0].endswith(".ogg")
    # the original .webm was cleaned up
    assert not any(p.suffix == ".webm" for p in tmp_path.iterdir())
