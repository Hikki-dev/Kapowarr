// The release calendar: Day, Week, Month and Year, a "coming up" list, and new
// series. It reads release dates the library already knows (the server does
// the date maths), so it works without internet. Helpers E, cell, button,
// fill, requestSeries and loadWatchlist come from extras.js.

const CAL = {
	view: 'month',
	anchor: null,
	api_key: null,
	upcoming_months: 3,
};

const STATE_WORDS = {
	downloaded: 'Downloaded',
	wanted: 'Wanted',
	upcoming: 'Not out yet',
	unmonitored: 'Not monitored',
};

const MS_DAY = 86400000;

// ---- Dates (always whole days, in the viewer's own calendar) ----
function isoDay(d) {
	const m = String(d.getMonth() + 1).padStart(2, '0'), day = String(d.getDate()).padStart(2, '0');
	return `${d.getFullYear()}-${m}-${day}`;
};

function parseDay(iso) {
	const [y, m, d] = iso.split('-').map(Number);
	return new Date(y, m - 1, d);
};

function addDays(iso, n) {
	const d = parseDay(iso);
	d.setDate(d.getDate() + n);
	return isoDay(d);
};

function formatDay(iso, opts) {
	return parseDay(iso).toLocaleDateString(undefined, opts);
};

function relativeDays(n) {
	if (n === 0) return 'today';
	if (n === 1) return 'tomorrow';
	if (n < 14) return `in ${n} days`;
	if (n < 60) return `in ${Math.round(n / 7)} weeks`;
	return `in ${Math.round(n / 30.4)} months`;
};

function periodLabel(r) {
	const long = {year: 'numeric', month: 'long'};
	if (r.view === 'day') return formatDay(r.start, {weekday: 'long', day: 'numeric', month: 'long', year: 'numeric'});
	if (r.view === 'week') return `${formatDay(r.start, {day: 'numeric', month: 'short'})} to ${formatDay(r.end, {day: 'numeric', month: 'short', year: 'numeric'})}`;
	if (r.view === 'month') return formatDay(r.start, long);
	return String(parseDay(r.start).getFullYear());
};

// ---- Small builders ----
function node(tag, cls, text) {
	const e = document.createElement(tag);
	if (cls) e.className = cls;
	if (text !== undefined) e.textContent = text;
	return e;
};

function stateChip(state) {
	return node('span', `state state-${state}`, STATE_WORDS[state]);
};

function releaseLink(r, cls) {
	const a = node('a', cls, `${r.volume_title} #${r.issue_number}`);
	a.href = `${url_base}/volumes/${r.volume_id}`;
	a.title = `${r.volume_title} #${r.issue_number}: ${STATE_WORDS[r.state]}`;
	return a;
};

function emptyNote(text) {
	return node('p', 'cal-empty', text);
};

