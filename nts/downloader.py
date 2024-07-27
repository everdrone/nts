import datetime
import os
import re
import sys
import urllib
import json

import mutagen
import requests
from yt_dlp import YoutubeDL
from cssutils import parseStyle
from bs4 import BeautifulSoup

from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, COMM, USLT
from mutagen.mp4 import MP4

__version__ = '1.3.1'

# defaults to darwin
download_dir = '~/Downloads'
if sys.platform.startswith('win32'):
    download_dir = '%USERPROFILE\\Downloads\\'
# expand it
download_dir = os.path.expanduser('~/Downloads')

def get_suffix(day):
    if 10 <= day % 100 <= 20:
        suffix = 'th'
    else:
        last_digit = day % 10
        if last_digit == 1:
            suffix = 'st'
        elif last_digit == 2:
            suffix = 'nd'
        elif last_digit == 3:
            suffix = 'rd'
        else:
            suffix = 'th'
    return suffix

def mixcloud_try(parsed):
    day = parsed['date'].strftime('%d')
    day += get_suffix(int(day))
    title = parsed['title'] + ' - ' + day + parsed['date'].strftime(' %B %Y')
    query = re.sub(r'[-/]', '', title)
    query = re.sub(r'\s+', '+', query)
    query = "https://api.mixcloud.com/search/?q=" + query + "&type=cloudcast"
    reply = requests.get(query)
    if reply.status_code != 200:
        return None
    reply = reply.json()['data']
    reply = filter(lambda x: x['user']['username'] == 'NTSRadio', reply)
    for resp in reply:
        if resp['name'] == title:
            return resp['url']
    return None

def download(url, quiet, save_dir, save=True):
    nts_url = url
    page = requests.get(url).content
    bs = BeautifulSoup(page, 'html.parser')

    # guessing there is one
    parsed = parse_nts_data(bs)
    parsed['url'] = nts_url
    # safe_title, date, title, artists, parsed_artists, genres, image_url = parse_nts_data(bs)

    button = bs.select('.episode__btn.mixcloud-btn')[0]
    link = button.get('data-src')
    host = None

    if 'https://mixcloud' not in link:
        mixcloud_url = mixcloud_try(parsed)
        if mixcloud_url:
            link = mixcloud_url

    if 'https://mixcloud' in link:
        host = 'mixcloud'
    elif 'https://soundcloud' in link:
        host = 'soundcloud'

    # get album art. If the one on mixcloud is available, use it. Otherwise,
    # fall back to the nts website.
    page = requests.get(link).content
    bs = BeautifulSoup(page, 'html.parser')
    image_type = ''
    image = None

    if host == 'mixcloud' and len(bs.select('div.album-art')) != 0:
        img = bs.select('div.album-art')[0].img
        srcset = img.get('srcset').split()
        img = srcset[-2].split(',')[1]
        image = urllib.request.urlopen(img)
        image_type = image.info().get_content_type()
        image = image.read()
    elif host == 'soundcloud' and len(bs.select('span.image__full')) != 0:
        style = parseStyle(bs.select('.image__full')[0].get('style'))
        image = urllib.request.urlopen(style['background-image'])
        image_type = image.info().get_content_type()
        image = image.read()

    if image is None and len(parsed['image_url']) > 0:
        if '/resize/' in parsed['image_url']:
            # use a bigger image
            parsed['image_url'] = re.sub(r'/resize/\d+x\d+/',
                                         '/resize/1000x1000/',
                                         parsed['image_url'])
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
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([link])

        # get the downloaded file
        files = os.listdir(save_dir)
        for file in files:
            if file.startswith(file_name):
                # found
                if not quiet:
                    print(f'adding metadata to {file} ...')

                # .m4a and .mp3 use different methods
                _, file_ext = os.path.splitext(file)
                file_ext = file_ext.lower()

                if file_ext == '.m4a':
                    set_m4a_metadata(os.path.join(save_dir, file), parsed,
                                     image, image_type)
                elif file_ext == '.mp3':
                    set_mp3_metadata(os.path.join(save_dir, file), parsed,
                                     image, image_type)
                else:
                    print(
                        f'Cannot edit metadata for unknown file type {file_ext}'
                    )
    return parsed


