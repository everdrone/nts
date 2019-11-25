import re
import os
import requests
import urllib
import datetime
import sys
from bs4 import BeautifulSoup
import youtube_dl
import mutagen

download_dir = os.path.expanduser('~/Downloads')


def download(url):
    nts_url = url
    page = requests.get(url).content
    bs = BeautifulSoup(page, 'html.parser')

    # guessing there is one
    title_box = bs.select('div.bio__title')[0]
    # textual data
    title = title_box.div.h1.text
    station = title_box.div.div.h2.find(text=True, recursive=False).strip()
    date = title_box.div.div.h2.span.text.split(',')[1].strip()
    date = datetime.datetime.strptime(date, '%d.%m.%y')
    # artists
    artists = []
    artist_box = bs.select('.bio-artists')[0]
    for anchor in artist_box.find_all('a'):
        artists.append(anchor.text.strip())

    # genres
    genres = []
    genres_box = bs.select('.episode-genres')[0]
    for anchor in genres_box.find_all('a'):
        genres.append(anchor.text)
    # tracklist
    tracks = []
    tracks_box = bs.select('.tracklist')[0]
    tracks_box = tracks_box.ul
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

    file_name = f'{title} - {date.year}-{date.month}-{date.day}'

    image = urllib.request.urlopen(img)
    image_type = image.info().get_content_type()
    image = image.read()

    print(f'\ndownloading into: {download_dir}\n')

    ydl_opts = {
        'outtmpl': os.path.join(download_dir, f'{title} - {date.year}-{date.month}-{date.day}.%(ext)s'),
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
            # album
            audio['\xa9alb'] = 'NTS'
            # artist
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
