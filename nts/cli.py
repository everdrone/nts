#!/usr/bin/env python3
import os
import re
import sys
from optparse import OptionParser
from nts import downloader as nts


def main():
    episode_regex = r'.*nts\.live\/shows.+(\/episodes)\/.+'
    show_regex = r'.*nts\.live\/shows\/([^/]+)$'

    # defaults to darwin
    download_dir = '~/Downloads'
    if sys.platform.startswith('win32'):
        download_dir = '%USERPROFILE%\\Downloads\\'
    # expand it
    download_dir = os.path.expanduser('~/Downloads')

    usage = "Usage: %prog [options] args"
    parser = OptionParser(usage=usage)
    parser.add_option("-o", "--out-dir", dest="output_directory", default=download_dir, action="store", type="string",
                      help="where the files will be downloaded, defaults to ~/Downloads on macOS and %USERPROFILE%\\Downloads", metavar="DIR")
    parser.add_option("-v", "--version", default=False,
                      dest="version", action="store_true",
                      help="print the version number and quit")
    parser.add_option("-q", "--quiet", default=False,
                      dest="quiet", action="store_true",
                      help="only print errors")

    (options, args) = parser.parse_args()

    if options.version:
        print(f'nts {nts.__version__}')
        exit(0)

    if len(args) < 1:
        print("please pass an URL or a file containing a list of urls.\n")
        parser.print_help()
        exit(1)

    download_dir = os.path.expanduser(options.output_directory)
    download_dir = os.path.abspath(options.output_directory)

    def url_matcher(url):
        if isinstance(url, str):
            url = url.strip()
            match_ep = re.match(episode_regex, url)
            match_sh = re.match(show_regex, url)

            if match_ep:
                nts.download(url=url, quiet=options.quiet,
                             save_dir=download_dir)
            elif match_sh:
                episodes = nts.get_episodes_of_show(match_sh.group(1))
                for ep in episodes:
                    url_matcher(ep)
            else:
                print(f'{url} is not an NTS url.\n')
                parser.print_help()
                exit(1)

    for arg in args:
        if os.path.isfile(arg):
            # check if file
            file = ""
            with open(arg, 'r') as f:
                file = f.read()
            lines = filter(None, file.split('\n'))
            for line in lines:
                url_matcher(line)
        else:
            url_matcher(arg)


if __name__ == '__main__':
    main()
