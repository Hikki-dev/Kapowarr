# Upgrading

The database is upgraded by itself on the first start. Nothing else needs doing, but always keep a copy first.

## 1. Back up

```bash
docker run --rm -v kapowarr-db:/db -v "$PWD":/backup alpine cp /db/Kapowarr.db /backup/Kapowarr.db.backup
```

(Use your own volume name if it is not `kapowarr-db`.)

## 2. Switch to this image

Stop the old container, then start `ghcr.io/hikki-dev/kapowarr-fork:latest` on the **same** database volume and the same folders. With Compose, change the `image:` line and run `docker compose up -d`.

## From where

| You come from | What happens |
|---|---|
| The original Kapowarr (1.0.0 to 1.3.2) | Upgraded to this fork's database. Library, root folder and settings stay. The Internet Archive indexer is added |
| The earlier version of this copy | The database is bridged to the current numbering. Your Prowlarr settings become a Prowlarr indexer. qBittorrent and your library are kept |
| An older build of this fork | Upgraded in the usual way, one numbered step at a time |

Each of the original versions 1.0.0, 1.1.0, 1.2.0, 1.3.0, 1.3.1 and 1.3.2 was upgraded this way and came out with the library, root folder and settings intact, and a clean integrity check.

## Going back

Stop the container, put your backup file back as `Kapowarr.db` in the database volume, and start the old image. A database that was upgraded cannot be read by an older version, so always go back with the backup.

## The image name changed

Earlier builds were published as `ghcr.io/hikki-dev/kapowarr`. This fork publishes as `ghcr.io/hikki-dev/kapowarr-fork`, so its package belongs to this repository and is public. Change the name in your Compose file or run command. Nothing else changes.
