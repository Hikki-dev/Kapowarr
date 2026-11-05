// Visual themes. One shared UI, five looks. Switching only changes the
// data-kp attribute and which stylesheet is loaded, so no page state is lost.
// Artwork lives in art/<theme>/<character>.jpg (see the Themes doc).
(function () {
	const base = () => document.querySelector('#url_base')?.dataset.value || '';
	const KEY = 'kp-theme';

	const THEMES = {
		classic: { name: 'Classic comic shop' },
		marvel: {
			name: 'Spider-Man + Iron Man',
			fonts: 'family=Rajdhani:wght@600;700',
			kicker: 'A Marvel collection',
			tagline: 'Your web of comics. Every issue wired in.',
			art: ['spider-man', 'iron-man']
		},
		dragonball: {
			name: 'Dragon Ball',
			fonts: 'family=Bowlby+One',
			kicker: 'Dragon Ball, Z and Super',
			tagline: 'Gather every issue and Shenron grants your wish.',
			art: ['shenron', 'goku', 'vegeta', 'gohan', 'piccolo', 'trunks', 'frieza', 'beerus', 'whis']
		},
		crossover: {
			name: 'Dragon Ball x Marvel x DC',
			fonts: 'family=Bangers',
			kicker: 'The Crossover Event',
			tagline: 'Three universes. One shelf.',
			art: ['goku', 'vegeta', 'shenron', 'spider-man', 'iron-man', 'captain-america', 'batman', 'superman', 'wonder-woman']
		},
		justice: {
			name: 'Justice League',
			fonts: 'family=Anton',
			kicker: 'Hall of Justice',
			tagline: 'Earth\'s greatest heroes, on your shelf.',
			art: ['batman', 'superman', 'wonder-woman', 'flash', 'aquaman', 'green-lantern', 'cyborg', 'martian-manhunter']
		},
		avengers: {
			name: 'Avengers',
			fonts: 'family=Oswald:wght@600&family=Comic+Neue:wght@700',
			kicker: 'Avengers Assemble',
			tagline: 'Earth\'s mightiest comics, collected.',
			art: ['iron-man', 'captain-america', 'thor', 'hulk', 'black-widow', 'hawkeye', 'spider-man', 'doctor-strange', 'black-panther']
		}
	};

	const get = () => {
		try { const t = localStorage.getItem(KEY); return THEMES[t] ? t : 'classic'; }
		catch (e) { return 'classic'; }
	};

	function link(id, href) {
		let l = document.getElementById(id);
		if (!l) { l = document.createElement('link'); l.id = id; l.rel = 'stylesheet'; document.head.appendChild(l); }
		if (l.getAttribute('href') !== href) l.setAttribute('href', href);
	}

	function apply(theme) {
		document.documentElement.dataset.kp = theme;
		const t = THEMES[theme];
		if (theme === 'classic') document.getElementById('kp-theme-css')?.remove();
		else link('kp-theme-css', `${base()}/static/css/themes/${theme}.css`);
		if (t.fonts) link('kp-theme-fonts', `https://fonts.googleapis.com/css2?${t.fonts}&display=swap`);
		else document.getElementById('kp-theme-fonts')?.remove();
		document.querySelectorAll('.kp-select').forEach(s => { s.value = theme; });
		buildHero();
	}

	function el(tag, cls, html) {
		const e = document.createElement(tag);
		if (cls) e.className = cls;
		if (html !== undefined) e.innerHTML = html;
		return e;
	}
	const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

	const art = (theme, name) => {
		const f = el('figure', 'kp-art');
		f.dataset.asset = `${theme}/${name}`;
		f.dataset.name = name;
		const img = el('img');
		img.src = `${base()}/art/${theme}/${name}`;
		img.alt = name.replace(/-/g, ' ');
		img.loading = 'lazy';
		f.appendChild(img);
		return f;
	};

	function switcher() {
		const header = document.querySelector('header');
		if (!header || header.querySelector('.kp-select')) return;
		const wrap = el('label', 'kp-switch');
		wrap.appendChild(el('span', null, 'Look'));
		const sel = el('select', 'kp-select');
		sel.setAttribute('aria-label', 'Change the look of Kapowarr');
		Object.entries(THEMES).forEach(([id, t]) => {
			const o = el('option'); o.value = id; o.textContent = t.name; sel.appendChild(o);
		});
		sel.value = get();
		sel.onchange = () => {
			try { localStorage.setItem(KEY, sel.value); } catch (e) { /* ignore */ }
			apply(sel.value);
		};
		wrap.appendChild(sel);
		header.appendChild(wrap);
	}

	let stats = null;
	function buildHero() {
		document.querySelectorAll('.kp-hero, .kp-rail').forEach(e => e.remove());
		const theme = get();
		const path = location.pathname.slice(base().length).replace(/\/+$/, '') || '/';
		const holder = document.querySelector('#library-container');
		if (theme === 'classic' || path !== '/' || !holder) return;
		const t = THEMES[theme];

		const hero = el('section', `kp-hero kp-hero-${theme}`);
		hero.setAttribute('aria-label', 'Featured');
		const text = el('div', 'kp-hero-text');
		text.appendChild(el('p', 'kp-kicker', esc(t.kicker)));
		text.appendChild(el('h1', 'kp-headline', 'Your collection'));
		const line = el('p', 'kp-stats', esc(t.tagline));
		line.id = 'kp-stats-line';
		text.appendChild(line);
		const feat = el('a', 'kp-feature', '');
		feat.id = 'kp-feature';
		feat.hidden = true;
		text.appendChild(feat);
		hero.appendChild(text);

		const stage = el('div', 'kp-stage');
		t.art.forEach(n => stage.appendChild(art(theme, n)));
		hero.appendChild(stage);

		if (theme === 'dragonball') {
			const balls = el('div', 'kp-balls');
			balls.setAttribute('aria-hidden', 'true');
			for (let i = 1; i <= 7; i++) balls.appendChild(el('i', null, String(i)));
			hero.appendChild(balls);
		}
		if (theme === 'marvel' || theme === 'avengers') {
			hero.appendChild(el('div', 'kp-reactor')).setAttribute('aria-hidden', 'true');
		}
		holder.insertBefore(hero, holder.firstChild);

		const rail = el('section', 'kp-rail');
		rail.setAttribute('aria-label', 'Recently added');
		rail.hidden = true;
		holder.insertBefore(rail, hero.nextSibling);
		fill(hero, rail);
	}

	function fill(hero, rail) {
		if (typeof usingApiKey !== 'function' || typeof fetchAPI !== 'function') return;
		usingApiKey(false).then(key => Promise.all([fetchAPI('/volumes', key), fetchAPI('/volumes/stats', key).catch(() => null)])
			.then(([vols, st]) => {
				const list = (vols.result || []).slice();
				if (!list.length) return;
				const have = list.reduce((a, v) => a + (v.issues_downloaded || 0), 0);
				const total = list.reduce((a, v) => a + (v.issue_count || 0), 0);
				const togo = Math.max(total - have, 0);
				hero.querySelector('#kp-stats-line').innerHTML =
					`<b>${list.length}</b> series &middot; <b>${have}</b> of <b>${total}</b> issues &middot; ${togo ? `<b>${togo}</b> still to get` : 'all collected'}`;
				const wanted = list.find(v => v.issue_count > v.issues_downloaded) || list[0];
				const f = hero.querySelector('#kp-feature');
				f.hidden = false;
				f.href = `${base()}/volumes/${wanted.id}`;
				f.innerHTML = `<span>Up next</span><strong>${esc(wanted.title)}</strong><em>${wanted.issues_downloaded} of ${wanted.issue_count} issues</em>`;
				const recent = list.sort((a, b) => b.id - a.id).slice(0, 8);
				rail.appendChild(el('h2', null, 'Recently added'));
				const row = el('div', 'kp-rail-row');
				recent.forEach(v => {
					const a = el('a', 'kp-tile');
					a.href = `${base()}/volumes/${v.id}`;
					a.innerHTML = `<img alt="" loading="lazy" src="${base()}/api/volumes/${v.id}/cover?api_key=${encodeURIComponent(key)}"><span>${esc(v.title)}</span>`;
					row.appendChild(a);
				});
				rail.appendChild(row);
				rail.hidden = false;
			})).catch(() => { });
	}

	function init() { switcher(); apply(get()); }
	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
	else init();
})();
