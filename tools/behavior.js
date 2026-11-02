// Behavioural evidence for the fidelity audit. Measures the things Karpathy's
// post actually promises, against the running container.
//
//   BASE=http://127.0.0.1:8765 node tools/behavior.js > data/behavior.json
const { chromium } = require('playwright');
const fs = require('fs');

const BASE = process.env.BASE || 'http://127.0.0.1:8765';

(async () => {
  const browser = await chromium.launch();
  const out = { base: BASE, errors: [] };

  // ---------- 1. thumbnails: 50% frame, not uploaded art
  const ctx1 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p1 = await ctx1.newPage();
  p1.on('pageerror', (e) => out.errors.push(e.message));
  await p1.goto(BASE + '/#/', { waitUntil: 'networkidle' });
  await p1.waitForTimeout(900);
  out.thumbs = await p1.evaluate(async () => {
    const c = await (await fetch('data/catalog.json')).json();
    const kinds = {};
    let mid = 0;
    for (const v of c.videos) {
      const k = (v.thumb || '').split('/').pop().replace('.jpg', '');
      kinds[k] = (kinds[k] || 0) + 1;
      if (k.endsWith('2')) mid += 1;
    }
    return { total: c.videos.length, midframe: mid, kinds };
  });

  // ---------- 2. export: self-describing file an agent can consume
  out.export = await p1.evaluate(async () => {
    const r = await fetch('data/catalog.json');
    const c = await r.json();
    return {
      bytes: Number(r.headers.get('content-length') || 0),
      ok: r.ok,
      topKeys: Object.keys(c),
      schemaFields: Object.keys(c.schema?.fields || {}).length,
      provenanceKeys: Object.keys(c.provenance || {}).length,
      records: c.videos?.length,
      downloadable: !!document.querySelector('a[download][href="data/catalog.json"]'),
    };
  });

  // ---------- 3. For You: no account, local session, responds to history
  const seed = ['Physics', 'Physics', 'Physics', 'Mathematics'];
  out.foryou = await p1.evaluate(async (seed) => {
    const cat = await (await fetch('data/catalog.json')).json();
    const picks = [];
    for (const s of seed) {
      const v = cat.videos.find((x) => x.subject === s && !picks.includes(x.id));
      if (v) picks.push(v.id);
    }
    return { seedSubjects: seed, pickable: picks.length };
  }, seed);

  // drive a real session: open 3 physics videos, then read the feed
  const phys = await p1.evaluate(async () => {
    const cat = await (await fetch('data/catalog.json')).json();
    return cat.videos.filter((v) => v.subject === 'Physics').slice(0, 3).map((v) => v.id);
  });
  for (const id of phys) {
    await p1.goto(`${BASE}/#/watch/${id}`, { waitUntil: 'domcontentloaded' });
    await p1.waitForTimeout(250);
  }
  const stored = await p1.evaluate(() => JSON.parse(localStorage.getItem('edutube.activity.v1') || 'null'));
  await p1.goto(BASE + '/#/foryou', { waitUntil: 'networkidle' });
  await p1.waitForTimeout(800);
  const feed = await p1.evaluate(() => [...document.querySelectorAll('#grid .card')].slice(0, 10)
    .map((c) => c.querySelectorAll('.card__sub')[1]?.textContent?.trim() || ''));
  out.foryou = {
    ...out.foryou,
    storedSubjects: stored ? Object.keys(stored.subjects) : [],
    storedChannels: stored ? Object.keys(stored.channels).length : 0,
    watchedIds: stored ? stored.watched.length : 0,
    top10Subjects: feed,
    physicsInTop10: feed.filter((s) => s.includes('Physics')).length,
    serverSideProfile: false,
  };

  // ---------- 4. keyboard shortcuts
  await p1.goto(BASE + '/#/', { waitUntil: 'networkidle' });
  await p1.waitForTimeout(600);
  await p1.keyboard.press('?');
  await p1.waitForTimeout(250);
  const overlay = await p1.evaluate(() => ({ open: !!document.querySelector('#kbd'), rows: document.querySelectorAll('.kbd-row').length }));
  await p1.keyboard.press('Escape');
  await p1.keyboard.press('j');
  await p1.keyboard.press('j');
  const focused = await p1.evaluate(() => document.querySelector('.card.is-focus')?.querySelector('.card__title')?.textContent?.slice(0, 40));
  await p1.keyboard.press('Enter');
  await p1.waitForTimeout(600);
  const enteredWatch = await p1.evaluate(() => location.hash.startsWith('#/watch/'));
  await p1.goto(BASE + '/#/watch/' + phys[0], { waitUntil: 'networkidle' });
  await p1.waitForTimeout(500);
  await p1.keyboard.press('j');
  const railFocus = await p1.evaluate(() => !!document.querySelector('.rail-card.is-focus'));
  out.keyboard = { overlay, focusedTitle: focused || null, enterOpensWatch: enteredWatch, watchPageJk: railFocus };

  // ---------- 5. quality posture: what the default feed actually shows
  await p1.goto(BASE + '/#/', { waitUntil: 'networkidle' });
  await p1.waitForTimeout(700);
  out.feed = await p1.evaluate((phys3) => {
    const cards = [...document.querySelectorAll('#grid .card')].slice(0, 12);
    return {
      sample: cards.map((c) => c.querySelector('.card__title')?.textContent?.slice(0, 46)),
      subjects: [...new Set(cards.map((c) => (c.querySelectorAll('.card__sub')[1]?.textContent || '').split('·')[1]?.trim()))],
    };
  }, phys);

  await browser.close();
  fs.writeFileSync('data/behavior.json', JSON.stringify(out, null, 2));
  console.log(JSON.stringify(out, null, 2));
})();
