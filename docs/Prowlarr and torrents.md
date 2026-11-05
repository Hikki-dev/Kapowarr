# Prowlarr and torrents

This fork can look for comics in three places. GetComics works as in the original. The other two are new.

## Prowlarr (torrents)

Prowlarr is the app that holds all your torrent sites. Kapowarr asks it once and gets answers from every site.

1. In Prowlarr, copy the API key (Settings, General).
2. In Kapowarr, open Settings, Indexers, and add **Prowlarr**. Enter its address (for example `http://prowlarr:9696` when both run in Docker on the same network) and the API key.
3. Press test. Kapowarr tells you if the address or the key is wrong.

How it searches: comics (category 7030) are asked first, so an answer comes in about ten seconds. Prowlarr may take up to 60 seconds in all, because it asks every site. Results that are not torrents are left out, and at most 100 are kept.

## qBittorrent (the download client)

Torrents need a download client. In Settings, Download Clients, add **qBittorrent** with its address, user name and password.

One thing matters: Kapowarr and qBittorrent must **see the download folder at the same path**. If qBittorrent saves to `/data/torrents`, then Kapowarr needs a mount that shows that folder at `/data/torrents` too (for example `-v /mnt/disk/torrents:/data/torrents`). Otherwise Kapowarr cannot find the finished file and cannot copy it into your library.

## Torrent links

Sites hand out three kinds of links: a magnet link, a link that leads to one, or the `.torrent` file itself. All three are turned into a magnet link, so qBittorrent can take them. A file bigger than 10 MB is ignored, because no real torrent file is that large.

## The Internet Archive

Add **Internet Archive** under Settings, Indexers. It needs no key. It finds public domain and archived comics and downloads the files directly. Titles such as "Batman: Year One" or "Saga (2012)" work. The page images and text files the archive makes by itself are left out.

## What was tested

A torrent link from Prowlarr was followed all the way: turned into a magnet link, accepted by qBittorrent and downloaded. What happens after the download finishes (copying the comic into the library) is the original's own part and was not run on a real comic torrent.
