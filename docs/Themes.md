# Visual themes

Kapowarr ships with a classic comic-shop look and five themed looks. Pick one
from the **Look** menu in the top bar. The choice is remembered in your
browser and changes only the styling, so nothing you are doing is lost.

| Look | What it is |
| --- | --- |
| Classic comic shop | The default. Cream page, red header. |
| Spider-Man + Iron Man | Charcoal and web lines, red and blue, gold HUD edges, an arc reactor. |
| Dragon Ball | Night blue and orange, Shenron behind the title, seven Dragon Balls in the corner. |
| Dragon Ball x Marvel x DC | A crossover cover with three slanted columns, one per universe. |
| Justice League | Dark Watchtower, a full League lineup, blue, red and gold. |
| Avengers | A comic page: white gutters, caption boxes, red, gold and navy. |

On the shelf page the themed looks add a hero section, a "next up" link to the
first series that still has missing issues, and a "Recently added" row.

## Artwork

Kapowarr does **not** ship any character artwork. Marvel, DC and Dragon Ball
characters belong to their owners, so each artwork slot shows a labelled
placeholder until you add your own files.

Put images in one folder per theme, one file per character:

```
art/marvel/spider-man.jpg        art/justice/batman.jpg
art/marvel/iron-man.jpg          art/justice/superman.jpg
art/dragonball/shenron.png       art/avengers/thor.webp
...
```

`.webp`, `.jpg`, `.jpeg`, `.png` and `.avif` all work. The placeholder shows the
exact path it expects, for example `art/marvel/spider-man.jpg`.

By default Kapowarr reads `frontend/static/art` inside the container. To keep
your art outside the image, mount a folder and point Kapowarr at it:

```yaml
environment:
  - KAPOWARR_ART_DIR=/art
volumes:
  - /path/to/your/art:/art:ro
```

Character names per theme:

- `marvel`: spider-man, iron-man
- `dragonball`: shenron (the backdrop), goku, vegeta, gohan, piccolo, trunks, frieza, beerus, whis
- `crossover`: goku, vegeta, shenron, spider-man, iron-man, captain-america, batman, superman, wonder-woman
- `justice`: batman, superman, wonder-woman, flash, aquaman, green-lantern, cyborg, martian-manhunter
- `avengers`: iron-man, captain-america, thor, hulk, black-widow, hawkeye, spider-man, doctor-strange, black-panther

Use artwork you own or are licensed to use. Official comic or animated-series
art only; no live-action stills.

## For developers

- `frontend/static/js/themes.js` holds the theme list, the switcher and the hero.
- `frontend/static/css/themes/<theme>.css` is loaded only for the chosen look. Each file sets its own colour tokens, fonts, background and component styling under `html[data-kp="<theme>"]`.
- `frontend/ui.py` serves `/art/<theme>/<name>`.
- To add a theme: add an entry to `THEMES` in `themes.js`, add the id to the early loader list in `templates/base.html`, and add a stylesheet.
