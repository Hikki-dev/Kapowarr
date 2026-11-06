# Folders: one library for comics, one for manga, more if you like

A root folder is a place where Kapowarr keeps series. Add as many as you like, for example `Comics`, `Manga` and `Manga 18+`, and point a separate Komga library at each.

## Add one

Settings, Media Management, **Add Root Folder**. Type the path. If the folder does not exist yet, Kapowarr creates it, as long as the folder above it exists (so a typo cannot build a whole new tree).

## Choose where a series goes

When you add a series you pick its root folder. Later, open the series and change its root folder: the files move there.

## No second copies

A move inside one drive should be a rename, not a copy. That only works when both folders are reached through the same mount. In Docker, mount the parent once and give the root folders paths below it:

    -v /mnt/Expansion:/library

Root folders: `/library/Comics`, `/library/Manga`, `/library/Manga 18+`. Two separate mounts of the same drive (`-v /mnt/Expansion/Comics:/comics -v /mnt/Expansion/Manga:/manga`) look like two drives to Docker, so a move between them is copied and then deleted.

Hardlinks (a second name for the same file, no extra space) need ext4, btrfs, xfs or NTFS. exFAT, the format of many external drives, cannot do them. On such a drive Kapowarr moves the file instead, so there is still only one copy.
