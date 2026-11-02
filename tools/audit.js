const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://127.0.0.1:8756';
const OUT = process.env.OUT || '/tmp/shots';
require('fs').mkdirSync(OUT, { recursive: true });

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  const failed = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('requestfailed', (r) => failed.push(r.url().slice(0, 90) + ' :: ' + (r.failure()?.errorText || '')));

  await page.goto(BASE + '/#/', { waitUntil: 'networkidle' });
  await page.waitForSelector('.card', { timeout: 15000 });
  await page.waitForTimeout(1200);

  const home = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('#grid .card')];
    const grid = document.querySelector('#grid');
    const cs = grid ? getComputedStyle(grid) : null;
    const thumbs = [...document.querySelectorAll('#grid .card__thumb img')];
    return {
      cards: cards.length,
      unique: new Set(cards.map((c) => c.querySelector('a.card__title')?.getAttribute('href'))).size,
      columns: cs ? cs.gridTemplateColumns.split(' ').length : 0,
      gridWidth: grid?.getBoundingClientRect().width,
      cardWidth: cards[0]?.getBoundingClientRect().width,
      hOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      loadedThumbs: thumbs.filter((i) => i.naturalWidth > 0).length,
      thumbCount: thumbs.length,
      headerH: document.querySelector('.header')?.getBoundingClientRect().height,
      firstTitle: cards[0]?.querySelector('.card__title')?.textContent?.trim(),
      chipCount: document.querySelectorAll('#chips .chip').length,
      railItems: document.querySelectorAll('.rail .nav-item').length,
    };
  });
  await page.screenshot({ path: OUT + '/01-home.png', fullPage: false });
  await page.screenshot({ path: OUT + '/01-home-full.png', fullPage: true });

  // ---- watch page
  await page.click('#grid .card');
  await page.waitForSelector('.watch__title', { timeout: 10000 });
  await page.waitForTimeout(800);
  const watch = await page.evaluate(() => ({
    title: document.querySelector('.watch__title')?.textContent?.trim(),
    upNext: document.querySelectorAll('.rail-card').length,
    descLen: document.querySelector('#desc')?.textContent?.length,
    playerW: document.querySelector('.player')?.getBoundingClientRect().width,
    playerH: document.querySelector('.player')?.getBoundingClientRect().height,
    hOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
  }));
  await page.screenshot({ path: OUT + '/02-watch.png', fullPage: false });

  // click poster -> iframe
  await page.click('[data-play]');
  await page.waitForTimeout(1200);
  const iframeSrc = await page.evaluate(() => document.querySelector('#player iframe')?.src || null);
  await page.screenshot({ path: OUT + '/03-watch-playing.png' });

  // ---- search
  await page.goto(BASE + '/#/search/physics', { waitUntil: 'networkidle' });
  await page.waitForTimeout(700);
  const search = await page.evaluate(() => ({
    h1: document.querySelector('.page-head h1')?.textContent?.trim(),
    rows: document.querySelectorAll('.list-row').length,
  }));
  await page.screenshot({ path: OUT + '/04-search.png' });

  // ---- subject
  await page.goto(BASE + '/#/about', { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  const about = await page.evaluate(() => ({
    h1: document.querySelector('.page-head h1')?.textContent?.trim(),
    stats: [...document.querySelectorAll('.stat__n')].map((n) => n.textContent),
  }));
  await page.screenshot({ path: OUT + '/05-about.png', fullPage: true });

  // ---- mobile
  const m = await ctx.newPage();
  await m.setViewportSize({ width: 414, height: 896 });
  await m.goto(BASE + '/#/', { waitUntil: 'networkidle' });
  await m.waitForTimeout(900);
  const mobile = await m.evaluate(() => ({
    hOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    cols: getComputedStyle(document.querySelector('#grid')).gridTemplateColumns.split(' ').length,
  }));
  await m.screenshot({ path: OUT + '/06-mobile.png' });

  console.log(JSON.stringify({ home, watch, iframeSrc: iframeSrc?.slice(0, 80), search, about, mobile, errors, failed: failed.slice(0, 8) }, null, 2));
  await browser.close();
})();
