import datetime
import json
import os
import os.path as osp
import re
from urllib import parse as urllib_parse

import ffmpeg
import music_tag
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from nts.utils import ROOT_PATH, PlaywrightContext, find_file, get_image, safe_get


def download(
    url,
    quiet,
    save_dir,
    save=True,
    save_image: list = ["embd", "file"],
):
    """
    save_image: "embd"-> sets artwork / "file" -> downloads into save_dir/file_name.{ext}
    """

    ntsp = NTSParser(url)
    ntsp_req_suc = ntsp.request()
    if not ntsp_req_suc:
        print("NTSParser request failed")
        return False
    ntsp.parse()

    if not save:
        return False

    if not quiet:
        print(f"\ndownloading into: {save_dir}\n")

    ## ----------------------------------------------------------
    file_path_pattern = osp.join(save_dir, f"{ntsp.data['file_name']}.**")
    down = True
    already_down = find_file(
        file_path_pattern,
        ["audio", "video"],
    )
    if len(already_down) != 0:
        print(f"already got something {already_down}")
        inp = input("overwrite ? (y) ")
        if inp.lower() == "y":
            for f in already_down:
                print(f"removing {f}")
                os.remove(f)
        else:
            down = False
    ## ----------------------------------------------------------

    if down:
        ydl_opts = {
            "outtmpl": osp.join(save_dir, f"{ntsp.data['file_name']}.%(ext)s"),
            "quiet": quiet,
        }
        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([ntsp.data["link"]])
        except DownloadError as e:
            print(e)
            print("got and 404 - skipping ")

    # get the downloaded file
    files = find_file(file_path_pattern, ["audio", "video"])
    if len(files) != 1:
        print(
            f"found already a file for: {ntsp.data['file_name']}\n\t{' , '.join(files)}"
        )
        breakpoint()
        return False

    file = files[0]
    file_path = osp.join(save_dir, file)
    if not quiet:
        print(f"adding metadata to {file} ...")

    # .m4a and .mp3 use different methods
    file_ext = osp.splitext(file)[-1].lower()
    updt = False
    if file_ext == ".webm" or file_ext == ".opus":
        old_file_path = file_path
        file = ntsp.data["file_name"] + ".ogg"
        file_path = osp.join(save_dir, file)

        ## -------------------------------------
        # dst_path = AudiUtils.convert_cuntainer(
        #     file_path,
        #     "ogg",
        #     args=["-c:a", "copy"],
        # )
        # print(dst_path)
        # assert new_file_path == dst_path
        # file_path = new_file_path
        ## -------------------------------------

        ffmpeg.input(old_file_path).output(file_path, acodec="copy").run(
            overwrite_output=True
        )
        # os.remove(file_path)
        updt = True
        file_ext = ".ogg"

    ## --------------------------------------------------
    ## TODO: if only 'embd' & img already present -> rm ?
    image, image_type = get_image(ntsp.data["image_url"])
    if "file" in save_image and image:
        file_img = f"{ntsp.data['file_name']}.{image_type}"
        filepath_img = osp.join(save_dir, file_img)
        if not osp.exists(filepath_img):
            with open(filepath_img, "wb") as f:
                f.write(image)
            print(f"Image downloaded: {filepath_img}")
        else:
            print(f"Image exists: {filepath_img}")

    if "embd" not in save_image:
        image = None
    ## --------------------------------------------------

    if not down and not updt:
        inp = input("reset metadata ? (y) ")
        if inp.lower() != "y":
            return False

    set_metadata(file_path, ntsp.data, image)

    # down_img_from_url(
    #     url,
    #     save_dir,
    #     file_name,
    #     css_sel="div.profile-image.visible-desktop img.profile-image__img",
    # )  ##
    return True


