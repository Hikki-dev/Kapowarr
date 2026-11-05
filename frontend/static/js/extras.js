const E = id => document.querySelector(id);
let week = 0;

function cell(row, text, link) {
	const td = document.createElement('td');
	if (link) {
		const a = document.createElement('a');
		a.href = link; a.textContent = text; td.appendChild(a);
	} else td.textContent = text === null || text === undefined ? '' : text;
	row.appendChild(td);
	return td;
};

function button(text, onclick) {
	const b = document.createElement('button');
	b.textContent = text; b.onclick = onclick;
	return b;
};

function fill(tbody, rows) {
	tbody.replaceChildren();
	rows.forEach(r => tbody.appendChild(r));
	if (!rows.length) {
		const tr = document.createElement('tr');
		cell(tr, 'Nothing here yet');
		tbody.appendChild(tr);
	};
};

function loadCalendar(api_key) {
	fetchAPI('/extras/calendar', api_key, {week: week}).then(j => {
		E('#week-label').textContent = `${j.result.start} to ${j.result.end}`;
		fill(E('#cal-library'), j.result.releases.map(r => {
			const tr = document.createElement('tr');
			cell(tr, r.date);
			cell(tr, r.volume_title, `${url_base}/volumes/${r.volume_id}`);
			cell(tr, '#' + r.issue_number);
			cell(tr, r.has_file ? 'Downloaded' : (r.monitored ? 'Wanted' : 'Not monitored'));
			return tr;
		}));
	});
	E('#cal-new').replaceChildren();
	E('#cal-source').textContent = '(looking...)';
	fetchAPI('/extras/calendar/new', api_key, {week: week}).then(j => {
		E('#cal-source').textContent = j.result.series.length ? `(from ${j.result.source})` : '';
		fill(E('#cal-new'), j.result.series.map(s => {
			const tr = document.createElement('tr');
			cell(tr, s.store_date);
			cell(tr, `${s.title}${s.start_year ? ' (' + s.start_year + ')' : ''}`);
			cell(tr, s.publisher);
			const td = cell(tr, '');
			td.appendChild(s.in_library ? document.createTextNode('In library')
				: button('Add and search', () => requestSeries(api_key, s.comicvine_id, '', loadCalendar)));
			return tr;
		}));
	});
	loadWatchlist(api_key);
};

function loadWatchlist(api_key) {
	fetchAPI('/extras/watchlist', api_key).then(j => {
		const ul = E('#watchlist'); ul.replaceChildren();
		j.result.forEach(w => {
			const li = document.createElement('li');
			li.textContent = `${w.kind === 'publisher' ? 'Publisher' : 'Title contains'}: ${w.value} `;
			li.appendChild(button('Remove', () =>
				sendAPI('DELETE', '/extras/watchlist', api_key, {id: w.id}).then(() => loadWatchlist(api_key))));
			ul.appendChild(li);
		});
	});
};

function requestSeries(api_key, cv_id, name, after) {
	sendAPI('POST', '/extras/requests', api_key, {}, {comicvine_id: cv_id, requester: name})
		.then(() => after(api_key))
		.catch(() => alert('Could not add it. Check the Kapowarr log.'));
};

function loadRequests(api_key) {
	fetchAPI('/extras/requests', api_key).then(j => {
		fill(E('#req-list'), j.result.map(r => {
			const tr = document.createElement('tr');
			cell(tr, `${r.title}${r.year ? ' (' + r.year + ')' : ''}`, r.volume_id ? `${url_base}/volumes/${r.volume_id}` : null);
			cell(tr, r.requester);
			cell(tr, new Date(r.created_at * 1000).toLocaleDateString());
			cell(tr, `${r.status} (${r.downloaded}/${r.issues})`);
			return tr;
		}));
	});
};

function searchSeries(api_key) {
	const q = E('#req-query').value.trim();
	if (!q) return;
	fetchAPI('/volumes/search', api_key, {query: encodeURIComponent(q)}).then(j => {
		fill(E('#req-results'), j.result.slice(0, 15).map(v => {
			const tr = document.createElement('tr');
			cell(tr, v.title, v.issue_count ? null : null);
			cell(tr, v.year);
			cell(tr, v.publisher);
			const td = cell(tr, '');
			td.appendChild(v.already_added ? document.createTextNode('In library')
				: button('Request', () => requestSeries(api_key, v.comicvine_id, E('#req-name').value, a => { loadRequests(a); searchSeries(a); })));
			return tr;
		}));
	});
};

function loadUpgrades(api_key) {
	fetchAPI('/extras/upgrades', api_key).then(j => {
		const pref = j.result.preference;
		E('#upg-info').textContent = pref.length
			? `Format preference: ${pref.join(', ')}. These issues have a file in a less wanted format.`
			: 'Set a format preference in Settings, Media Management to find upgrades.';
		fill(E('#upg-list'), j.result.issues.map(i => {
			const tr = document.createElement('tr');
			cell(tr, i.volume_title, `${url_base}/volumes/${i.volume_id}`);
			cell(tr, '#' + i.issue_number);
			cell(tr, i.format);
			const td = cell(tr, '');
			td.appendChild(button('Look for better', e => {
				e.target.textContent = 'Searching...';
				sendAPI('POST', '/extras/upgrades/search', api_key, {}, {issue_id: i.issue_id})
					.then(r => r.json()).then(s => {
						const n = (s.result.results || []).length;
						e.target.textContent = n ? `${n} better found: open the volume to download` : 'Nothing better found';
					});
			}));
			return tr;
		}));
	});
};

function loadReading(api_key) {
	fetchAPI('/extras/reading', api_key).then(j => {
		E('#read-info').textContent = j.result.length
			? 'From Komga. Series you are caught up on are searched for new issues first.'
			: 'Komga is not set up (KAPOWARR_KOMGA_URL and KAPOWARR_KOMGA_API_KEY) or has none of these series.';
		fill(E('#read-list'), j.result.map(r => {
			const tr = document.createElement('tr');
			cell(tr, r.title, `${url_base}/volumes/${r.volume_id}`);
			cell(tr, `${r.read}/${r.komga_books}`);
			cell(tr, r.unread);
			cell(tr, r.caught_up ? 'Caught up' : 'Reading');
			return tr;
		}));
	});
};

usingApiKey().then(api_key => {
	const loaders = {calendar: loadCalendar, requests: loadRequests, upgrades: loadUpgrades, reading: loadReading};
	document.querySelectorAll('#extras-tabs button').forEach(b => b.onclick = () => {
		document.querySelectorAll('#extras-tabs button').forEach(x => x.classList.toggle('active', x === b));
		document.querySelectorAll('.tab').forEach(t => t.classList.toggle('hidden', t.id !== 'tab-' + b.dataset.tab));
		loaders[b.dataset.tab](api_key);
	});
	E('#week-prev').onclick = () => { week -= 1; loadCalendar(api_key); };
	E('#week-next').onclick = () => { week += 1; loadCalendar(api_key); };
	E('#watch-add').onclick = () => {
		const value = E('#watch-value').value.trim();
		if (!value) return;
		sendAPI('POST', '/extras/watchlist', api_key, {}, {kind: E('#watch-kind').value, value: value})
			.then(() => { E('#watch-value').value = ''; loadWatchlist(api_key); });
	};
	E('#req-search').onclick = () => searchSeries(api_key);
	E('#req-query').onkeydown = e => { if (e.key === 'Enter') searchSeries(api_key); };
	loadCalendar(api_key);
});
