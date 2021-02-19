import datetime
import os
import re
import sys
import urllib
import json

import mutagen
import requests
import youtube_dl
from bs4 import BeautifulSoup


__version__ = '1.1.6'


# defaults to darwin
download_dir = '~/Downloads'
if sys.platform.startswith('win32'):
    download_dir = '%USERPROFILE\\Downloads\\'
# expand it
download_dir = os.path.expanduser('~/Downloads')


def download(url, quiet, save_dir, save=True):
    nts_url = url
    page = requests.get(url).content
    bs = BeautifulSoup(page, 'html.parser')

    # guessing there is one
    parsed = parse_nts_data(bs)
    # safe_title, date, title, artists, parsed_artists, genres, image_url = parse_nts_data(bs)

    button = bs.select('.episode__btn.mixcloud-btn')[0]
    link = button.get('data-src')
    match = re.match(r'https:\/\/www.mixcloud\.com\/NTSRadio.+$', link)

    # get album art. If the one on mixcloud is available, use it. Otherwise,
    # fall back to the nts website.
    page = requests.get(link).content
    bs = BeautifulSoup(page, 'html.parser')
    image_type = ''
    if len(bs.select('div.album-art')) != 0:
        img = bs.select('div.album-art')[0].img
        srcset = img.get('srcset').split()
        img = srcset[-2].split(',')[1]
        image = urllib.request.urlopen(img)
        image_type = image.info().get_content_type()
        image = image.read()
    elif len(parsed["image_url"]):
        image = urllib.request.urlopen(parsed["image_url"])
        image_type = image.info().get_content_type()
        image = image.read()

    file_name = f'{parsed["safe_title"]} - {parsed["date"].year}-{parsed["date"].month}-{parsed["date"].day}'

    # download
    if save:
        if not quiet:
            print(f'\ndownloading into: {save_dir}\n')
        ydl_opts = {
            'outtmpl': os.path.join(save_dir, f'{file_name}.%(ext)s'),
            'quiet': quiet
        }
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([link])

        # get the downloaded file
        files = os.listdir(save_dir)
        for file in files:
            if file.startswith(file_name):
                # found
                if not quiet:
                    print(f'adding metadata to {file} ...')
                audio = mutagen.File(os.path.join(save_dir, file))
                # title
                audio['\xa9nam'] = f'{parsed["title"]} - {parsed["date"].day:02d}.{parsed["date"].month:02d}.{parsed["date"].year:02d}'
                # part of a compilation
                audio['cpil'] = True
                # album
                audio['\xa9alb'] = 'NTS'
                # artist
                join_artists = parsed['artists'] + parsed['parsed_artists']
                all_artists = []
                presence_set = set()
                for aa in join_artists:
                    al = aa.lower()
                    if al not in presence_set:
                        presence_set.add(al)
                        all_artists.append(aa)
                # add to output data
                parsed['all_artists'] = all_artists
                # add to file metadata
                audio['\xa9ART'] = "; ".join(all_artists)
                # year
                audio['\xa9day'] = f'{parsed["date"].year}'
                # comment
                audio['\xa9cmt'] = nts_url
                # genre
                if len(parsed['genres']) != 0:
                    audio['\xa9gen'] = parsed['genres'][0]
                # cover
                if image_type != '':
                    match = re.match(r'jpe?g$', image_type)
                    img_format = None
                    if match:
                        img_format = mutagen.mp4.AtomDataType.JPEG
                    else:
                        img_format = mutagen.mp4.AtomDataType.PNG
                    cover = mutagen.mp4.MP4Cover(image, img_format)
                    audio['covr'] = [cover]
                audio.save()
    return parsed


def parse_nts_data(bs):
    # guessing there is one
    title_box = bs.select('div.bio__title')[0]

    # title data
    title, safe_title = parse_title(title_box)

    # parse artists in the title
    artists, parsed_artists = parse_artists(title, bs)

    station = title_box.div.div.h2.find(text=True, recursive=False).strip()

    bg_tag = bs.select('section#bg[style]')
    background_image_regex = r'background-image:url\((.*)\)'
    image_url = re.match(background_image_regex,
                         bg_tag[0]['style']).groups()[0]

    # sometimes it's just the date
    date = title_box.div.div.h2.span.text
    if ',' in date:
        date = date.split(',')[1].strip()
    else:
        date = date.strip()
    date = datetime.datetime.strptime(date, '%d.%m.%y')

    # genres
    genres = parse_genres(bs)

    # tracklist
    tracks = parse_tracklist(bs)
    return {
        'safe_title': safe_title,
        'date': date,
        'title': title,
        'artists': artists,
        'parsed_artists': parsed_artists,
        'genres': genres,
        'station': station,
        'tracks': tracks,
        'image_url': image_url,
    }


