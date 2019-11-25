# NTS Radio downloader

## Installation

First install all the requirements

```sh
pip3 install -r requirements.txt
```

## Usage

Just paste the show url and it will be downloaded in your Downloads folder at `~/Downloads`

```sh
python3 nts.py https://www.nts.live/shows/lee-gamble/episodes/lee-gamble-7th-october-2019
```

If you have multiple urls, write them into a file line by line and pass the file to the script

```sh
python3 nts.py links.txt
```