class NTSParser:
    def __init__(self, url):
        self.url = url

        self.data = {
            "url": self.url,
            "safe_title": "",
            "date": None,
            "title": "",
            "artists": [],
            "parsed_artists": [],
            "genres": [],
            "station": "",
            "tracks": [],
            "image_url": "",
            "description": "",
            "link": "",
        }

    def request(self):
        result = safe_get(self.url)
        if not result.success:
            return None

        page = result.response.content
        self.bs_data = BeautifulSoup(page, "html.parser")

        self.api_url = "https://nts.live/api/v2" + urllib_parse.urlparse(self.url).path
        result = safe_get(self.api_url)
        if not result.success:
            return None
        self.api_data = result.response.json()

        self.api_show_url = ""
        for link_d in self.api_data.get("links"):
            if link_d["rel"] == "show":
                self.api_show_url = link_d["href"]
        assert self.api_show_url != self.api_url

        return True

    def parse(self):
        print(f"\n\n{'-' * 30}")

        # title data
        def unsafe_char(s):
            return re.sub(r"\/|\:", "-", s)

        self.data["title"] = self.api_data.get("name", "unknown")
        self.data["safe_title"] = unsafe_char(self.data["title"])

        self.data["artists"], self.data["parsed_artists"] = self._parse_artists()

        self.data["station"] = self.api_data.get("location_long", "London")

        self.data["image_url"] = self._get_image_url("medium_large")

        # sometimes it's just the date
        date = self.api_data.get("broadcast", "")
        self.data["date"] = datetime.datetime.fromisoformat(date)

        self.data["genres"] = list(
            filter(
                lambda x: x != "",
                map(lambda x: x.get("value", ""), self.api_data.get("genres", [])),
            )
        )

        self.data["tracks"] = self._parse_tracklist()

        self.data["description"] = self.api_data.get("description", "")

        self.data["link"] = self._get_link()

        self.data["file_name"] = (
            f"{self.data['safe_title']} - {self.data['date'].year}-{self.data['date'].month}-{self.data['date'].day}"
        )

        print(f"{self.data['file_name']} -- {self.data['link']}")
        print(f"{self.data}")

    def _get_image_url(self, size="medium_large"):
        size = f"picture_{size}"
        dims = {
            "picture_large": "1600x1600",
            "picture_medium_large": "800x800",
            "picture_medium": "400x400",
            "picture_small": "200x200",
            "picture_thumb": "100x100",
        }
        assert size in dims.keys()
        return self.api_data.get("media", {}).get(size, "")

    def _parse_tracklist(self):
        tracks = self.api_data.get("embeds", {}).get("tracklist", {}).get("results", [])
        tracks = map(
            lambda x: {"name": x.get("title", ""), "artist": x.get("artist", "")},
            tracks,
        )
        return list(tracks)

    def _parse_artists(self):
        assert self.data["title"]
        # parse artists in the title
        parsed_artists = re.findall(
            r"(?:w\/|with)(.+?)(?=\sand\s|,|&|\s-\s)", self.data["title"], re.IGNORECASE
        )
        if not parsed_artists:
            parsed_artists = re.findall(
                r"(?:w\/|with)(.+)", self.data["title"], re.IGNORECASE
            )
        # strip all
        parsed_artists = [x.strip() for x in parsed_artists]
        # get other artists after the w/
        if parsed_artists:
            more_people = re.sub(
                r"^.+?(?:w\/|with)(.+?)(?=\sand\s|,|&|\s-\s)",
                "",
                self.data["title"],
                re.IGNORECASE,
            )
            if more_people == self.data["title"]:
                # no more people
                more_people = ""
            if not re.match(r"^\s*-\s", more_people):
                # split if separators are encountered
                more_people = re.split(r",|\sand\s|&", more_people, re.IGNORECASE)
                # append to array
                if more_people:
                    for mp in more_people:
                        mp.strip()
                        parsed_artists.append(mp)
        parsed_artists = list(filter(None, parsed_artists))

        artists = []
        # TODO: figure out how to replace the code below (only thing keeping beautiful soup around)
        artist_box = self.bs_data.select(".bio-artists")
        if artist_box:
            artist_box = artist_box[0]
            for anchor in artist_box.find_all("a"):
                artists.append(anchor.text.strip())

        ## ------------------------------------------------
        # still using bs4, but with this logic
        # just a handfull of missing cases in 100+ö.....-ö
        if len(artists) == 0 and len(parsed_artists) == 0:
            _artists = []

            ## -----------------
            ## from show_alias
            show_alias = self.api_data.get("show_alias", "")
            if show_alias == "the-nts-guide-to":
                artists.append("NTS")
            else:
                show_alias = " ".join(
                    [a.lower().capitalize() for a in show_alias.split("-")]
                )
                _artists.append(show_alias)

                ## -----------------
                ## get the text above "See all episodes"
                link = self.bs_data.find("a", {"class": "bio__show-link"})
                if link:
                    container_div = link.find("div")
                    if container_div:
                        # First div child should be the show name
                        show_name_div = container_div.find("div")
                        if show_name_div:
                            _artists.append(show_name_div.get_text(strip=True))

                ## a match seems a strong indicator
                ## better take the one from html
                if len(_artists) == 2:
                    if _artists[0].lower() == _artists[1].lower():
                        artists.append(_artists[1])
                    elif (
                        _artists[0].replace(" ", "").lower()
                        in _artists[1].replace(" ", "").lower()
                    ):
                        artists.append(_artists[1])
                    elif (
                        _artists[1].replace(" ", "").lower()
                        in _artists[0].replace(" ", "").lower()
                    ):
                        artists.append(_artists[1])
                print(_artists)

            # if len(artists) == 0 and len(parsed_artists) == 0:
            #     print(_artists)
            #     tmp = self.api_data.copy()
            #     tmp.pop("embeds")
            #     # tmp["embeds"]["tracklist"].pop("results")
            #     print(tmp)
            #     breakpoint()

        return artists, parsed_artists

    def _mixcloud_api_try(self):
        def get_suffix(day):
            if 10 <= day % 100 <= 20:
                return "th"
            return {
                1: "st",
                2: "nd",
                3: "rd",
            }.get(day % 10, "th")

        day = self.data["date"].strftime("%d")
        day += get_suffix(int(day))
        title = self.data["title"] + " - " + day + self.data["date"].strftime(" %B %Y")
        query = re.sub(r"[-/]", "", title)
        query = re.sub(r"\s+", "+", query)
        query = "https://api.mixcloud.com/search/?q=" + query + "&type=cloudcast"
        result = safe_get(query)
        if not result.success:
            print(f"mixcloud_api failed {query}")
            return None
        reply = result.response.json()["data"]
        reply = filter(lambda x: x["user"]["username"] == "NTSRadio", reply)
        for resp in reply:
            if resp["name"] == title:
                return resp["url"]
        print(f"mixcloud_api failed {query}")
        return None

    def _get_link(self):
        link = self.api_data.get("mixcloud", "")
        result = safe_get(link)
        if not result.success:
            print(f"mixcloud link {result.status_code} ")
            mixcloud_url = self._mixcloud_api_try()
            if mixcloud_url:
                link = mixcloud_url
                print(f"mixcloud_api succed {link}")
            else:
                link = self.api_data.get("audio_sources", [{"url": ""}])[0].get(
                    "url", ""
                )
                result = safe_get(link)
                if not result.success:
                    print(f"audio_sources link {result.status_code}")
                    breakpoint()

        return link