def parse_tracklist(bs):
    # tracklist
    tracks = []
    tracks_box = bs.select('.tracklist')[0]
    if tracks_box:
        tracks_box = tracks_box.ul
        if tracks_box:
            tracks_list = tracks_box.select('li.track')
            for track in tracks_list:
                artist = track.select('.track__artist')[0].text.strip()
                name = track.select('.track__title')[0].text.strip()
                tracks.append({
                    'artist': artist,
                    'name': name
                })
    return tracks


def parse_genres(bs):
    # genres
    genres = []
    genres_box = bs.select('.episode-genres')[0]
    for anchor in genres_box.find_all('a'):
        genres.append(anchor.text.strip())
    return genres


def parse_artists(title, bs):
    # parse artists in the title
    parsed_artists = re.findall(
        r'(?:w\/|with)(.+?)(?=and|,|&|\s-\s)', title, re.IGNORECASE)
    if not parsed_artists:
        parsed_artists = re.findall(
            r'(?:w\/|with)(.+)', title, re.IGNORECASE)
    # strip all
    parsed_artists = [x.strip() for x in parsed_artists]
    # get other artists after the w/
    if parsed_artists:
        more_people = re.sub(
            r'^.+?(?:w\/|with)(.+?)(?=and|,|&|\s-\s)', '', title, re.IGNORECASE)
        if more_people == title:
            # no more people
            more_people = ''
        if not re.match(r'^\s*-\s', more_people):
            # split if separators are encountered
            more_people = re.split(r',|and|&', more_people, re.IGNORECASE)
            # append to array
            if more_people:
                for mp in more_people:
                    mp.strip()
                    parsed_artists.append(mp)
    parsed_artists = list(filter(None, parsed_artists))
    # artists
    artists = []
    artist_box = bs.select('.bio-artists')
    if artist_box:
        artist_box = artist_box[0]
        for anchor in artist_box.find_all('a'):
            artists.append(anchor.text.strip())
    return artists, parsed_artists


def parse_title(title_box):
    title = title_box.div.h1.text
    title = title.strip()

    # remove unsafe characters for the FS
    safe_title = re.sub(r'\/|\:', '-', title)
    return title, safe_title


def get_episodes_of_show(show_name):
    offset = 0
    count = 0
    output = []
    while True:
        api_url = f'https://www.nts.live/api/v2/shows/{show_name}/episodes?offset={offset}'
        res = requests.get(api_url)
        try:
            res = res.json()
        except:
            print('error parsing api response json')
            exit(1)
        if count == 0:
            count = int(res['metadata']['resultset']['count'])
        offset += int(res['metadata']['resultset']['limit'])
        if res['results']:
            res = res['results']
            for ep in res:
                if ep['status'] == 'published':
                    alias = ep['episode_alias']
                    output.append(
                        f'https://www.nts.live/shows/{show_name}/episodes/{alias}')
        if len(output) == count:
            break

    return output


def main():
    episode_regex = r'.*nts\.live\/shows.+(\/episodes)\/.+'
    show_regex = r'.*nts\.live\/shows\/([^/]+)$'

    if len(sys.argv) < 2:
        print("please pass an URL or a file containing a list of urls.")
        exit(1)

    arg = sys.argv[1]
    line = arg

    match_episode = re.match(episode_regex, line)
    match_show = re.match(show_regex, line)

    lines = []

    if match_episode:
        lines += line.strip()
    elif match_show:
        lines += get_episodes_of_show(match_show.group(1))

    if os.path.isfile(arg):
        # read list
        file = ""
        with open(arg, 'r') as f:
            file = f.read()
        lines = filter(None, file.split('\n'))

    if len(lines) == 0:
        print('Didn\'t find shows to download.')
        exit(1)

    for line in lines:
        download(line, False, download_dir)


if __name__ == "__main__":
    main()
