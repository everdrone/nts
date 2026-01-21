import datetime
import json
import os
import os.path as osp
import re
import urllib

import ffmpeg
import music_tag
import requests
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from nts.utils import BrowserContext, PlaywrightContext, find_file, goto_retry


def get_image(image_url: str, dims="700x700"):
    image_type = ""
    image = None
    if image_url:
        if "ntslive.co.uk" in image_url:
            ## https://media3.ntslive.co.uk/resize/100x100/ab1af3ee-cae1-459b-9e81-5afec44f9ad3_1768348800.png
            ## https://media2.ntslive.co.uk/resize/800x800/ab1af3ee-cae1-459b-9e81-5afec44f9ad3_1768348800.png
            image_url = (
                f"https://media2.ntslive.co.uk/resize/{dims}/{image_url.split('/')[-1]}"
            )
        image = urllib.request.urlopen(image_url)
        image_type = image.info().get_content_type()  ## image/{format}
        # image_type = f"{osp.splitext(image_url)[-1]}"
        image = image.read()
        print(f"got {image_type} from {image_url}")
        return image, image_type.split("/")[-1]
    else:
        print("no image_url found")
        return None, ""


def download(url, quiet, save_dir, save=True, save_image: list = ["embd", "file"]):
    """
    save_image: "embd"-> sets artwork / "file" -> downloads into save_dir/file_name.{ext}
    """
    nts_url = url
    page = requests.get(url).content
    bs_data = BeautifulSoup(page, "html.parser")
    api_url = "https://nts.live/api/v2" + urllib.parse.urlparse(url).path
    api_data = requests.get(api_url).json()

    ntsp = NTSParser()
    ntsp.parse(bs_data, api_data)
    ntsp.data["url"] = nts_url

    # download
    if save:
        if not quiet:
            print(f"\ndownloading into: {save_dir}\n")

        ## ----------------------------------------------------------
        file_path_pattern = osp.join(save_dir, f"{ntsp.data['file_name']}.**")
        down = True
        already_down = find_file(file_path_pattern, ["audio", "video"])
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
            # try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([ntsp.data["link"]])
            # except DownloadError:
            #     print("got and 404 - skipping ")

        # get the downloaded file
        files = find_file(file_path_pattern, ["audio", "video"])
        if len(files) != 1:
            print(
                f"found already a file for: {ntsp.data['file_name']}\n\t{' , '.join(files)}"
            )
            breakpoint()
            return

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
                return

        set_metadata(file_path, ntsp.data, image)

        # down_img_from_url(
        #     url,
        #     save_dir,
        #     file_name,
        #     css_sel="div.profile-image.visible-desktop img.profile-image__img",
        # )  ##


