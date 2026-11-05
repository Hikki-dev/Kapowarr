# Troubleshooting

| What you see | Why | What to do |
|---|---|---|
| Kapowarr finds no comic when you add a series | No ComicVine key | Get a free key at comicvine.gamespot.com/api and paste it in Settings, General |
| `docker pull` says the image is denied | An old name was used | Use `ghcr.io/hikki-dev/kapowarr-fork:latest` (see [Upgrading](Upgrading.md)) |
| Prowlarr says "connection failed" | Wrong address or key | Use the address Kapowarr can reach. In Docker on one network, use the container name, not `localhost`. Copy the key again from Prowlarr, Settings, General |
| The Prowlarr search is slow | Prowlarr asks every site and one is slow | Disable slow sites in Prowlarr. A search is cut at 60 seconds and the answers that came in are kept |
| A torrent is added but never imported | Kapowarr cannot see qBittorrent's download folder | Mount the same folder at the same path in both containers (see [Prowlarr and torrents](Prowlarr%20and%20torrents.md)) |
| A torrent cannot be added | The link was not a torrent | Links of any kind are turned into magnet links; a file over 10 MB is ignored. Check the Kapowarr log for the exact reason |
| No message arrives | `KAPOWARR_NOTIFY_URL` is wrong or not set | The log says "The notification could not be sent". Check the URL, for ntfy use `https://ntfy.sh/your-topic`. See [Notifications, Komga and metrics](Notifications%20Komga%20and%20metrics.md) |
| Komga does not show a new comic | The scan was not asked for | Set `KAPOWARR_KOMGA_URL` and an API key (Komga, Account settings, API keys). `/api/system/metrics` shows `kapowarr_komga_scans` and `kapowarr_komga_scans_failed` |
| A comic uses twice the disk space | The download folder and the library are on different drives, so hardlinking is not possible and the file is copied | Put both on the same drive, or set the seeding handling so the download is removed after seeding |
| The Internet Archive finds nothing | The archive has no matching file | Try the title as it is written on the archive. Page images and text files are left out on purpose |
| Files in the library belong to root | `PUID` and `PGID` are `0` | Set them to your own ids (`id -u`, `id -g`) and restart |
| The container is `(unhealthy)` | The web page did not start | `docker logs kapowarr`. Look for a database error, and restore your backup if needed |
| An upgrade stops part-way | The database is damaged or from a very old version | Restore your backup and open an issue with the log lines |

Logs are in the container at `/app/logs`, or with `docker logs kapowarr`. Still stuck? [Open an issue](https://github.com/Hikki-dev/Kapowarr/issues) with the log lines and your version.
