#!/usr/bin/env python3
import os.path as osp
import re
import sys

import click

from nts.downloader import download, get_episodes_of_show, get_my_favs

## -----------------------------------------------------------------
EPISODE_REGEX = r'.*nts\.live\/shows.+(\/episodes)\/.+'
SHOW_REGEX = r'.*nts\.live\/shows\/([^/]+)$'
# MY_REGEX = r".*nts\.live\/my-nts(?:\/.*)?$"
## --------------------
# defaults to darwin
download_dir_dflt = '~/Downloads'
if sys.platform.startswith('win32'):
    download_dir_dflt = '%USERPROFILE%\\Downloads\\'
download_dir_dflt = osp.expanduser('~/Downloads')
## --------------------


@click.command()
@click.argument(
    'args',
    nargs=-1,
    # required=True,
)
@click.option(
    '--out-dir',
    '-o',
    'output_directory',
    default=download_dir_dflt,
    type=str,
    help='where the files will be downloaded, defaults to ~/Downloads on macOS and %USERPROFILE%\\Downloads',
    metavar='DIR',
)
@click.option(
    '--parse-only',
    '-p',
    'parse_only',
    is_flag=True,
    show_default=True,
    default=False,
    help='only parse, no download',
)
@click.option(
    '--quiet',
    '-q',
    is_flag=True,
    show_default=True,
    default=False,
    help='only print errors',
)
@click.option(
    '--my-episodes',
    '-mye',
    'my_episodes',
    is_flag=True,
    show_default=True,
    default=False,
    help='reads from my_episodes.json if present or directly from https://www.nts.live/my-nts/favourites/episodes',
)
@click.option(
    '--my-shows',
    '-mys',
    'my_shows',
    is_flag=True,
    show_default=True,
    default=False,
    help='reads from my_shows.json if present or directly from https://www.nts.live/my-nts/favourites/shows',
)
@click.version_option()
def main(
    args,
    output_directory,
    quiet,
    parse_only,
    my_episodes,
    my_shows,
):
    """pass an URL or a file containing a list of urls"""

    download_dir = osp.abspath(osp.expanduser(output_directory))

    def url_matcher(url):
        if isinstance(url, str):
            url = url.strip()
            match_ep = re.match(EPISODE_REGEX, url)
            match_sh = re.match(SHOW_REGEX, url)

            if match_ep:
                _ = download(
                    url=url,
                    quiet=quiet,
                    save=not parse_only,
                    save_dir=download_dir,
                    save_image=['embd'],  ## file
                )

            elif match_sh:
                episodes = get_episodes_of_show(match_sh.group(1))
                for ep in episodes:
                    url_matcher(ep)

            else:
                print(f'{url} is not an NTS url.\n')
                raise ValueError(f'Invalid NTS URL: {url}')

    ## -----------------------------
    if my_episodes:
        episodes = get_my_favs('https://www.nts.live/my-nts/favourites/episodes')
        # { "href": "..", "title": "..","date": "22 Apr 2024",}
        download_dir = osp.join(download_dir, 'myeps')
        for ep in episodes:
            url_matcher(ep['href'])

    if my_shows:
        shows = get_my_favs('https://www.nts.live/my-nts/favourites/shows')
        # { "href": "..", "title": "..","date": "22 Apr 2024",}
        download_dir = osp.join(download_dir, 'myshows')
        for show in shows:
            url_matcher(show['href'])
    ## -----------------------------

    download_dir = osp.abspath(osp.expanduser(output_directory))
    for arg in args:
        if osp.isfile(arg):
            file = ''
            with open(arg, 'r') as f:
                file = f.read()
            lines = filter(None, file.split('\n'))
            for line in lines:
                url_matcher(line)
        else:
            url_matcher(arg)


if __name__ == '__main__':
    main()