def parse_nts_data(bs):
    # guessing there is one
    title_box = bs.select('div.bio__title')[0]

    # title data
    title, safe_title = parse_title(title_box)

    # parse artists in the title
    artists, parsed_artists = parse_artists(title, bs)

    station = title_box.div.div.h2.find(text=True, recursive=False)
    if not station:
        station = 'London'
    else:
        station = station.strip()

    # bg_tag = bs.select('section#bg[style]')
    bg_tag = bs.select('img.visible-desktop')[0]
    image_url = bg_tag.get('src') if bg_tag else ''

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
                tracks.append({'artist': artist, 'name': name})
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
    parsed_artists = re.findall(r'(?:w\/|with)(.+?)(?=and|,|&|\s-\s)', title,
                                re.IGNORECASE)
    if not parsed_artists:
        parsed_artists = re.findall(r'(?:w\/|with)(.+)', title, re.IGNORECASE)
    # strip all
    parsed_artists = [x.strip() for x in parsed_artists]
    # get other artists after the w/
    if parsed_artists:
        more_people = re.sub(r'^.+?(?:w\/|with)(.+?)(?=and|,|&|\s-\s)', '',
                             title, re.IGNORECASE)
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
        except json.decoder.JSONDecodeError as e:
            print('error parsing api response json:', e)
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
                        f'https://www.nts.live/shows/{show_name}/episodes/{alias}'
                    )
        if len(output) == count:
            break

    return output


def set_m4a_metadata(file_path, parsed, image, image_type):
    audio = MP4(file_path)

    audio[
        '\xa9nam'] = f'{parsed["title"]} - {parsed["date"].day:02d}.{parsed["date"].month:02d}.{parsed["date"].year:02d}'
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
    audio['\xa9cmt'] = parsed['url']
    # genre
    if len(parsed['genres']) != 0:
        audio['\xa9gen'] = parsed['genres'][0]
    # tracklist in lyrics
    if len(parsed['tracks']) != 0:
        tracklist = '\n'.join(list(map(lambda x: f'{x["name"]} by {x["artist"]}', parsed['tracks'])))
        tracklist = 'Tracklist:\n' + tracklist
        audio['\xa9lyr'] = tracklist
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


def set_mp3_metadata(file_path, parsed, image, image_type):
    audio = mutagen.File(file_path, easy=True)

    audio[
        'title'] = f'{parsed["title"]} - {parsed["date"].day:02d}.{parsed["date"].month:02d}.{parsed["date"].year:02d}'
    audio['compilation'] = '1'  # True
    audio['album'] = 'NTS'

    # add artist string
    join_artists = parsed['artists'] + parsed['parsed_artists']
    all_artists = []
    presence_set = set()
    for aa in join_artists:
        al = aa.lower()
        if al not in presence_set:
            presence_set.add(al)
            all_artists.append(aa)
    audio['artist'] = "; ".join(all_artists)
    audio['date'] = str(parsed['date'].year)

    # add first genre
    if len(parsed['genres']) != 0:
        audio['genre'] = parsed['genres'][0]
    audio.save()

    # add cover
    audio = ID3(file_path)
    if audio.getall('APIC'):
        audio.delall('APIC')
    if image_type != '':
        audio.add(
            APIC(encoding=3,
                 mime=image_type,
                 type=3,
                 desc=u'Cover',
                 data=image))

    # add comment
    audio.delall('COMM')
    audio['COMM'] = COMM(encoding=0,
                         lang='eng',
                         desc=u'',
                         text=[parsed['url']])

    # add tracklist to lyrics
    tracklist = '\n'.join(list(map(lambda x: f'{x["name"]} by {x["artist"]}', parsed['tracks'])))

    if tracklist:
        audio.delall('USLT')
        audio['USLT'] = (USLT(encoding=3, lang='eng', desc=u'Tracklist', text=tracklist))

    audio.save()


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
