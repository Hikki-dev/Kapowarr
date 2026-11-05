// Adds the "you are here" strip, and says how many issues are left.
// Pure decoration: if anything here fails, Kapowarr works exactly as before.
(function () {
	const base = () => document.querySelector('#url_base')?.dataset.value || '';
	const path = () => location.pathname.slice(base().length).replace(/\/+$/, '') || '/';

	const PAGES = {
		'/': ['My Shelf', 'Every comic you collect. Open one to see which issues you have and which are still to get.'],
		'/add': ['Find a Comic', 'Search for a series and add it to your shelf. Kapowarr then looks for its issues.'],
		'/library-import': ['Import', 'Bring in comics you already have on disk.'],
		'/extras': ['New This Week', 'What comes out this week, your pull list, requests and upgrades.'],
		'/activity/queue': ['Downloads', 'Comics being downloaded right now.'],
		'/activity/history': ['History', 'Everything that was downloaded before.'],
		'/activity/blocklist': ['Blocklist', 'Downloads you told Kapowarr never to use again.'],
		'/system/status': ['Status', 'Is everything working?'],
		'/system/tasks': ['Tasks', 'Jobs Kapowarr runs by itself, and when.'],
		'/system/backups': ['Backups', 'Copies of your Kapowarr settings and library list.'],
		'/settings/mediamanagement': ['Settings: Files', 'How comics are named and where they are kept.'],
		'/settings/indexers': ['Settings: Where to look', 'The places Kapowarr searches for comics.'],
		'/settings/download': ['Settings: Downloads', 'How downloads behave.'],
		'/settings/downloadclients': ['Settings: Download apps', 'Torrent apps such as qBittorrent.'],
		'/settings/metadata': ['Settings: Comic info', 'Where Kapowarr learns about comics (ComicVine).'],
		'/settings/general': ['Settings: General', 'Login, address and other basics.']
	};

	function el(tag, cls, text) {
		const e = document.createElement(tag);
		if (cls) e.className = cls;
		if (text !== undefined) e.textContent = text;
		return e;
	}

	function bar() {
		const p = path();
		const isVolume = /^\/volumes\/\d+$/.test(p);
		const [name, hint] = isVolume ? ['My Shelf', 'One series. The table lists every issue and whether you have it.'] : (PAGES[p] || [document.title.replace(/ - Kapowarr$/, ''), '']);
		const b = el('div', 'here-bar');
		b.setAttribute('role', 'navigation');
		b.setAttribute('aria-label', 'You are here');
		b.appendChild(el('span', 'here-tag', 'YOU ARE HERE'));
		if (isVolume) {
			const a = el('a', null, name);
			a.href = base() + '/';
			b.appendChild(a);
			b.appendChild(el('span', null, '›'));
			const crumb = el('span', 'here-crumb', 'Loading...');
			b.appendChild(crumb);
			const left = el('span', 'here-left hidden');
			b.appendChild(left);
			b.appendChild(el('span', 'here-hint', hint));
			return { b, crumb, left };
		}
		b.appendChild(el('span', null, name));
		if (hint) b.appendChild(el('span', 'here-hint', hint));
		return { b };
	}

	function volumeCounts(parts) {
		const id = path().split('/').pop();
		if (typeof usingApiKey !== 'function' || typeof fetchAPI !== 'function') return;
		usingApiKey(false).then(key => fetchAPI(`/volumes/${id}`, key)).then(j => {
			const v = j.result;
			const have = v.issues_downloaded, total = v.issue_count, togo = Math.max(total - have, 0);
			parts.crumb.textContent = `${v.title}${v.year ? ' (' + v.year + ')' : ''}`;
			parts.left.classList.remove('hidden');
			parts.left.textContent = togo ? `You have ${have} of ${total} issues · ${togo} still to get` : `You have all ${total} issues`;
			parts.left.className = 'here-left' + (togo ? '' : ' here-done');
		}).catch(() => { parts.crumb.textContent = 'Series'; });
	}

	function togoLabels() {
		document.querySelectorAll('.list-entry').forEach(entry => {
			const num = entry.querySelector('.list-prog-num');
			if (!num) return;
			const [have, total] = num.textContent.split('/').map(n => parseInt(n));
			if (isNaN(have) || isNaN(total)) return;
			let label = entry.querySelector('.list-togo');
			if (!label) {
				label = el('p', 'list-togo');
				entry.appendChild(label);
			}
			const togo = Math.max(total - have, 0);
			label.textContent = togo ? `${togo} still to get` : 'Complete';
			label.classList.toggle('done', togo === 0);
		});
	}

	function start() {
		const header = document.querySelector('header');
		if (!header || document.querySelector('.here-bar')) return;
		const parts = bar();
		header.insertAdjacentElement('afterend', parts.b);
		if (parts.left) volumeCounts(parts);
		if (path() === '/') {
			const lib = document.querySelector('#list-library');
			if (lib) {
				new MutationObserver(togoLabels).observe(lib, { childList: true, subtree: true, characterData: true });
				togoLabels();
			}
		}
	}

	if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
	else start();
})();
