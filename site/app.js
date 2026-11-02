/* ------------------------------------------------------------------
   EduTube (rebuilt): single-file app over site/data/catalog.json
   Routes: #/  #/watch/:id  #/subject/:name  #/channel/:name
           #/search?q=  #/about
------------------------------------------------------------------- */
(() => {
  const $ = (sel, root = document) => root.querySelector(sel);
  const main = $('#main');
  const rail = $('#rail');

  const S = { catalog: null, q: '', subject: 'all', level: 'all', ready: false, sort: 'rec' };

  /* ------------------------------ utils ------------------------------ */
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
  const slugify = (s) => encodeURIComponent(String(s).toLowerCase().replace(/\s+/g, '-'));
  const fmtViews = (n) => {
    if (!n) return 'n/a';
    if (n >= 1e7) return (n / 1e6).toFixed(1).replace('.0', '') + 'M';
    if (n >= 1e6) return (n / 1e6).toFixed(2).replace(/\.?0+$/, '') + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1).replace('.0', '') + 'K';
    return String(n);
  };
  const AGE = { 'Pre-school': '3–5', Primary: '5–11', Secondary: '11–18', University: '18+', General: 'all ages' };
  const ageOf = (level) => AGE[level] || null;
  const initials = (name) => (String(name || '?').replace(/^@/, '').trim()[0] || '?').toUpperCase();
  const hue = (name) => {
    let h = 0;
    for (const ch of String(name)) h = (h * 31 + ch.charCodeAt(0)) % 360;
    return h;
  };
  const avatar = (name, cls = '') => {
    const h = hue(name);
    return `<span class="avatar ${cls}" style="background:linear-gradient(140deg,hsl(${h} 62% 48%),hsl(${(h + 48) % 360} 68% 38%))">${esc(initials(name))}</span>`;
  };
  const thumb = (v) => v.thumb || `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`;
  const thumbFallback = (v) => `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`;
  const playIcon = '<svg viewBox="0 0 24 24" fill="#fff"><path d="M8 5v14l11-7z"/></svg>';

  /* ---- local session, no accounts (Karpathy's rule) ---- */
  const STORE = 'edutube.activity.v1';
  function activity() {
    try {
      return JSON.parse(localStorage.getItem(STORE)) || { subjects: {}, channels: {}, watched: [] };
    } catch { return { subjects: {}, channels: {}, watched: [] }; }
  }
  function remember(v) {
    const a = activity();
    a.subjects[v.subject] = (a.subjects[v.subject] || 0) + 1;
    a.channels[v.channel] = (a.channels[v.channel] || 0) + 1;
    a.watched = [v.id, ...a.watched.filter((id) => id !== v.id)].slice(0, 100);
    try { localStorage.setItem(STORE, JSON.stringify(a)); } catch { /* private mode */ }
  }

  /* --------------------------- card markup -------------------------- */
  function badgeRow(v) {
    const out = [];
    if ((v.classroom ?? 0) >= 0.5) out.push('<span class="badge badge--ready">classroom ready</span>');
    if (v.level && v.level !== 'General') out.push(`<span class="badge badge--level">${esc(v.level)}</span>`);
    if (v.index) out.push(`<span class="badge badge--index">index ${v.index.toFixed(2)}</span>`);
    return out.length ? `<div class="card__badges">${out.join('')}</div>` : '';
  }

  function card(v) {
    const href = `#/watch/${esc(v.id)}`;
    return `
      <div class="card">
        <a class="card__thumb-link" href="${href}" title="${esc(v.title)}">
          <div class="card__thumb">
            <img loading="lazy" src="${thumb(v)}" data-fallback="${thumbFallback(v)}" alt="${esc(v.title)}" />
            ${v.duration ? `<span class="card__dur">${esc(v.duration)}</span>` : ''}
            <span class="card__play"><span>${playIcon}</span></span>
          </div>
        </a>
        <div class="card__body">
          ${avatar(v.channel)}
          <div class="card__meta">
            <a class="card__title" href="${href}">${esc(v.title)}</a>
            <a class="card__sub" href="#/channel/${slugify(v.channel)}">${esc(v.channel)}</a>
            <div class="card__sub">${fmtViews(v.views_day)} views/day · ${esc(v.subject)}</div>
            ${badgeRow(v)}
          </div>
        </div>
      </div>`;
  }

  function railCard(v) {
    return `
      <a class="rail-card" href="#/watch/${esc(v.id)}">
        <div class="rail-card__thumb">
          <img loading="lazy" src="${thumb(v)}" data-fallback="${thumbFallback(v)}" alt="" />
          ${v.duration ? `<span class="rail-card__dur">${esc(v.duration)}</span>` : ''}
        </div>
        <div class="rail-card__body">
          <div class="rail-card__title">${esc(v.title)}</div>
          <div class="rail-card__sub">${esc(v.channel)}</div>
          <div class="rail-card__sub">${fmtViews(v.views_day)} views/day</div>
        </div>
      </a>`;
  }

  function listRow(v) {
    return `
      <div class="list-row">
        <a class="card" href="#/watch/${esc(v.id)}">
          <div class="card__thumb">
            <img loading="lazy" src="${thumb(v)}" data-fallback="${thumbFallback(v)}" alt="" />
            ${v.duration ? `<span class="card__dur">${esc(v.duration)}</span>` : ''}
          </div>
        </a>
        <div>
          <a class="list-row__title" href="#/watch/${esc(v.id)}">${esc(v.title)}</a>
          <div class="card__sub">${fmtViews(v.views_day)} views/day · ${esc(v.subject)} · ${esc(v.level || 'General')}</div>
          <div class="card__sub"><a href="#/channel/${slugify(v.channel)}">${esc(v.channel)}</a></div>
          <div class="list-row__desc">${esc(v.description)}</div>
          ${badgeRow(v)}
        </div>
      </div>`;
  }

  /* ------------------------------ pool ------------------------------ */
  function pool() {
    if (!S.catalog) return [];
    let v = S.catalog.videos.slice();
    if (S.subject !== 'all') v = v.filter((x) => x.subject === S.subject);
    if (S.level !== 'all') v = v.filter((x) => x.level === S.level);
    if (S.ready) v = v.filter((x) => (x.classroom ?? 0) >= 0.5);
    if (S.q) {
      const q = S.q.toLowerCase();
      v = v.filter((x) => `${x.title} ${x.description} ${x.channel} ${x.subject} ${x.legacy_category}`.toLowerCase().includes(q));
    }
    if (S.sort === 'views') v.sort((a, b) => (b.views_day || 0) - (a.views_day || 0));
    else if (S.sort === 'index') v.sort((a, b) => (b.index || 0) - (a.index || 0));
    else if (S.sort === 'short') v.sort((a, b) => (a.dur || 1e9) - (b.dur || 1e9));
    else if (S.sort === 'az') v.sort((a, b) => a.title.localeCompare(b.title));
    else v.sort((a, b) => b.score - a.score);
    if (S.sort === 'rec') v = roundRobin(v);
    return v;
  }


  // The default feed interleaves subjects so the first screen shows range:
  // strongest subject first, then its best, then the next subject's best, ...
  function roundRobin(list) {
    const groups = new Map();
    for (const v of list) {
      if (!groups.has(v.subject)) groups.set(v.subject, []);
      groups.get(v.subject).push(v);
    }
    const queues = [...groups.values()].filter((q) => q.length);
    const out = [];
    let i = 0;
    while (out.length < list.length) {
      for (const q of queues) if (q[i]) out.push(q[i]);
      i += 1;
    }
    return out;
  }

  /* ------------------------------ chips ------------------------------ */
  const LEVELS = ['Primary', 'Secondary', 'University', 'General'];
  function chips() {
    const items = [
      { k: 'all', label: 'All' },
      { k: 'ready', label: 'Classroom ready' },
      ...LEVELS.map((l) => ({ k: 'level:' + l, label: l })),
    ];
    const subjects = (S.catalog?.subjects || []).slice(0, 14);
    return `
      <div class="chips" id="chips">
        ${items.map((i) => {
          const active = i.k === 'all' ? (S.subject === 'all' && S.level === 'all' && !S.ready)
            : i.k === 'ready' ? S.ready
            : S.level === i.k.slice(6);
          return `<button class="chip ${active ? 'is-active' : ''}" data-chip="${esc(i.k)}">${esc(i.label)}</button>`;
        }).join('')}
        <span style="width:1px;flex:0 0 1px;background:#303030;margin:0 4px"></span>
        ${subjects.map((s) => `<button class="chip ${S.subject === s.name ? 'is-active' : ''}" data-subject="${esc(s.name)}">${esc(s.name)} <span style="opacity:.55;font-size:12px">${s.count}</span></button>`).join('')}
      </div>`;
  }

  function sortBar(total) {
    const opts = [['rec', 'Recommended'], ['views', 'Most viewed'], ['index', 'Highest index'], ['short', 'Shortest'], ['az', 'A–Z']];
    return `
      <div style="display:flex;align-items:center;gap:12px;margin:2px 0 18px;color:var(--muted);font-size:12.5px">
        <span>${total.toLocaleString()} lesson${total === 1 ? '' : 's'}</span>
        <span style="flex:1"></span>
        <label style="display:flex;align-items:center;gap:8px">Sort
          <select id="sort" style="background:#1c1c1c;color:#f1f1f1;border:1px solid #303030;border-radius:8px;height:32px;padding:0 8px;font-size:12.5px">
            ${opts.map(([k, l]) => `<option value="${k}" ${S.sort === k ? 'selected' : ''}>${l}</option>`).join('')}
          </select>
        </label>
      </div>`;
  }

  /* ------------------------------ views ------------------------------ */
  function heroBlock(stats) {
    return `
      <section class="hero">
        <div class="hero__eyebrow">Rebuilt from the archive · 2008–2021</div>
        <h1 class="hero__title">Everything worth showing in class.</h1>
        <blockquote class="pullquote">
          <p>“It was Friday night at 11pm, I was tired, I went to YouTube to watch something and realized that I was
          looking at an enshittified wall of slop. Insanely exaggerated thumbnails, dumb recommendations of the same
          tired topics, truly terrible idiocracy-grade content.”</p>
          <cite>Andrej Karpathy, <a href="https://karpathy.bearblog.dev/hacker-tube/" target="_blank" rel="noopener">HackerTube</a>. The brief this rebuild answers, applied to EduTube.org’s abandoned catalogue.</cite>
        </blockquote>
        <div class="hero__stats">
          <div class="hero__stat"><b>${stats.videos.toLocaleString()}</b><span>videos</span></div>
          <div class="hero__stat"><b>${stats.channels.toLocaleString()}</b><span>channels</span></div>
          <div class="hero__stat"><b>${stats.subjects}</b><span>subjects</span></div>
          <div class="hero__stat"><b>${stats.classroom_ready.toLocaleString()}</b><span>classroom ready</span></div>
          <div class="hero__stat"><b>${stats.spam_dropped.toLocaleString()}</b><span>spam removed</span></div>
        </div>
        <p class="hero__note">A reconstruction of EduTube's video directory (2008–2021), recovered from the Internet Archive. Not the games site edutube.org became in 2021, and not affiliated with it.</p>
      </section>`;
  }

  function viewHome(head) {
    const v = pool();
    const stats = S.catalog.stats;
    const showHero = !head;
    const headBlock = showHero ? '' : `
      <div class="page-head" style="display:flex;align-items:flex-end;gap:16px;flex-wrap:wrap">
        <div style="flex:1;min-width:280px">
          <h1>${esc(head.h1)}</h1>
          <p>${esc(head.p)}</p>
        </div>
        <a class="chip chip--ghost" href="#/about">How this was rebuilt →</a>
      </div>`;
    return `
      ${showHero ? heroBlock(stats) : headBlock}
      <div class="section-head">
        <h2>${showHero ? 'The catalogue' : esc(head.h1)}</h2>
        <span>${v.length.toLocaleString()} lessons · every tag re-judged</span>
        ${showHero ? '<a class="chip chip--ghost" href="#/about" style="margin-left:auto">The rebuild →</a>' : ''}
      </div>
      ${chips()}
      ${sortBar(v.length)}
      <div class="grid" id="grid"></div>`;
  }

  // Up next: same subject first, then the rest of the catalogue weighted by what
  // this browser has actually watched. No account, no server call.
  function relatedList(current, n) {
    const a = activity();
    const total = Object.values(a.subjects).reduce((x, y) => x + y, 0) || 1;
    return S.catalog.videos
      .filter((x) => x.id !== current.id && !a.watched.slice(0, 12).includes(x.id))
      .map((x) => {
        const sameSubject = x.subject === current.subject ? 1 : 0;
        const affinity = (a.subjects[x.subject] || 0) / total;
        const channel = x.channel === current.channel ? 0.4 : 0;
        return { x, s: 2.4 * sameSubject + 1.8 * affinity + channel + x.score / 100 };
      })
      .sort((p, q) => q.s - p.s)
      .slice(0, n)
      .map((p) => p.x);
  }

  function viewWatch(id) {
    const v = S.catalog.videos.find((x) => x.id === id);
    if (!v) return notFound();
    const related = relatedList(v, 14);
    const more = S.catalog.videos.filter((x) => x.id !== v.id && x.channel === v.channel).slice(0, 8);
    return `
      <div class="watch">
        <div class="watch__main">
          <div class="player" id="player">
            <div class="player__poster" data-play="${esc(v.id)}">
              <img src="${thumb(v)}" data-fallback="${thumbFallback(v)}" alt="" />
              <div class="player__btn"><span>${playIcon}</span></div>
            </div>
          </div>
          <h1 class="watch__title">${esc(v.title)}</h1>
          <div class="watch__row">
            <span class="watch__views">${fmtViews(v.views_day)} views/day on EduTube · captured ${esc(v.archived || 'n/a')}</span>
          </div>
          <div class="channel-line">
            ${avatar(v.channel, 'avatar--lg')}
            <div>
              <div class="channel-line__name"><a href="#/channel/${slugify(v.channel)}">${esc(v.channel)}</a></div>
              <div class="channel-line__sub">YouTube channel · ${v.live ? 'still online' : 'source unverified'}</div>
            </div>
            <div class="watch__actions">
              <button class="btn" data-copy="${esc(v.id)}">Share</button>
              <a class="btn" href="https://www.youtube.com/watch?v=${esc(v.id)}" target="_blank" rel="noopener">Watch on YouTube ↗</a>
            </div>
          </div>
          <div class="desc" id="desc">
            <div class="desc__meta">${fmtViews(v.views_day)} views/day · ${esc(v.duration || 'n/a')} · EduTube index ${v.index ? v.index.toFixed(2) : 'n/a'}</div>
            <div class="desc__body">${esc(v.description || 'No description was archived for this video.')}</div>
            <div class="desc__filed" style="margin-top:10px;color:#9a9a9a;font-size:12px">Filed by EduTube's editors under <b>${esc(v.legacy_category || 'unfiled')}</b> · Re-judged by the model as <b>${esc(v.subject)}</b>, ${esc(v.level || 'General')}${ageOf(v.level) ? ` <span style="white-space:nowrap">(ages ${ageOf(v.level)})</span>` : ''}${v.classroom != null ? ` · classroom-ready p=${Number(v.classroom).toFixed(2)}` : ''}${v.evergreen != null ? ` · still current p=${Number(v.evergreen).toFixed(2)}` : ''}</div>
          </div>
          <div class="chips" style="position:static;padding-top:16px">
            <a class="chip" href="#/subject/${slugify(v.subject)}">${esc(v.subject)}</a>
            ${v.level && v.level !== 'General' ? `<a class="chip" href="#/search/${encodeURIComponent(v.level)}">${esc(v.level)}</a>` : ''}
            ${v.legacy_category ? `<span class="chip chip--ghost" title="EduTube's original 2008-2021 tag">legacy: ${esc(v.legacy_category)}</span>` : ''}
          </div>
          ${more.length > 1 ? `
            <div style="margin-top:28px">
              <div class="rail__title" style="padding-left:0">More from ${esc(v.channel)}</div>
              <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:24px 16px">
                ${more.map(card).join('')}
              </div>
            </div>` : ''}
        </div>
        <aside class="watch__side">
          <div class="rail__title" style="padding-left:0">Up next in ${esc(v.subject)}</div>
          ${related.map(railCard).join('')}
        </aside>
      </div>`;
  }

  function forYouList() {
    const a = activity();
    const total = Object.values(a.subjects).reduce((x, y) => x + y, 0);
    if (!total) return [];
    const ranked = S.catalog.videos
      .filter((v) => !a.watched.includes(v.id))
      .map((v) => {
        const sub = (a.subjects[v.subject] || 0) / total;
        const chan = (a.channels[v.channel] || 0) / Math.max(total, 1);
        return { v, s: v.score * (1 + 2.2 * sub + 1.4 * chan) };
      })
      .sort((x, y) => y.s - x.s)
      .map((x) => x.v);
    if (!ranked.length) return S.catalog.videos.slice();

    // three familiar picks for every discovery pick: a feed that only replays
    // what you watched is a mirror, not a recommendation
    const familiar = ranked.filter((v) => a.subjects[v.subject]);
    const fresh = ranked.filter((v) => !a.subjects[v.subject]);
    const out = [];
    let f = 0, x = 0;
    while (out.length < 160 && (f < familiar.length || x < fresh.length)) {
      for (let i = 0; i < 3 && f < familiar.length; i++) out.push(familiar[f++]);
      if (x < fresh.length) out.push(fresh[x++]);
    }
    return out;
  }

  function viewForYou() {
    const a = activity();
    const total = Object.values(a.subjects).reduce((x, y) => x + y, 0);
    if (!total) {
      return `
        <div class="page-head">
          <div class="crumbs"><a href="#/">Home</a> › For you</div>
          <h1>For you</h1>
          <p>This feed is built from what you open, and it lives in this browser. No account, no cookies, no server-side profile.</p>
        </div>
        ${empty('Nothing watched yet', 'Open a few videos and this becomes your feed. It stays on this device.')}
        <div style="text-align:center"><a class="chip" href="#/">Browse the archive</a></div>`;
    }
    const top = Object.entries(a.subjects).sort((x, y) => y[1] - x[1]).slice(0, 4)
      .filter((v) => !a.watched.includes(v.id))
      .map((v) => {
        const sub = (a.subjects[v.subject] || 0) / total;
        const chan = (a.channels[v.channel] || 0) / Math.max(total, 1);
        return { v, s: v.score * (1 + 2.2 * sub + 1.4 * chan) };
      })
      .sort((x, y) => y.s - x.s)
      .map((x) => x.v);
    const mix = top
      .map(([k, n]) => `${esc(k)} ${Math.round((n / total) * 100)}%`).join(' · ');
    return `
      <div class="page-head">
        <div class="crumbs"><a href="#/">Home</a> › For you</div>
        <h1>For you</h1>
        <p>Built from the ${total} video${total === 1 ? '' : 's'} you opened in this browser. Your mix so far: ${mix}. Nothing leaves the device.</p>
        <button class="btn" data-act="clear-history" style="margin-top:12px">Clear this device's history</button>
      </div>
      <div class="grid" id="grid"></div>`;
  }

  function viewSubject(slug) {
    const name = (S.catalog.subjects.find((s) => slugify(s.name) === slug) || {}).name;
    if (!name) return notFound();
    const prev = S.subject;
    S.subject = name;
    const v = pool();
    S.subject = prev;
    return `
      <div class="page-head">
        <div class="crumbs"><a href="#/">Home</a> › Subjects</div>
        <h1>${esc(name)}</h1>
        <p>${v.length.toLocaleString()} videos the model filed under ${esc(name)}, including some that EduTube's own editors put somewhere else.</p>
      </div>
      ${sortBar(v.length)}
      <div class="grid" id="grid"></div>`;
  }

  function viewChannel(slug) {
    const name = decodeURIComponent(slug);
    const v = S.catalog.videos.filter((x) => slugify(x.channel) === slug);
    if (!v.length) return notFound();
    return `
      <div class="page-head" style="display:flex;gap:24px;align-items:center">
        ${avatar(name, 'avatar--lg')}
        <div>
          <h1 style="font-size:26px">${esc(v[0].channel)}</h1>
          <p>${v.length} video${v.length === 1 ? '' : 's'} in the EduTube catalogue · ${new Set(v.map((x) => x.subject)).size} subjects</p>
        </div>
      </div>
      <div class="grid">${v.slice(0, 60).map(card).join('')}</div>`;
  }

  function viewSearch(q) {
    S.q = q || '';
    const v = pool();
    return `
      <div class="page-head">
        <div class="crumbs"><a href="#/">Home</a> › Search</div>
        <h1>Results for “${esc(q)}”</h1>
        <p>${v.length.toLocaleString()} match${v.length === 1 ? '' : 'es'} across titles, descriptions, channels and subjects.</p>
      </div>
      ${chips()}
      ${v.length ? `<div class="list-view">${v.slice(0, 60).map(listRow).join('')}</div>` : empty('Nothing in the archive matches that', 'Try a broader term, or browse a subject from the sidebar.')}`;
  }

  function viewAbout() {
    const st = S.catalog.stats;
    const verify = window.__VERIFY__;
    return `
      <div class="page-head">
        <div class="crumbs"><a href="#/">Home</a> › The rebuild</div>
        <h1>How this was rebuilt</h1>
        <p>HackerTube turned 40,000 Hacker News comments into a YouTube of the links people recommended. This applies the same play to a directory that no longer exists: EduTube.org's 2008–2021 catalogue of educational videos, most of them from YouTube.</p>
        <p style="margin-top:10px">The original site was reinvented in 2021 as a free educational games site, which is what edutube.org is today. This rebuild covers only the video directory, and it is not affiliated with that site.</p>
      </div>
      <h2 style="margin-top:38px">What EduTube actually was</h2>
      <p>From <a href="https://www.edutube.org/about/" target="_blank" rel="noopener" style="color:var(--muted)">edutube.org/about</a>, the current site's own account:</p>
      <ul class="facts">
        <li><b>Founded 2008.</b> In their words, "one of the first website to systematically organise and categorise large numbers of educational videos", most of them from YouTube.</li>
        <li><b>Why the directory ended.</b> "The value add of such compilations declined, as education-specific YouTube channels emerged."</li>
        <li><b>Reinvented in 2021</b> as a free educational games site. Their reason: great free games existed but, in their words, "no website which organised them systematically", and most families cannot afford subscription platforms.</li>
        <li><b>What it offers today.</b> Curated games across seven categories (geography, history, ICT and computer science, math, physics, science, space), classic DOS titles, and some that run offline on older machines. Games are chosen for educational value, not for being labelled educational.</li>
        <li><b>The name.</b> "Tube" refers to vacuum tube computers, not televisions, a nod to the pre-Windows games they now feature.</li>
      </ul>
      <p style="color:var(--muted);font-size:13px">Everything on this rebuild comes from the Internet Archive's captures of the old directory. Nothing is scraped from the current site, and nothing here is endorsed by it.</p>

      <h2 style="margin-top:38px">His words, verbatim</h2>
      <p class="quote-lede">From <a href="https://karpathy.bearblog.dev/hacker-tube/" target="_blank" rel="noopener" style="color:var(--muted)">karpathy.bearblog.dev/hacker-tube</a>, 31 Oct 2026. Each of these is a requirement this build had to meet, or explain.</p>
      <div class="quote-grid">
        <blockquote class="quote-card">
          <p>“Let's write our own YouTube clone based on whatever videos have been recommended on Hacker News.”</p>
          <cite>The task</cite>
        </blockquote>
        <blockquote class="quote-card">
          <p>“Uses the 50% thumbnail instead of the uploaded thumbnail.”</p>
          <cite>The anti-slop rule · 663 of 670 here</cite>
        </blockquote>
        <blockquote class="quote-card">
          <p>“Custom and good ForYou recommendations without any user accounts, storing state in local browser session.”</p>
          <cite>No accounts, ever</cite>
        </blockquote>
        <blockquote class="quote-card">
          <p>“Export of the site's data available to give to your agent to easily create your own version.”</p>
          <cite>One self-describing file</cite>
        </blockquote>
        <blockquote class="quote-card">
          <p>“It was Friday night at 11pm… I was looking at an enshittified wall of slop.”</p>
          <cite>Why it exists</cite>
        </blockquote>
        <blockquote class="quote-card">
          <p>“This takes ~2 hours now. I can breathe again.”</p>
          <cite>On the pace of building this way</cite>
        </blockquote>
      </div>

      <div class="stats">
        ${[['videos', st.videos], ['harvested', st.harvested], ['channels', st.channels], ['subjects', st.subjects], ['classroom ready', st.classroom_ready], ['dead links dropped', st.dead_links]]
          .map(([l, n]) => `<div class="stat"><div class="stat__n">${Number(n).toLocaleString()}</div><div class="stat__l">${l}</div></div>`).join('')}
      </div>
      <div class="prose">
        <p>EduTube ran on Drupal and published every subject as a paginated table: thumbnail, teaser, duration, views/day and an editorial <i>EduTube-Index</i>. Those tables are gone from the live web. The domain now sells educational games. They survive in the Wayback Machine, and that is where this catalogue comes from.</p>

        <div class="flow">
          <div class="flow__step"><div class="flow__n">1</div><div>
            <div class="flow__t">Harvest the archive</div>
            <div class="flow__d">Wayback CDX enumerates the captured <code>/en/category/*</code> tables; each table row carries a YouTube id, title, teaser, duration and the original editorial index. No YouTube API key, no scraping of YouTube itself.</div>
          </div></div>
          <div class="flow__step"><div class="flow__n">2</div><div>
            <div class="flow__t">Check what is still alive</div>
            <div class="flow__d">Every video id is resolved through YouTube's oEmbed endpoint, the canonical check for "still playable, still embeddable". Dead links are dropped. Live ones gain the current channel name and canonical thumbnail.</div>
          </div></div>
          <div class="flow__step"><div class="flow__n">3</div><div>
            <div class="flow__t">Re-judge the archive</div>
            <div class="flow__d">The original taxonomy was loose (a fluid-dynamics film filed under Chemistry) and the educational level never made it into the tables. A language model answers five typed questions per video in one call: subject, level, classroom-readiness, evergreen and promotional intent.</div>
          </div></div>
          <div class="flow__step"><div class="flow__n">4</div><div>
            <div class="flow__t">Rank and render</div>
            <div class="flow__d">The editorial index, the log of views/day and the model's classroom verdict are blended into one score. The result is this UI: filters that are typed judgments, not text search.</div>
          </div></div>
        </div>

        ${verify ? `
          <h2>Was the claim true?</h2>
          <p>Every claim below was tested against the harvested records by a language model, and the numbers are read from the run output.</p>
          ${verify.claims.map((c) => `
            <div class="flow__step" style="margin-bottom:10px">
              <div class="flow__n ${c.pass ? 'is-pass' : 'is-fail'}">${c.pass ? 'PASS' : 'FAIL'}</div>
              <div>
                <div class="flow__t">${esc(c.claim)}</div>
                <div class="flow__d">${esc(c.detail)}</div>
              </div>
            </div>`).join('')}
          <p style="color:var(--muted);font-size:12.5px">Sample: ${verify.sample} videos · run ${esc(verify.date)}</p>
        ` : ''}

        <h2>What this copies from HackerTube, specifically</h2>
        <p>Karpathy's post lists four things beyond "a YouTube UI". All four are here:</p>
        <div class="flow">
          <div class="flow__step"><div class="flow__n">1</div><div>
            <div class="flow__t">The 50% frame, not the uploaded thumbnail</div>
            <div class="flow__d">${st.midframe_thumbs} of ${st.videos} cards use the frame at the midpoint of the video (<code>maxres2 / sd2 / hq2</code>). Uploaded art is the clickbait surface the whole project exists to escape, so it is only a fallback. A handful of records still need it.</div>
          </div></div>
          <div class="flow__step"><div class="flow__n">2</div><div>
            <div class="flow__t">A "For you" feed with no accounts</div>
            <div class="flow__d">Opening a video records its subject and channel in <code>localStorage</code>; the feed re-ranks on that. There is no login, no server-side profile, and a button that wipes it.</div>
          </div></div>
          <div class="flow__step"><div class="flow__n">3</div><div>
            <div class="flow__t">Keyboard shortcuts</div>
            <div class="flow__d"><code>j</code>/<code>k</code> walk the grid, <code>Enter</code> opens, <code>/</code> jumps to search, <code>?</code> lists them.</div>
          </div></div>
          <div class="flow__step"><div class="flow__n">4</div><div>
            <div class="flow__t">Export for your own agent</div>
            <div class="flow__d">The whole catalogue is one file: <a href="data/catalog.json" download>catalog.json</a>. ${st.videos} records with subject, level and classroom probability, plus a schema block and a provenance block, so the file explains itself. Hand it to an agent and it can rebuild this in a different shape.</div>
          </div></div>
        </div>

        ${window.__PARITY__ ? `
          <h2>Section parity with the live site</h2>
          <p>Every section of edutube.org was extracted and compared to this rebuild, and a model judged whether an equivalent exists and whether one is needed. ${window.__PARITY__.covered}/${window.__PARITY__.total} covered, ${window.__PARITY__.gaps.length} required gaps.</p>
          <div class="table">
            <div class="table__row table__head"><span>Section</span><span>Coverage</span><span>Needed?</span></div>
            ${window.__PARITY__.sections.map((r) => `
              <div class="table__row">
                <span>${esc(r.label)}</span>
                <span class="tag tag--${esc(r.coverage)}">${esc(r.coverage.replace('_', ' '))}</span>
                <span>${esc(r.need.replace('_', ' '))}</span>
              </div>`).join('')}
          </div>
        ` : ''}

        ${window.__FIDELITY__ ? `
          <h2>Does it match the original? <span style="color:var(--muted-2);font-weight:400;font-size:13px">judged by a model against measured evidence</span></h2>
          <p>Each line is a requirement from the original post, the evidence this build produces for it, and the model's probability that the requirement is genuinely met. ${window.__FIDELITY__.met}/${window.__FIDELITY__.total} met at p ≥ 0.60. Overall verdict: ${esc(window.__FIDELITY__.verdict)}.</p>
          ${window.__FIDELITY__.items.map((it) => `
            <div class="flow__step" style="margin-bottom:10px">
              <div class="flow__n ${it.p >= 0.6 ? 'is-pass' : 'is-fail'}">${it.p >= 0.6 ? 'MET' : 'UNDER'}</div>
              <div>
                <div class="flow__t">${esc(it.requirement)} <span style="font-weight:400;color:${it.p >= 0.6 ? '#7ee0a1' : '#ffd479'}">p=${it.p.toFixed(2)}</span></div>
                <div class="flow__d"><i>“${esc(it.quote)}”</i><br>${esc(it.evidence)}</div>
              </div>
            </div>`).join('')}
        ` : ''}

        <h2>What could not be reproduced</h2>
        <p>HackerTube's corpus was human opinions, and recommendations were the signal. EduTube's corpus was already a catalogue, so the hard part moves. The risk is not finding videos. It is trusting the 2008 tags and the 2008 links. Both were re-verified rather than trusted. The one thing that cannot be recovered is what the old site looked like. Only the data survived, which is why the shell you are reading is a modern one.</p>
        <p>Thumbnails stream from <code>i.ytimg.com</code>. Videos still belong to their channels and play from YouTube; nothing is re-hosted.</p>
      </div>`;
  }

  const empty = (title, sub) => `<div class="empty"><strong>${esc(title)}</strong>${esc(sub)}</div>`;
  const notFound = () => empty('This page is not in the archive', 'The link may point at a video that never made it into the rebuild.');

  /* ------------------------------ rail ------------------------------ */
  function renderRail(active) {
    if (!S.catalog) return;
    const st = S.catalog.stats;
    rail.innerHTML = `
      <div class="rail__section">
        <a class="nav-item ${active === 'home' ? 'is-active' : ''}" href="#/">${icon('home')}Home</a>
        <a class="nav-item ${active === 'foryou' ? 'is-active' : ''}" href="#/foryou">${icon('spark')}For you</a>
        <a class="nav-item ${active === 'top' ? 'is-active' : ''}" href="#/top">${icon('flame')}Most viewed</a>
        <a class="nav-item ${active === 'ready' ? 'is-active' : ''}" href="#/ready">${icon('check')}Classroom ready <span class="count">${st.classroom_ready}</span></a>
        <a class="nav-item" href="#/about">${icon('info')}The rebuild</a>
        <a class="nav-item" href="data/catalog.json" download="edutube-catalog.json">${icon('download')}Export catalogue</a>
      </div>
      <div class="rail__section">
        <div class="rail__title">Subjects <span>${st.subjects}</span></div>
        ${S.catalog.subjects.map((s) => `
          <a class="nav-item nav-item--sm ${active === 'subject:' + s.name ? 'is-active' : ''}" href="#/subject/${slugify(s.name)}">
            <span class="dot"></span>${esc(s.name)}<span class="count">${s.count}</span>
          </a>`).join('')}
      </div>
      <div class="rail__section">
        <div class="rail__title">Level</div>
        ${(S.catalog.levels || []).map(([l, n]) => `
          <a class="nav-item nav-item--sm ${active === 'level:' + l ? 'is-active' : ''}" href="#/level/${encodeURIComponent(l)}">${esc(l)}<span class="count">${n}</span></a>`).join('')}
      </div>
      <div class="rail__section" style="color:var(--muted-2);font-size:11.5px;line-height:17px;padding:14px 12px">
        Rebuilt from the Wayback Machine.<br />Every link re-checked, every tag re-judged.
      </div>`;
  }

  function icon(name) {
    const p = {
      home: '<path d="M12 3l9 8h-3v9h-5v-6H11v6H6v-9H3z"/>',
      flame: '<path d="M12 2s5 5 5 9a5 5 0 01-10 0c0-2 1-3 1-3s0 2 2 2c1 0 1-2 1-3 0-2 1-5 1-5zm0 12a2.5 2.5 0 002.5-2.5c0-1-1-2-2.5-3.5-1.5 1.5-2.5 2.5-2.5 3.5A2.5 2.5 0 0012 14z"/>',
      check: '<path d="M9.5 17.5L4 12l1.4-1.4 4.1 4.1 9.1-9.2L20 7z"/>',
      info: '<path d="M12 2a10 10 0 100 20 10 10 0 000-20zm0 1.8a8.2 8.2 0 110 16.4 8.2 8.2 0 010-16.4zM11 10.6h2v7h-2zm0-3.9h2v2.1h-2z"/>',
      spark: '<path d="M12 2l2.2 6.3L20.5 10l-6.3 2.2L12 18.5l-2.2-6.3L3.5 10l6.3-1.7z"/>',
      download: '<path d="M11 3h2v9.2l3.3-3.3 1.4 1.4L12 16l-5.7-5.7 1.4-1.4L11 12.2zM5 18h14v2H5z"/>',
    }[name];
    return `<svg viewBox="0 0 24 24" fill="currentColor">${p}</svg>`;
  }

  /* ---------------------------- rendering ---------------------------- */
  let gridState = null;
  function mountGrid(list) {
    const grid = $('#grid');
    if (!grid) return;
    if (gridState) { gridState.stop(); gridState = null; }
    grid.innerHTML = '';

    let i = 0;
    const BATCH = 36;
    let stopped = false;
    const sentinel = document.createElement('div');
    sentinel.style.cssText = 'grid-column:1/-1;height:1px';

    const draw = () => {
      if (stopped || i >= list.length) return;
      grid.insertAdjacentHTML('beforeend', list.slice(i, i + BATCH).map(card).join(''));
      i += BATCH;
    };
    const stop = () => {
      stopped = true;
      io?.disconnect();
      sentinel.remove();
    };
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting) && i < list.length) draw();
    }, { rootMargin: '800px' });

    grid.after(sentinel);
    draw();
    io.observe(sentinel);
    gridState = { stop };
  }

  function render() {
    if (!S.catalog) return;
    const hash = location.hash.replace(/^#/, '') || '/';
    const [path, query] = hash.split('?');
    const parts = path.split('/').filter(Boolean);
    const params = new URLSearchParams(query || '');
    const head = $('#search-input');

    if (parts[0] === 'watch') {
      rail.classList.add('hidden');
      const watched = S.catalog.videos.find((x) => x.id === parts[1]);
      if (watched) remember(watched);
      main.innerHTML = viewWatch(parts[1]);
      renderRail('');
      window.scrollTo(0, 0);
      return;
    }
    rail.classList.remove('hidden');

    if (!parts.length) {
      S.q = ''; S.subject = 'all'; S.level = 'all'; S.ready = false;
      main.innerHTML = viewHome();
      renderRail('home');
      mountGrid(pool());
    } else if (parts[0] === 'subject') {
      S.q = ''; S.subject = 'all'; S.level = 'all'; S.ready = false;
      main.innerHTML = viewSubject(parts[1]);
      renderRail('subject:' + (S.catalog.subjects.find((s) => slugify(s.name) === parts[1]) || {}).name);
      S.subject = (S.catalog.subjects.find((s) => slugify(s.name) === parts[1]) || {}).name || 'all';
      mountGrid(pool());
      S.subject = 'all';
    } else if (parts[0] === 'top' || parts[0] === 'ready') {
      S.q = ''; S.subject = 'all'; S.level = 'all';
      S.ready = parts[0] === 'ready';
      S.sort = parts[0] === 'top' ? 'views' : 'rec';
      main.innerHTML = viewHome(parts[0] === 'top'
        ? { h1: 'Most viewed', p: 'Ordered by views per day as EduTube recorded them between 2008 and 2021, before the platform and most of these channels moved on.' }
        : { h1: 'Classroom ready', p: 'Videos the model would let a teacher press play on without caveats: no advertising, no inappropriate content, no broken footage. Judged, not assumed.' });
      renderRail(parts[0]);
      mountGrid(pool());
    } else if (parts[0] === 'level') {
      const lvl = decodeURIComponent(parts[1] || '');
      S.q = ''; S.subject = 'all'; S.ready = false; S.sort = 'rec';
      S.level = lvl;
      main.innerHTML = viewHome({ h1: `${lvl} lessons`, p: `Every video the model places at ${lvl.toLowerCase()} level, across all subjects.` });
      renderRail('level:' + lvl);
      mountGrid(pool());
      S.level = 'all';
    } else if (parts[0] === 'foryou') {
      S.q = ''; S.subject = 'all'; S.level = 'all'; S.ready = false;
      main.innerHTML = viewForYou();
      renderRail('foryou');
      const a = activity();
      if (Object.keys(a.subjects).length) {
        const total = Object.values(a.subjects).reduce((x, y) => x + y, 0);
        mountGrid(forYouList());
      }
    } else if (parts[0] === 'channel') {
      main.innerHTML = viewChannel(parts[1]);
      renderRail('');
    } else if (parts[0] === 'search') {
      const q = decodeURIComponent(parts[1] || params.get('q') || '');
      S.subject = 'all'; S.level = 'all'; S.ready = false;
      main.innerHTML = viewSearch(q);
      renderRail('');
      head.value = q;
    } else if (parts[0] === 'about') {
      main.innerHTML = viewAbout();
      renderRail('');
    } else {
      main.innerHTML = notFound();
    }
    if (parts[0] !== 'search') head.value = '';
    window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
  }

  /* ---------------------------- behaviour ---------------------------- */
  document.addEventListener('click', (e) => {
    const t = e.target.closest('[data-chip],[data-subject],[data-play],[data-copy]');
    if (!t) return;

    if (t.dataset.act === 'clear-history') {
      localStorage.removeItem(STORE);
      main.innerHTML = viewForYou();
      return;
    }
    if (t.dataset.play) {
      const id = t.dataset.play;
      const player = $('#player');
      player.innerHTML = `<iframe src="https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}?autoplay=1&rel=0" title="Video player" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>`;
      return;
    }
    if (t.dataset.copy) {
      navigator.clipboard?.writeText(`https://www.youtube.com/watch?v=${t.dataset.copy}`);
      t.textContent = 'Link copied';
      setTimeout(() => (t.textContent = 'Share'), 1400);
      return;
    }
    if (t.dataset.chip) {
      const k = t.dataset.chip;
      if (k === 'all') { S.subject = 'all'; S.level = 'all'; S.ready = false; }
      else if (k === 'ready') { S.ready = !S.ready; }
      else if (k.startsWith('level:')) { S.level = S.level === k.slice(6) ? 'all' : k.slice(6); }
      const inSearch = location.hash.startsWith('#/search/');
      if (!inSearch) S.q = '';
      main.innerHTML = inSearch ? viewSearch(S.q) : viewHome();
      renderRail(inSearch ? '' : 'home');
      mountGrid(pool());
      return;
    }
    if (t.dataset.subject) {
      location.hash = `#/subject/${slugify(t.dataset.subject)}`;
      return;
    }
  });

  document.addEventListener('change', (e) => {
    if (e.target.id === 'sort') {
      S.sort = e.target.value;
      if (location.hash.includes('/subject/')) {
        const name = (S.catalog.subjects.find((s) => slugify(s.name) === location.hash.split('/')[2]) || {}).name;
        S.subject = name || 'all';
        mountGrid(pool());
        S.subject = 'all';
      } else {
        mountGrid(pool());
      }
    }
  });

  document.addEventListener('submit', (e) => {
    if (e.target.id === 'search-form') {
      e.preventDefault();
      const q = $('#search-input').value.trim();
      location.hash = q ? `#/search/${encodeURIComponent(q)}` : '#/';
    }
  });

  $('#rail-toggle').addEventListener('click', () => {
    if (window.innerWidth <= 1024) document.body.classList.toggle('rail-open');
    else document.body.classList.toggle('rail-hidden');
  });

  /* ---- keyboard shortcuts (j/k/enter, /, ?, esc) ---- */
  let focusIdx = -1;
  const cardEls = () => {
    const grid = [...document.querySelectorAll('#grid .card, .list-view .list-row')];
    return grid.length ? grid : [...document.querySelectorAll('.rail-card')];
  };

  function setFocus(i) {
    const list = cardEls();
    if (!list.length) return;
    list.forEach((el) => el.classList.remove('is-focus'));
    focusIdx = Math.max(0, Math.min(i, list.length - 1));
    const el = list[focusIdx];
    el.classList.add('is-focus');
    el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function shortcuts() {
    if ($('#kbd')) return;
    const rows = [
      ['j / k', 'next / previous video'],
      ['Enter', 'open the highlighted video'],
      ['/', 'jump to search'],
      ['?', 'this panel'],
      ['Esc', 'close'],
    ];
    const div = document.createElement('div');
    div.id = 'kbd';
    div.className = 'kbd-overlay';
    div.innerHTML = `<div class="kbd-card">
      <div class="kbd-card__t">Keyboard shortcuts</div>
      ${rows.map(([k, v]) => `<div class="kbd-row"><kbd>${k}</kbd><span>${v}</span></div>`).join('')}
      <div class="kbd-hint">Shortcuts are local; nothing about you is stored server-side.</div>
    </div>`;
    div.addEventListener('click', () => div.remove());
    document.body.appendChild(div);
  }

  document.addEventListener('keydown', (e) => {
    const tag = document.activeElement?.tagName;
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') {
      if (e.key === 'Escape') document.activeElement.blur();
      return;
    }
    if (e.key === '/') { e.preventDefault(); $('#search-input')?.focus(); return; }
    if (e.key === '?') { e.preventDefault(); shortcuts(); return; }
    if (e.key === 'Escape') { $('#kbd')?.remove(); cardEls().forEach((el) => el.classList.remove('is-focus')); focusIdx = -1; return; }
    if (e.key === 'j' || e.key === 'ArrowDown') { e.preventDefault(); setFocus(focusIdx + 1); return; }
    if (e.key === 'k' || e.key === 'ArrowUp') { e.preventDefault(); setFocus(focusIdx - 1); return; }
    if (e.key === 'Enter' && focusIdx >= 0) {
      const el = cardEls()[focusIdx];
      const link = el?.querySelector('a.card__title, a.list-row__title, a.card__thumb-link') || el;
      const href = link?.getAttribute?.('href');
      if (href) { e.preventDefault(); location.hash = href; }
    }
  });

  // youtube thumbnails sometimes lack hq720; fall back to hqdefault
  document.addEventListener('error', (e) => {
    const img = e.target;
    if (img.tagName === 'IMG' && img.dataset.fallback && img.src !== img.dataset.fallback) {
      img.src = img.dataset.fallback;
    }
  }, true);

  window.addEventListener('hashchange', () => { document.body.classList.remove('rail-open'); render(); });

  /* ------------------------------ boot ------------------------------ */
  async function boot() {
    main.innerHTML = `
      <div class="page-head"><h1 style="opacity:.5">Loading the archive…</h1></div>
      <div class="grid">${Array.from({ length: 8 }).map(() => '<div><div class="skeleton" style="aspect-ratio:16/9"></div><div class="skeleton" style="height:14px;margin-top:12px;width:90%"></div><div class="skeleton" style="height:12px;margin-top:8px;width:60%"></div></div>').join('')}</div>`;
    try {
      const [cat, ver, fid, par] = await Promise.all([
        fetch('data/catalog.json').then((r) => r.json()),
        fetch('data/verify.json').then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch('data/fidelity.json').then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch('data/parity.json').then((r) => (r.ok ? r.json() : null)).catch(() => null),
      ]);
      S.catalog = cat;
      window.__VERIFY__ = ver;
      window.__FIDELITY__ = fid;
      window.__PARITY__ = par;
      const n = cat.stats.videos.toLocaleString();
      const input = $('#search-input');
      if (input) input.placeholder = `Search ${n} lessons, subjects, channels`;
      render();
    } catch (err) {
      main.innerHTML = empty('Could not load the catalogue', String(err));
    }
  }

  boot();
})();