// ---- Views ----
function renderMonth(r) {
	const holder = node('div', 'cal-month-holder');
	const wrap = node('div', 'cal-month');
	holder.appendChild(wrap);
	['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].forEach(n => wrap.appendChild(node('div', 'cal-dow', n)));
	const byDay = groupByDay(r.releases);
	for (let day = r.grid_start; day <= r.grid_end; day = addDays(day, 1)) {
		const items = byDay[day] || [];
		const cellEl = node('div', 'cal-day');
		if (day < r.start || day > r.end) cellEl.classList.add('other');
		if (day === r.today) cellEl.classList.add('today');
		const num = node('button', 'cal-num', String(parseDay(day).getDate()));
		num.title = `Open ${formatDay(day, {weekday: 'long', day: 'numeric', month: 'long'})}`;
		num.onclick = () => setView('day', day);
		cellEl.appendChild(num);
		items.slice(0, 3).forEach(i => cellEl.appendChild(releaseLink(i, `cal-item state-${i.state}`)));
		if (items.length > 3) {
			const more = node('button', 'cal-more', `+${items.length - 3} more`);
			more.onclick = () => setView('day', day);
			cellEl.appendChild(more);
		};
		wrap.appendChild(cellEl);
	};
	if (!r.releases.length) holder.appendChild(emptyNote('Nothing is scheduled this month. Release dates show up here once ComicVine knows them.'));
	return holder;
};

function groupByDay(releases) {
	const out = {};
	releases.forEach(i => (out[i.date] = out[i.date] || []).push(i));
	return out;
};

function dayTable(items) {
	const table = node('table', 'cal-table');
	const body = node('tbody');
	items.forEach(i => {
		const tr = node('tr');
		cell(tr, i.volume_title, `${url_base}/volumes/${i.volume_id}`);
		cell(tr, '#' + i.issue_number);
		tr.appendChild(node('td')).appendChild(stateChip(i.state));
		body.appendChild(tr);
	});
	table.appendChild(body);
	return table;
};

function renderWeek(r) {
	const wrap = node('div', 'cal-week');
	const byDay = groupByDay(r.releases);
	for (let day = r.start; day <= r.end; day = addDays(day, 1)) {
		const row = node('section', 'cal-week-day');
		if (day === r.today) row.classList.add('today');
		const head = node('button', 'cal-week-head', formatDay(day, {weekday: 'long', day: 'numeric', month: 'short'}));
		head.onclick = () => setView('day', day);
		row.appendChild(head);
		const items = byDay[day] || [];
		row.appendChild(items.length ? dayTable(items) : node('p', 'cal-none', 'Nothing out'));
		wrap.appendChild(row);
	};
	return wrap;
};

function renderDay(r) {
	const wrap = node('div', 'cal-dayview');
	wrap.appendChild(r.releases.length ? dayTable(r.releases) : emptyNote('Nothing comes out on this day.'));
	return wrap;
};

function renderYear(r) {
	const wrap = node('div', 'cal-year');
	const year = parseDay(r.start).getFullYear();
	r.months.forEach(m => {
		const tile = node('button', 'cal-tile');
		if (year === parseDay(r.today).getFullYear() && m.month === parseDay(r.today).getMonth() + 1) tile.classList.add('today');
		tile.appendChild(node('strong', null, new Date(year, m.month - 1, 1).toLocaleDateString(undefined, {month: 'long'})));
		tile.appendChild(node('span', 'cal-tile-total', m.total ? `${m.total} ${m.total === 1 ? 'issue' : 'issues'}` : 'No releases'));
		const parts = [];
		if (m.downloaded) parts.push(`${m.downloaded} downloaded`);
		if (m.wanted) parts.push(`${m.wanted} wanted`);
		if (m.upcoming) parts.push(`${m.upcoming} not out yet`);
		if (m.unmonitored) parts.push(`${m.unmonitored} not monitored`);
		if (parts.length) tile.appendChild(node('small', null, parts.join(' · ')));
		tile.onclick = () => setView('month', `${year}-${String(m.month).padStart(2, '0')}-01`);
		wrap.appendChild(tile);
	});
	return wrap;
};

// ---- Loading ----
function setView(view, anchor) {
	CAL.view = view;
	if (anchor) CAL.anchor = anchor;
	try { localStorage.setItem('kapowarr-cal-view', view); } catch (e) { /* private mode */ }
	loadCalendar(CAL.api_key);
};

function loadCalendar(api_key) {
	CAL.api_key = api_key;
	const today = isoDay(new Date());
	if (!CAL.anchor) {
		let saved = null;
		try { saved = localStorage.getItem('kapowarr-cal-view'); } catch (e) { /* ignore */ }
		if (['day', 'week', 'month', 'year'].includes(saved)) CAL.view = saved;
		CAL.anchor = today;
	};
	document.querySelectorAll('#cal-views button').forEach(b => {
		b.classList.toggle('on', b.dataset.view === CAL.view);
		b.setAttribute('aria-pressed', b.dataset.view === CAL.view);
	});
	const body = E('#cal-body');
	body.setAttribute('aria-busy', 'true');
	fetchAPI('/extras/calendar', api_key, {view: CAL.view, date: CAL.anchor, today: today}).then(j => {
		const r = j.result;
		CAL.prev = r.prev;
		CAL.next = r.next;
		E('#cal-label').textContent = periodLabel(r);
		const views = {day: renderDay, week: renderWeek, month: renderMonth, year: renderYear};
		body.replaceChildren(views[r.view](r));
		body.removeAttribute('aria-busy');
		E('#cal-legend').classList.toggle('hidden', r.view === 'year');
	}).catch(() => {
		body.replaceChildren(emptyNote('The calendar could not be loaded. Check the Kapowarr log.'));
		body.removeAttribute('aria-busy');
	});
	loadUpcoming(api_key);
	resetNew();
	loadWatchlist(api_key);
};

function loadUpcoming(api_key) {
	const list = E('#up-list');
	fetchAPI('/extras/calendar/upcoming', api_key, {months: CAL.upcoming_months, today: isoDay(new Date())}).then(j => {
		const r = j.result;
		list.replaceChildren();
		if (!r.next_per_series.length) {
			list.appendChild(emptyNote(`Nothing is dated in the next ${CAL.upcoming_months} ${CAL.upcoming_months === 1 ? 'month' : 'months'}. Dates appear once ComicVine knows them.`));
			return;
		};
		r.next_per_series.forEach(i => {
			const li = node('li', 'up-item');
			li.appendChild(releaseLink(i, 'up-title'));
			li.appendChild(node('span', 'up-date', formatDay(i.date, {weekday: 'short', day: 'numeric', month: 'short', year: 'numeric'})));
			li.appendChild(node('span', 'up-when', relativeDays(i.days_away)));
			li.appendChild(stateChip(i.state));
			list.appendChild(li);
		});
		if (r.truncated) list.appendChild(emptyNote('Only the first releases are listed. Narrow the range to see the rest.'));
	}).catch(() => list.replaceChildren(emptyNote('Could not load what is coming up.')));
};

// ---- New series (asks ComicVine, so only when asked) ----
function resetNew() {
	E('#cal-new').replaceChildren();
	E('#cal-source').textContent = '';
	const btn = E('#cal-new-load');
	btn.disabled = CAL.view === 'year';
	btn.textContent = CAL.view === 'year' ? 'Pick a month, week or day first' : 'Look up new series for this period';
};

function loadNew(api_key) {
	E('#cal-source').textContent = '(looking...)';
	fetchAPI('/extras/calendar/new', api_key, {view: CAL.view, date: CAL.anchor}).then(j => {
		E('#cal-source').textContent = j.result.series.length ? `(from ${j.result.source})` : '';
		fill(E('#cal-new'), j.result.series.map(s => {
			const tr = node('tr');
			cell(tr, s.store_date);
			cell(tr, `${s.title}${s.start_year ? ' (' + s.start_year + ')' : ''}`);
			cell(tr, s.publisher);
			const td = cell(tr, '');
			td.appendChild(s.in_library ? document.createTextNode('In library')
				: button('Add and search', () => requestSeries(api_key, s.comicvine_id, '', () => loadNew(api_key))));
			return tr;
		}));
	}).catch(() => { E('#cal-source').textContent = '(could not load)'; });
};

function wireCalendar(api_key) {
	document.querySelectorAll('#cal-views button').forEach(b => b.onclick = () => setView(b.dataset.view));
	E('#cal-prev').onclick = () => { CAL.anchor = CAL.prev; loadCalendar(api_key); };
	E('#cal-next').onclick = () => { CAL.anchor = CAL.next; loadCalendar(api_key); };
	E('#cal-today').onclick = () => { CAL.anchor = isoDay(new Date()); loadCalendar(api_key); };
	E('#up-months').onchange = e => { CAL.upcoming_months = Number(e.target.value); loadUpcoming(api_key); };
	E('#cal-new-load').onclick = () => loadNew(api_key);
	document.addEventListener('keydown', e => {
		if (E('#tab-calendar').classList.contains('hidden') || /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) return;
		if (e.key === 'ArrowLeft') E('#cal-prev').click();
		if (e.key === 'ArrowRight') E('#cal-next').click();
	});
};
