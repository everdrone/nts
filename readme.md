# NTS Radio downloader

Downloads [NTS](https://www.nts.live) episodes (with metadata) for offline listening.

<img src="https://i.postimg.cc/fRfNN8Y6/nts-header.png" />

## Installation

First install all the requirements.

```sh
pip3 install nts-everdrone
```

## Usage

```
Usage: nts [options] args

Options:
  -h, --help            show this help message and exit
  -o DIR, --out-dir=DIR
                        where the files will be downloaded, defaults to
                        ~/Downloads on macOS and %USERPROFILE%\Downloads
  -v, --version         print the version number and quit
  -q, --quiet           only print errors
```

Just paste the episode url and it will be downloaded in your Downloads folder.

```sh
nts https://www.nts.live/shows/myshow/episodes/myepisode
```

Alternatively, you can pass a show/host url to download all its episodes.

```sh
nts https://www.nts.live/shows/myshow
```

If you have multiple urls, write them into a file line by line and pass the file to the script.
Show urls will be expanded and downloaded as well.

```sh
nts links.txt
```

You can also pass files and urls (shows or episodes) at the same time

```sh
nts links.txt https://www.nts.live/shows/myshow
```

To change the output directory use the `--out-dir` option, or the `-o` shorthand

```sh
nts -o ~/Desktop/NTS links.txt
```