class NTSParser:
    def __init__(self):
        self.data = {
            "filename": "",
            "url": "",
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

    def parse(self, bs_data, api_data):
        print(f"\n\n{'-' * 30}")

        # title data
        def unsafe_char(s):
            return re.sub(r"\/|\:", "-", s)

        self.data["title"] = api_data.get("name", "unknown")
        self.data["safe_title"] = unsafe_char(self.data["title"])

        self.data["artists"], self.data["parsed_artists"] = self._parse_artists(bs_data)

        self.data["station"] = api_data.get("location_long", "London")

        self.data["image_url"] = api_data.get("media", {}).get("picture_large", "")

        # sometimes it's just the date
        date = api_data.get("broadcast", "")
        self.data["date"] = datetime.datetime.fromisoformat(date)

        self.data["genres"] = list(
            filter(
                lambda x: x != "",
                map(lambda x: x.get("value", ""), api_data.get("genres", [])),
            )
        )

        self.data["tracks"] = self._parse_tracklist(api_data)

        self.data["description"] = api_data.get("description", "")

        self.data["link"] = self._get_link(api_data)

        self.data["file_name"] = (
            f"{self.data['safe_title']} - {self.data['date'].year}-{self.data['date'].month}-{self.data['date'].day}"
        )

        print(f"{self.data['file_name']} -- {self.data['link']}")
        print(f"{self.data}")
        breakpoint()

    def _parse_tracklist(self, api_data):
        tracks = api_data.get("embeds", {}).get("tracklist", {}).get("results", [])
        tracks = map(
            lambda x: {"name": x.get("title", ""), "artist": x.get("artist", "")},
            tracks,
        )
        return list(tracks)

    def _parse_artists(self, bs_data):
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
        # artists
        artists = []
        # TODO: figure out how to replace the code below (only thing keeping beautiful soup around)
        artist_box = bs_data.select(".bio-artists")
        if artist_box:
            artist_box = artist_box[0]
            for anchor in artist_box.find_all("a"):
                artists.append(anchor.text.strip())
        return artists, parsed_artists

    def _mixcloud_try(self):
        def get_suffix(day):
            if 10 <= day % 100 <= 20:
                suffix = "th"
            else:
                last_digit = day % 10
                if last_digit == 1:
                    suffix = "st"
                elif last_digit == 2:
                    suffix = "nd"
                elif last_digit == 3:
                    suffix = "rd"
                else:
                    suffix = "th"
            return suffix

        day = self.data["date"].strftime("%d")
        day += get_suffix(int(day))
        title = self.data["title"] + " - " + day + self.data["date"].strftime(" %B %Y")
        query = re.sub(r"[-/]", "", title)
        query = re.sub(r"\s+", "+", query)
        query = "https://api.mixcloud.com/search/?q=" + query + "&type=cloudcast"
        reply = requests.get(query)
        if reply.status_code != 200:
            return None
        reply = reply.json()["data"]
        reply = filter(lambda x: x["user"]["username"] == "NTSRadio", reply)
        for resp in reply:
            if resp["name"] == title:
                return resp["url"]
        return None

    def _get_link(self, api_data):
        # link = api_data.get("mixcloud", "") or api_data.get("audio_sources", [{"url": ""}])[
        #     0
        # ].get("url", "")
        # if "https://mixcloud" not in link:
        #     mixcloud_url = self._mixcloud_try()
        #     if mixcloud_url:
        #         link = mixcloud_url
        ## not sure whats for
        # if "https://mixcloud" in link:
        #     host = "mixcloud"
        # elif "https://soundcloud" in link:
        #     host = "soundcloud"

        link = api_data.get("mixcloud", "")
        if not link or requests.get(link).status_code != 200:
            print(f"mixcloud link none or 404 {link} ")
            link = api_data.get("audio_sources", [{"url": ""}])[0].get("url", "")
            if not link or requests.get(link).status_code != 200:
                print(f"audio_sources link none or 404 {link}")
                breakpoint()
        # print(f"mixcloud link succed {link} ")
        if "mixcloud.com" not in link:
            mixcloud_url = self._mixcloud_try()
            if mixcloud_url:
                link = mixcloud_url
                print(f"mixcloud_try succed {link}")

        return link


### ----------------------------------------------------------------
def get_episodes_of_show(show_name):
    offset = 0
    count = 0
    output = []
    while True:
        api_url = (
            f"https://www.nts.live/api/v2/shows/{show_name}/episodes?offset={offset}"
        )
        res = requests.get(api_url)
        try:
            res = res.json()
        except json.decoder.JSONDecodeError as e:
            print("error parsing api response json:", e)
            exit(1)
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


@PlaywrightContext(headless=False, slow_mo=150)
def get_my_favs(context: BrowserContext, url: str) -> list:
    print(url)

    favs_type = url.split("/")[-1]
    root = os.getenv("PIXI_PROJECT_ROOT")
    assert root
    favs_json = osp.join(root, f"data/nts_fav_{favs_type}.json")
    if osp.exists(favs_json):
        with open(favs_json) as f:
            all_links = json.load(f)
            # print(all_links)
        print(f"found data/my_{favs_type}.json")
        inp = input("update ? (y) ")
        if inp.lower() != "y":
            return all_links

    page = context.new_page()
    goto_retry(page, url)

    all_links = []
    previous_count = 0

    inp = input("login into nts , then continue (y) ")
    if inp != "y":
        return all_links

    while True:
        container = page.locator("div.my-nts__list-container")
        try:
            container.wait_for(state="visible", timeout=5000)
        except:
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
            if link_info and link_info["href"] not in [l["href"] for l in all_links]:
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
        except:
            print("No new items appeared after scrolling, stopping")
            break

    with open(favs_json, "w", encoding="utf-8") as f:
        json.dump(all_links, f, ensure_ascii=False, indent=2)
    print(f"{len(all_links)} {favs_type} saved to {favs_json}.")

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
