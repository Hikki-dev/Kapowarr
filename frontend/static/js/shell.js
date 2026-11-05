// Page titles and hints, the first-run checklist, "missing" counts, the
// series summary, activity tabs and the phone menu. Everything here only adds
// information; if it fails, Kapowarr works exactly as before.
(function () {
	const base = () => document.querySelector('#url_base')?.dataset.value || '';
	const path = () => location.pathname.slice(base().length).replace(/\/+$/, '') || '/';

	const PAGES = {
		'/': ['Series', 'Every comic you collect, and how complete each one is.'],
		'/add': ['Add Series', 'Search for a comic and add it to your shelf.'],
		'/library-import': ['Import', 'Bring in comics you already have on disk.'],
		'/extras': ['New This Week', 'New releases, your auto-follow list, requests and upgrades.'],
		'/activity/queue': ['Queue', 'What is downloading right now.'],
		'/activity/history': ['History', 'Everything that was downloaded before.'],
		'/activity/blocklist': ['Blocklist', 'Releases you told Kapowarr never to use again.'],
		'/system/status': ['Status', 'Is everything working?'],
		'/system/tasks': ['Tasks', 'Jobs Kapowarr runs by itself, and when.'],
		'/system/backups': ['Backups', 'Copies of your settings and library list.'],
		'/settings/mediamanagement': ['Media Management', 'How comics are named and where they are kept.'],
		'/settings/indexers': ['Indexers', 'The places Kapowarr searches for comics.'],
		'/settings/download': ['Downloads', 'How downloads behave.'],
		'/settings/downloadclients': ['Download Clients', 'Torrent apps such as qBittorrent.'],
		'/settings/metadata': ['Metadata', 'Where Kapowarr learns about comics (ComicVine).'],
		'/settings/general': ['General', 'Login, address and other basics.']
	};

	const el = (tag, cls, text) => {
		const e = document.createElement(tag);
		if (cls) e.className = cls;
		if (text !== undefined) e.textContent = text;
		return e;
	};
	const ico = name => {
		const s = el('span', 'ico');
		s.setAttribute('aria-hidden', 'true');
		s.style.setProperty('--i', `url('${base()}/static/img/ui/${name}.svg')`);
		return s;
	};
	const api = (endpoint) => (typeof usingApiKey === 'function' && typeof fetchAPI === 'function')
		? usingApiKey(false).then(key => key ? fetchAPI(endpoint, key) : Promise.reject('no key'))
		: Promise.reject('no api');

	function heading() {
		const p = path();
		const isVolume = /^\/volumes\/\d+$/.test(p);
		const info = PAGES[p] || (isVolume ? ['Series', ''] : null);
		const t = document.querySelector('.page-title'), h = document.querySelector('.page-hint');
		if (info && t) t.textContent = info[0];
		if (info && h) h.textContent = info[1];
		if (isVolume) volumePage(t, h);
	}

	// Series page: show the name, and a plain have / missing / total strip.
	function volumePage(title, hint) {
		const id = path().split('/').pop();
		const apply = v => {
			title.textContent = `${v.title}${v.year ? ' (' + v.year + ')' : ''}`;
			hint.textContent = '';
			document.title = `${v.title} - Kapowarr`;
			const holder = document.querySelector('.volume-info-container');
			if (!holder || holder.querySelector('.volume-stats')) return;
			const have = v.issues_downloaded, total = v.issue_count, miss = Math.max(total - have, 0);
			const strip = el('div', 'volume-stats');
			[['Have', have, ''], ['Missing', miss, miss ? 'bad' : 'good'], ['In the run', total, '']].forEach(([k, n, c]) => {
				const d = el('div');
				d.appendChild(el('b', null, k));
				d.appendChild(el('span', c, String(n)));
				strip.appendChild(d);
			});
			const tags = holder.querySelector('#volume-tags');
			(tags || holder.lastChild).insertAdjacentElement('afterend', strip);
		};
		api(`/volumes/${id}`).then(j => apply(j.result)).catch(() => { });
	}

	// Poster cards: "3 missing" / "Complete" next to the count.
	function labels() {
		document.querySelectorAll('.list-entry').forEach(entry => {
			const box = entry.querySelector('.list-prog-container');
			const num = entry.querySelector('.list-prog-num');
			if (!box || !num) return;
			const [have, total] = num.textContent.split('/').map(n => parseInt(n));
			if (isNaN(have) || isNaN(total)) return;
			let label = box.querySelector('.list-togo');
			if (!label) { label = el('span', 'list-togo'); box.appendChild(label); }
			const miss = Math.max(total - have, 0);
			// Only write when something changed, or the observer would loop.
			const text = miss ? `${miss} missing` : 'Complete';
			const cls = 'list-togo ' + (!miss ? 'done' : have === 0 ? 'none' : 'todo');
			if (label.textContent !== text) label.textContent = text;
			if (label.className !== cls) label.className = cls;
			const shown = `${have} / ${total}`;
			if (num.textContent !== shown) num.textContent = shown;
		});
	}

	// First run: say exactly what is still needed.
	function checklist() {
		const holder = document.querySelector('main');
		if (!holder || document.querySelector('.setup-card')) return;
		Promise.all([api('/rootfolder'), api('/settings'), api('/externalclients')]).then(([rf, st, cl]) => {
			const steps = [
				[(rf.result || []).length > 0, 'Root folder', '/settings/mediamanagement'],
				[!!(st.result || {}).comicvine_api_key, 'ComicVine key', '/settings/metadata'],
				[(cl.result || []).length > 0, 'Download client (for torrents)', '/settings/downloadclients']
			];
			const missing = steps.filter(s => !s[0]);
			if (!missing.length || document.querySelector('.setup-card')) return;
			const card = el('section', 'setup-card');
			card.setAttribute('aria-label', 'Setup');
			const t = el('div');
			t.appendChild(el('strong', null, 'Finish setting up'));
			t.appendChild(el('span', 'sub', 'These are the things Kapowarr still needs before it can find comics.'));
			card.appendChild(t);
			steps.forEach(([ok, name, href]) => {
				const a = el('a', 'setup-step' + (ok ? ' done' : ''));
				a.href = base() + href;
				a.appendChild(ico(ok ? 'check_circle_fill' : 'radio_button_unchecked'));
				a.appendChild(document.createTextNode(name));
				card.appendChild(a);
			});
			const go = el('a', 'setup-go', 'Set up now');
			go.href = base() + missing[0][2];
			card.appendChild(go);
			const bar = holder.querySelector('.tool-bar-container');
			if (bar) bar.insertAdjacentElement('afterend', card); else holder.insertBefore(card, holder.firstChild);
		}).catch(() => { });
	}

	// Queue, History and Blocklist read as one place.
	function tabs() {
		const p = path();
		if (!p.startsWith('/activity/')) return;
		const row = el('nav', 'tabs-row');
		row.setAttribute('aria-label', 'Activity');
		[['Queue', '/activity/queue'], ['History', '/activity/history'], ['Blocklist', '/activity/blocklist']].forEach(([n, h]) => {
			const a = el('a', p === h ? 'on' : '', n);
			a.href = base() + h;
			row.appendChild(a);
		});
		const main = document.querySelector('main');
		if (main) main.insertAdjacentElement('afterbegin', row);
	}

	function queueBadge() {
		const b = document.querySelector('#queue-badge');
		if (!b) return;
		api('/activity/queue').then(j => {
			const n = (j.result || []).length;
			b.textContent = String(n);
			b.classList.toggle('hidden', n === 0);
		}).catch(() => { });
	}

	function emptyState() {
		const e = document.querySelector('#empty-library');
		if (!e || e.querySelector('a')) return;
		e.classList.add('empty-state-wrap');
		e.innerHTML = '';
		const box = el('div', 'empty-state');
		box.appendChild(el('h2', null, 'Your shelf is empty'));
		box.appendChild(el('p', null, 'Add a comic and Kapowarr will find its issues, download them and keep them organised.'));
		const a = el('a', 'setup-go', 'Add your first series');
		a.href = base() + '/add';
		box.appendChild(a);
		e.appendChild(box);
	}

	function start() {
		heading();
		emptyState();
		tabs();
		queueBadge();
		setInterval(queueBadge, 15000);
		document.querySelector('#tabbar-more')?.addEventListener('click', () => document.querySelector('#toggle-nav')?.click());
		if (path() === '/') {
			const lib = document.querySelector('#list-library');
			if (lib) {
				new MutationObserver(labels).observe(lib, { childList: true, subtree: true, characterData: true });
				labels();
			}
			checklist();
		}
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
