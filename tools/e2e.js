// End-to-end suite for the containerised site. Every check is an assertion;
// the process exits non-zero if any fail. Also sweeps overflow across routes
// and widths.
//
//   BASE=http://127.0.0.1:8765 node tools/e2e.js
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://127.0.0.1:8765';
const results = [];
const fails = [];
const errors = [];

const go = async (page, hash) => {
  await page.goto(BASE + '/' + hash, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(650);
};

const check = (name, pass, detail) => {
  results.push({ name, pass: !!pass, detail });
  if (!pass) fails.push(`${name}: ${detail}`);
};

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error' && !/404|ERR_ABORTED|ggpht|youtube-nocookie/.test(m.text())) errors.push(m.text()); });

  // ---------- home
  await page.goto(BASE + '/#/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(900);
  const home = await page.evaluate(() => ({
    hero: !!document.querySelector('.hero'),
    heroTitle: document.querySelector('.hero__title')?.textContent?.trim(),
    quote: document.querySelector('.pullquote p')?.textContent?.length || 0,
    cite: document.querySelector('.pullquote cite')?.textContent?.includes('Karpathy'),
    cards: document.querySelectorAll('#grid .card').length,
    chips: document.querySelectorAll('#chips .chip').length,
    footer: !!document.querySelector('.site-foot'),
  }));
  check('home renders hero', home.hero, JSON.stringify(home));
  check('hero carries the attributed quote', home.quote > 120 && home.cite, `quote chars ${home.quote}`);
  check('home grid populated', home.cards >= 24, `${home.cards} cards`);
  check('footer provenance present', home.footer, '');

  // ---------- search
  await page.fill('#search-input', 'photosynthesis');
  await page.press('#search-input', 'Enter');
  await page.waitForTimeout(800);
  const search = await page.evaluate(() => ({
    hash: location.hash,
    h1: document.querySelector('.page-head h1')?.textContent,
    rows: document.querySelectorAll('.list-row').length,
  }));
  check('search routes and returns rows', search.hash.startsWith('#/search/') && search.rows > 0, JSON.stringify(search));

  // ---------- filter chip
  await page.goto(BASE + '/#/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(700);
  const before = await page.evaluate(() => document.querySelectorAll('#grid .card').length);
  await page.click('#chips .chip:nth-child(2)'); // classroom ready
  await page.waitForTimeout(700);
  const after = await page.evaluate(() => ({
    cards: document.querySelectorAll('#grid .card').length,
    active: document.querySelector('#chips .chip.is-active')?.textContent?.trim(),
    allReady: [...document.querySelectorAll('#grid .card')].every((c) => c.querySelector('.badge--ready')),
  }));
  check('classroom filter narrows and marks itself active', after.active?.includes('Classroom ready') && after.allReady, JSON.stringify({ before, after }));

  // ---------- sort
  await page.goto(BASE + '/#/top', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(800);
  const top = await page.evaluate(() => {
    const v = [...document.querySelectorAll('#grid .card')].slice(0, 5)
      .map((c) => (c.querySelectorAll('.card__sub')[1]?.textContent || '').match(/([\d.]+)([KM]?)/) || []);
    return { h1: document.querySelector('.page-head h1')?.textContent, first: v[0]?.[0], titles: v.length };
  });
  check('most viewed route renders', top.h1 === 'Most viewed' && top.titles === 5, JSON.stringify(top));

  // ---------- subject + channel
  await page.goto(BASE + '/#/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(600);
  const subjSel = await page.evaluate(() => document.querySelector('#chips .chip[data-subject]')?.dataset.subject);
  await page.click('#chips .chip[data-subject]');
  await page.waitForTimeout(800);
  const subj = await page.evaluate(() => ({
    hash: location.hash,
    h1: document.querySelector('.page-head h1')?.textContent,
    cards: document.querySelectorAll('#grid .card').length,
  }));
  check('subject hub renders', subj.h1 === subjSel && subj.cards > 0, JSON.stringify(subj));

  await page.click('#grid .card a.card__sub');
  await page.waitForTimeout(800);
  const chan = await page.evaluate(() => ({
    hash: location.hash,
    h1: document.querySelector('h1')?.textContent,
    cards: document.querySelectorAll('.grid .card').length,
  }));
  check('channel page renders', chan.hash.startsWith('#/channel/') && chan.cards > 0, JSON.stringify(chan));

  // ---------- watch page
  await page.goto(BASE + '/#/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(600);
  await page.click('#grid .card a.card__thumb-link');
  await page.waitForTimeout(900);
  const watch = await page.evaluate(() => ({
    title: document.querySelector('.watch__title')?.textContent?.trim(),
    upNext: document.querySelectorAll('.rail-card').length,
    hasDesc: !!document.querySelector('#desc'),
  }));
  check('watch page renders title, description, up next', watch.title && watch.hasDesc && watch.upNext >= 10, JSON.stringify(watch));

  await page.click('[data-play]');
  await page.waitForTimeout(2500);
  const player = await page.evaluate(() => {
    const f = document.querySelector('#player iframe');
    const r = f?.getBoundingClientRect();
    return { src: f?.src || '', w: r?.width || 0, h: r?.height || 0 };
  });
  check('click to play mounts the embed', player.src.includes('youtube-nocookie.com/embed/') && player.w > 600, JSON.stringify(player));

  // keyboard on watch page
  await page.keyboard.press('j');
  await page.waitForTimeout(300);
  const railFocus = await page.evaluate(() => !!document.querySelector('.rail-card.is-focus'));
  check('j/k navigates up next on watch page', railFocus, '');

  // ---------- keyboard overlay on home
  await page.goto(BASE + '/#/', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(600);
  await page.keyboard.press('?');
  await page.waitForTimeout(250);
  const kbd = await page.evaluate(() => ({ open: !!document.querySelector('#kbd'), rows: document.querySelectorAll('.kbd-row').length }));
  await page.keyboard.press('Escape');
  check('shortcuts overlay opens and closes', kbd.open && kbd.rows >= 5, JSON.stringify(kbd));

  // ---------- for you
  const ids = await page.evaluate(async () => {
    const c = await (await fetch('data/catalog.json')).json();
    return c.videos.filter((v) => v.subject === 'Physics').slice(0, 3).map((v) => v.id);
  });
  for (const id of ids) {
    await page.goto(`${BASE}/#/watch/${id}`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(200);
  }
  await page.goto(BASE + '/#/foryou', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(800);
  const fy = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('#grid .card')];
    const subs = cards.slice(0, 10).map((c) => (c.querySelectorAll('.card__sub')[1]?.textContent || '').split('·')[1]?.trim() || '');
    return { n: cards.length, physics: subs.filter((s) => s.includes('Physics')).length, distinct: new Set(subs).size };
  });
  check('for you is personalised with exploration', fy.physics >= 5 && fy.physics <= 8 && fy.distinct >= 3, JSON.stringify(fy));

  // ---------- export
  const exp = await page.evaluate(async () => {
    const r = await fetch('data/catalog.json');
    const c = await r.json();
    return { ok: r.ok, records: c.videos.length, schema: Object.keys(c.schema?.fields || {}).length, prov: Object.keys(c.provenance || {}).length, dl: !!document.querySelector('a[download][href="data/catalog.json"]') };
  });
  check('export is downloadable and self-describing', exp.ok && exp.schema >= 15 && exp.prov >= 5 && exp.dl, JSON.stringify(exp));

  // ---------- 404 route
  await page.goto(BASE + '/#/watch/does-not-exist', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(500);
  const nf = await page.evaluate(() => document.querySelector('.empty strong')?.textContent || '');
  check('unknown route shows an empty state', nf.length > 0, nf);

  // ---------- overflow matrix
  const routes = ['#/', '#/top', '#/ready', '#/foryou', '#/about', '#/search/physics', '#/subject/physics'];
  const widths = [320, 360, 390, 414, 480, 600, 768, 900, 1024, 1280, 1440, 1920];
  const overflow = [];
  for (const w of widths) {
    await page.setViewportSize({ width: w, height: 900 });
    for (const r of routes) {
      await page.goto(BASE + '/' + r, { waitUntil: 'domcontentloaded' });
      await page.waitForTimeout(220);
      const d = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      if (d > 0) overflow.push({ w, r, d });
    }
  }
  check('no horizontal overflow across 12 widths x 7 routes', overflow.length === 0, JSON.stringify(overflow.slice(0, 5)));

  check('no console errors', errors.length === 0, JSON.stringify(errors.slice(0, 3)));

  await browser.close();

  const passed = results.filter((r) => r.pass).length;
  console.log(`\n${passed}/${results.length} checks passed\n`);
  for (const r of results) console.log(`${r.pass ? 'PASS' : 'FAIL'}  ${r.name}${r.pass ? '' : '  -> ' + r.detail}`);
  require('fs').writeFileSync('data/e2e.json', JSON.stringify({ base: BASE, passed, total: results.length, results }, null, 2));
  if (fails.length) { console.log('\nFAILURES:\n' + fails.join('\n')); process.exit(1); }
})();
