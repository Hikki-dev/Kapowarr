# Extras: calendar, requests, upgrades, reading

Open **Extras** in the menu under Volumes. Everything on it uses what Kapowarr already has; there is nothing new to install.

## Calendar

* **In your library:** the issues of your series that go on sale in the chosen week, and whether you have them. This works without internet.
* **New series starting:** the number ones that go on sale that week, from ComicVine. If ComicVine is blocked or out of requests and Metron is set up (below), Metron answers instead. Press **Add and search** to add one.
* **Follow automatically:** add a **publisher** (it must match exactly, ignoring capitals, for example `Image`) or a **word in the title** (for example `Batman`). Once a day, new number ones that match are added to your first root folder, monitored, and searched for. A series is only ever followed once, and a message is sent if you have set up notifications. Without a watch list nothing is added by itself.

## Requests

Type your name (optional), search, and press **Request**. The series is added to your first root folder, monitored, and searched for. The list shows each request with who asked and how far it got: *Searching*, *Downloading*, *Partly there* or *Complete*. Anyone who can sign in to Kapowarr can use it.

## Upgrades

Needs a **format preference** in Settings, Media Management (for example `cbz, cbr, pdf`: the first is most wanted). The tab lists issues whose best file is in a less wanted format. **Look for better** runs a search and counts the results in a better format (it reads the format from the name or link of each result; results that do not say are not counted). Download the one you want from the volume page.

When the better file has arrived, the old one can be removed by itself. That is **off** by default. Set `KAPOWARR_UPGRADE_REMOVE_OLD=1` to switch it on. Only files in a less wanted format than the best file of the same issue are removed, and only when the best file's format is in your preference list.

## Reading

With Komga set up (`KAPOWARR_KOMGA_URL` and `KAPOWARR_KOMGA_API_KEY`, see [Notifications, Komga and metrics](Notifications%20Komga%20and%20metrics.md)) this tab shows, for every series that both apps have (matched by name, and by year when several share a name), how many issues you have read and how many are unread. A series with everything read is **caught up**. Every 30 minutes, caught-up series that still have monitored issues missing are searched for first.

## Metron (optional)

A free account on metron.cloud. Set `KAPOWARR_METRON_USER` and `KAPOWARR_METRON_PASSWORD`. It is only used for the calendar, and only when ComicVine fails. Metron series are linked to ComicVine through their `cv_id`; series without one cannot be added and are skipped.

## What was tested

The rules of every part run in offline checks on every change: weeks, watch list, follow, requests, format ranking, removing replaced files, Komga matching, Metron answers and the fallback. The Extras page and its endpoints were opened on a live server. Metron was not tried against the real service, because that needs an account.
