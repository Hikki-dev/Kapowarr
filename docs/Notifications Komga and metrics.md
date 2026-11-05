# Notifications, Komga and metrics

None of this needs a settings screen. Add the environment variable to the container, restart it, done. Nothing here can stop an import: every call runs in the background, has a 10 second limit, and a failure only writes a line to the log.

## Messages

Set `KAPOWARR_NOTIFY_URL`:

| You use | Set it to |
|---|---|
| ntfy | `https://ntfy.sh/your-topic` (or your own server's topic URL) |
| Discord | the webhook URL (Server settings, Integrations, Webhooks) |
| Anything else | any URL. It gets a JSON post: `{"title": "...", "message": "..."}` |

Three kinds of message are sent, like Sonarr and Radarr do:

| Message | When | Discord colour |
|---|---|---|
| Comic grabbed | A download starts | blue |
| Comic imported | The comic was downloaded and filed in your library | green |
| Download failed | A download could not finish | red |

On Discord each one is a small card with a coloured stripe.

## Komga

Set `KAPOWARR_KOMGA_URL` (for example `http://komga:25600`) and sign in with one of:

- `KAPOWARR_KOMGA_API_KEY`: create one in Komga under Account settings, API keys. This is the better choice.
- `KAPOWARR_KOMGA_USER` and `KAPOWARR_KOMGA_PASSWORD`.

After each import Kapowarr asks Komga to scan its libraries, so the comic shows up at once instead of at the next scheduled scan.

## Compose example

```yaml
    environment:
      - KAPOWARR_NOTIFY_URL=https://ntfy.sh/my-comics
      - KAPOWARR_KOMGA_URL=http://komga:25600
      - KAPOWARR_KOMGA_API_KEY=your-komga-key
```

## Hardlinks

`KAPOWARR_HARDLINK=0` turns hardlinking off. See [Prowlarr and torrents](Prowlarr%20and%20torrents.md).

## Metrics

`GET /api/system/metrics?api_key=YOUR_KEY` returns plain text that Prometheus, Homepage (custom API widget) or Beszel can read:

| Name | Meaning |
|---|---|
| `kapowarr_volumes` | Series in the library |
| `kapowarr_issues`, `kapowarr_issues_with_file` | Issues known, and those that have a file |
| `kapowarr_queue` | Downloads waiting or running |
| `kapowarr_prowlarr_searches`, `_cache_hits`, `_fallback_searches`, `_failures` | How Prowlarr searches went since the start |
| `kapowarr_prowlarr_last_search_seconds`, `_results` | Speed of the last search, and results found |
| `kapowarr_notifications_sent`, `_failed` | Messages that went out, and those that did not |
| `kapowarr_komga_scans`, `_failed` | Komga scans asked for |

The api key is the one in Kapowarr under Settings, General.
