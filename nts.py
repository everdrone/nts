import datetime
import os
import re
import sys
import urllib

import mutagen
import requests
import youtube_dl
from bs4 import BeautifulSoup

download_dir = os.path.expanduser('~/Downloads')


def download(url, save=True, save_dir=download_dir):
    nts_url = url
    page = requests.get(url).content
    bs = BeautifulSoup(page, 'html.parser')

    # guessing there is one
    parsed = parse_nts_data(bs)
    # safe_title, date, title, artists, parsed_artists, genres = parse_nts_data(bs)

    button = bs.select('.episode__btn.mixcloud-btn')[0]
    link = button.get('data-src')
    match = re.match(r'https:\/\/www.mixcloud\.com\/NTSRadio.+$', link)

    # get album art
    page = requests.get(link).content
    bs = BeautifulSoup(page, 'html.parser')
    img = bs.select('div.album-art')[0].img
    srcset = img.get('srcset').split()
    img = srcset[-2].split(',')[1]

    file_name = f'{parsed["safe_title"]} - {parsed["date"].year}-{parsed["date"].month}-{parsed["date"].day}'

    image = urllib.request.urlopen(img)
    image_type = image.info().get_content_type()
    image = image.read()

    # download
    if save:
        print(f'\ndownloading into: {save_dir}\n')
        ydl_opts = {
            'outtmpl': os.path.join(save_dir, f'{file_name}.%(ext)s'),
        }
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            ydl.download([link])

        # get the downloaded file
        files = os.listdir(save_dir)
        for file in files:
            if file.startswith(file_name):
                # found
                print(f'adding metadata to {file} ...')
                audio = mutagen.File(os.path.join(save_dir, file))
                # title
                audio['\xa9nam'] = f'{parsed["title"]} - {parsed["date"].day:02d}.{parsed["date"].month:02d}.{parsed["date"].year:02d}'
                # part of a compilation
                audio['cpil'] = True
                # album
                audio['\xa9alb'] = 'NTS'
                # artist
                if not parsed['artists']:
                    if parsed['parsed_artists']:
                        audio['\xa9ART'] = "; ".join(parsed['parsed_artists'])
                else:
                    audio['\xa9ART'] = "; ".join(parsed['artists'])
                # year
                audio['\xa9day'] = f'{parsed["date"].year}'
                # comment
                audio['\xa9cmt'] = nts_url
                # genre
                audio['\xa9gen'] = parsed['genres'][0]
                # cover
                match = re.match(r'jpe?g$', image_type)
                img_format = None
                if match:
                    img_format = mutagen.mp4.AtomDataType.JPEG
                else:
                    img_format = mutagen.mp4.AtomDataType.PNG
                cover = mutagen.mp4.MP4Cover(image, img_format)
                audio['covr'] = [cover]
                audio.save()


def parse_nts_data(bs):
    # guessing there is one
    title_box = bs.select('div.bio__title')[0]

    # title data
    title, safe_title = parse_title(title_box)

    # parse artists in the title
    artists, parsed_artists = parse_artists(title, bs)

    station = title_box.div.div.h2.find(text=True, recursive=False).strip()

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
        'tracks': tracks
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
        if not re.match(r'^\s*-\s', more_people):
            # split if separators are encountered
            more_people = re.split(r',|and|&', more_people, re.IGNORECASE)
            # append to array
            if more_people:
                for mp in more_people:
                    mp.strip()
                    parsed_artists.append(mp)
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


def main():
    show_regex = r'.*nts\.live\/shows.+(\/episodes)\/.+'

    if len(sys.argv) < 2:
        print("please pass an URL or a file containing a list of urls.")
        exit(1)
    arg = sys.argv[1]
    if os.path.isfile(arg):
        # read list
        file = ""
        with open(arg, 'r') as f:
            file = f.read()
        lines = filter(None, file.split('\n'))
        for line in lines:
            match = re.match(show_regex, line)
            if match:
                download(line.strip())
            else:
                print(f'{line} is not an NTS url.')
    else:
        match = re.match(show_regex, arg)
        if match:
            download(arg.strip())
        else:
            print(f'{arg} is not an NTS url.')
            exit(1)


if __name__ == "__main__":
    main()