## ----------------------------------------------------------------
def get_episodes_of_show(show_name):
    offset = 0
    count = 0
    output = []
    while True:
        api_url = (
            f"https://www.nts.live/api/v2/shows/{show_name}/episodes?offset={offset}"
        )
        result = safe_get(api_url)
        if not result.success:
            break
        try:
            res = result.response.json()
        except json.decoder.JSONDecodeError as e:
            print("error parsing api response json:", e)
            break

        if count == 0:
            count = int(res["metadata"]["resultset"]["count"])
        offset += int(res["metadata"]["resultset"]["limit"])
        if res["results"]:
            res = res["results"]
            for ep in res:
                if ep["status"] == "published":
                    alias = ep["episode_alias"]
                    output.append(
                        f"https://www.nts.live/shows/{show_name}/episodes/{alias}"
                    )
        if len(output) == count:
            break

    return output


def get_my_favs(url: str) -> list:
    pw = PlaywrightContext(
        headless=False,
        slow_mo=150,
        auth_filepath=osp.join(ROOT_PATH, "data/.nts_auth.json"),
        auth_login_url="https://www.nts.live/sign-in",
    )
    pw.__enter__()

    favs_type = url.split("/")[-1]
    favs_json = osp.join(ROOT_PATH, f"data/nts_fav_{favs_type}.json")
    if osp.exists(favs_json):
        with open(favs_json) as f:
            all_links = json.load(f)
            # print(all_links)
        print(f"found data/my_{favs_type}.json")
        inp = input("update ? (y) ")
        if inp.lower() != "y":
            return all_links

    page = pw.context.new_page()
    pw.goto_retry(page, url)

    all_links = []
    previous_count = 0
    while True:
        container = page.locator("div.my-nts__list-container")
        try:
            container.wait_for(state="visible", timeout=5000)
        except TimeoutError:
            print("Container not found, breaking")
            break

        items = page.locator("div.article-list-item")
        current_count = items.count()

        current_links = page.eval_on_selector_all(
            "div.article-list-item",
            """els => els.map(el => {
                const link = el.querySelector('a.nts-app.nts-link');
                if (!link) return null;

                return {
                    href: link.href,
                    title: link.querySelector('h2')?.textContent?.trim() || '',
                    date: link.querySelector('.article-list-item__content__top__subtitle')?.textContent?.trim() || ''
                };
            }).filter(Boolean)""",
        )

        for link_info in current_links:
            if link_info and link_info["href"] not in [
                link["href"] for link in all_links
            ]:
                all_links.append(link_info)

        print(f"Found {len(all_links)} unique links so far")

        if current_count <= previous_count:
            print("No more items loaded, stopping")
            break
        previous_count = current_count

        # Scroll to bottom to trigger more loading
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        try:
            page.wait_for_timeout(2000)
            page.locator("div.article-list-item").nth(current_count).wait_for(
                state="attached", timeout=5000
            )
        except TimeoutError:
            print("No new items appeared after scrolling, stopping")
            break

    if len(all_links):
        with open(favs_json, "w", encoding="utf-8") as f:
            json.dump(all_links, f, ensure_ascii=False, indent=2)
        print(f"\n{len(all_links)} {favs_type} saved to {favs_json}.")

    pw.__exit__()

    return all_links


