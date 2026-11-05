# Extras: calendar, requests, upgrades, reading

Open **New This Week** in the menu (Library section). The page is called Extras in the code. Everything on it uses what Kapowarr already has; there is nothing new to install.

## Calendar

Choose **Day, Week, Month or Year**. The arrows (or the left and right arrow keys) move to the previous or next period, and **Today** comes back to now. Kapowarr remembers the view you chose. The full picture, with screenshots, is in [The interface](Interface.md).

* **In your library:** the issues of your series that come out in the period, and how each one stands: *Downloaded*, *Wanted* (already out and missing), *Not out yet* or *Not monitored*. This works without internet. An issue with no release date is not shown, because it has no day to sit on.
* **Coming up:** the next issue of each series that has a date, for the next month, 3 months, 6 months or year, with how far away it is. This is the quickest way to see what is coming this month, next month or in three months.
* **New series starting:** the number ones that come out in the period, from ComicVine. It asks ComicVine only when you press **Look up new series for this period**, so browsing the calendar never uses up your requests. It is not offered for the year view. If ComicVine is blocked or out of requests and Metron is set up (below), Metron answers instead. Press **Add and search** to add one.
* **Follow automatically:** the safest choice is a **series (exact name)**, such as `Absolute Batman`: only that title is followed (capitals and a year in brackets do not matter, and `Batman` or `Absolute Batman Special` are not matched). You can also add a **publisher** (it must match exactly, ignoring capitals, for example `Image`: everything that publisher starts) or a **word in the title** (for example `Batman`). Once a day, new number ones that match are added to your first root folder, monitored, and searched for. A series is only ever followed once, and a message is sent if you have set up notifications. Without a watch list nothing is added by itself.

## Requests

Type your name (optional), search, and press **Request**. The series is added to your first root folder, monitored, and searched for. The list shows each request with who asked and how far it got: *Searching*, *Downloading*, *Partly there* or *Complete*. Anyone who can sign in to Kapowarr can use it.

## Upgrades

Needs a **format preference** in Settings, Media Management (for example `cbz, cbr, pdf`: the first is most wanted). The tab lists issues whose best file is in a less wanted format. **Look for better** runs a search and counts the results in a better format (it reads the format from the name or link of each result; results that do not say are not counted). Download the one you want from the volume page.

When the better file has arrived, the old one can be removed by itself. That is **off** by default. Set `KAPOWARR_UPGRADE_REMOVE_OLD=1` to switch it on. Only files in a less wanted format than the best file of the same issue are removed, and only when the best file's format is in your preference list.

## Reading

With Komga set up (`KAPOWARR_KOMGA_URL` and `KAPOWARR_KOMGA_API_KEY`, see [Notifications, Komga and metrics](Notifications%20Komga%20and%20metrics.md)) this tab shows, for every series that both apps have (matched by name, and by year when several share a name), how many issues you have read and how many are unread. A series with everything read is **caught up**. Every 30 minutes, caught-up series that still have monitored issues missing are searched for first.

## Metron (optional)

A free account on metron.cloud. Set `KAPOWARR_METRON_API_KEY` (metron.cloud, your profile, API key). It is only used for the calendar, and only when ComicVine fails. Metron series are linked to ComicVine through their `cv_id`; series without one cannot be added and are skipped.

## What was tested

The rules of every part run in offline checks on every change: weeks, watch list, follow, requests, format ranking, removing replaced files, Komga matching, Metron answers and the fallback. The Extras page and its endpoints were opened on a live server. Metron was not tried against the real service, because that needs an account.
