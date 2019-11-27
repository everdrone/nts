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


def download(url):
    nts_url = url
    page = requests.get(url).content
    bs = BeautifulSoup(page, 'html.parser')

    # guessing there is one
    title_box = bs.select('div.bio__title')[0]

    # textual data
    title = title_box.div.h1.text
    title = title.strip()

    # parse artists in the title
    parsed_artists = re.findall(
        '(?:w\/|with)(.+?)(?=and|,|&|\s-\s)', title, re.IGNORECASE)
    if not parsed_artists:
        parsed_artists = re.findall(
            '(?:w\/|with)(.+)', title, re.IGNORECASE)
    # strip all
    parsed_artists = [x.strip() for x in parsed_artists]
    # get other artists after the w/
    if parsed_artists:
        more_people = re.sub(
            '^.+?(?:w\/|with)(.+?)(?=and|,|&|\s-\s)', '', title, re.IGNORECASE)
        if not re.match('^\s*-\s', more_people):
            # split if separators are encountered
            more_people = re.split(',|and|&', more_people, re.IGNORECASE)
            # append to array
            if more_people:
                for mp in more_people:
                    mp.strip()
                    parsed_artists.append(mp)

    # remove unsafe characters for the FS
    safe_title = re.sub('\/|\:', '-', title)
    station = title_box.div.div.h2.find(text=True, recursive=False).strip()

    # sometimes it's just the date
    date = title_box.div.div.h2.span.text
    if ',' in date:
        date = date.split(',')[1].strip()
    else:
        date = date.strip()
    date = datetime.datetime.strptime(date, '%d.%m.%y')

    # artists
    artists = []
    artist_box = bs.select('.bio-artists')
    if artist_box:
        artist_box = artist_box[0]
        for anchor in artist_box.find_all('a'):
            artists.append(anchor.text.strip())

    # genres
    genres = []
    genres_box = bs.select('.episode-genres')[0]
    for anchor in genres_box.find_all('a'):
        genres.append(anchor.text.strip())

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

    button = bs.select('.episode__btn.mixcloud-btn')[0]
    link = button.get('data-src')
    match = re.match('https:\/\/www.mixcloud\.com\/NTSRadio.+$', link)

    # get album art
    page = requests.get(link).content
    bs = BeautifulSoup(page, 'html.parser')
    img = bs.select('div.album-art')[0].img
    srcset = img.get('srcset').split()
    img = srcset[-2].split(',')[1]

    file_name = f'{safe_title} - {date.year}-{date.month}-{date.day}'

    image = urllib.request.urlopen(img)
    image_type = image.info().get_content_type()
    image = image.read()

    print(f'\ndownloading into: {download_dir}\n')

    # download
    ydl_opts = {
        'outtmpl': os.path.join(download_dir, f'{file_name}.%(ext)s'),
    }
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        ydl.download([link])

    # get the downloaded file
    files = os.listdir(download_dir)
    for file in files:
        if file.startswith(file_name):
            # found
            print(f'adding metadata to {file} ...')
            audio = mutagen.File(os.path.join(download_dir, file))
            # title
            audio['\xa9nam'] = f'{title} - {date.day:02d}.{date.month:02d}.{date.year:02d}'
            # part of a compilation
            audio['cpil'] = True
            # album
            audio['\xa9alb'] = 'NTS'
            # artist
            if not artists:
                if parsed_artists:
                    audio['\xa9ART'] = "; ".join(parsed_artists)
            else:
                audio['\xa9ART'] = "; ".join(artists)
            # year
            audio['\xa9day'] = f'{date.year}'
            # comment
            audio['\xa9cmt'] = nts_url
            # genre
            audio['\xa9gen'] = genres[0]
            # cover
            match = re.match('jpe?g$', image_type)
            img_format = None
            if match:
                img_format = mutagen.mp4.AtomDataType.JPEG
            else:
                img_format = mutagen.mp4.AtomDataType.PNG
            cover = mutagen.mp4.MP4Cover(image, img_format)
            audio['covr'] = [cover]
            audio.save()


def main():
    show_regex = '.*nts\.live\/shows.+(\/episodes)\/.+'

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