### ----------------------------------------------------------------
def set_metadata(file_path, parsed, image):
    def get_title(parsed):
        return f"{parsed['title']} - {parsed['date'].day:02d}.{parsed['date'].month:02d}.{parsed['date'].year:02d}"

    def get_tracklist(parsed):
        return "\n".join(
            list(map(lambda x: f"{x['name']} by {x['artist']}", parsed["tracks"]))
        )

    def get_date(parsed):
        return f"{parsed['date'].date().isoformat()}"

    def get_genres(parsed):
        return "; ".join(parsed["genres"])

    def get_artists(parsed):
        join_artists = parsed["artists"] + parsed["parsed_artists"]
        all_artists = []
        presence_set = set()
        for aa in join_artists:
            al = aa.lower()
            if al not in presence_set:
                presence_set.add(al)
                all_artists.append(aa)
        return "; ".join(all_artists)

    def get_comment(parsed):
        comment = ""
        desc = parsed.get("description", "")
        if len(desc) > 0:
            comment = desc + "\n"
        comment += f"Station Location: {parsed['station']}\n"
        comment += parsed["url"]
        return comment

    ft = music_tag.load_file(file_path)
    assert ft, f"music_tag failed to load {file_path}"
    ft["title"] = get_title(parsed)
    ft["compilation"] = 1
    ft["album"] = "NTS"
    ft["artist"] = get_artists(parsed)
    ft.raw["year"] = get_date(parsed)
    ft["genre"] = get_genres(parsed)
    tracklist = get_tracklist(parsed)
    if tracklist:
        ft["lyrics"] = "Tracklist:\n" + get_tracklist(parsed)
    ft["comment"] = get_comment(parsed)
    if image:
        ft["artwork"] = image
    ft.save()
