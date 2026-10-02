// Play every activity of every lesson to the end in a headless browser, answering like a child who knows the answers:
// cards are tapped, quiz answers are found through the page's test hook (window.__quiz), characters are written
// stroke by stroke along the stroke data's median lines (so the real Hanzi Writer stroke check runs), and pictures
// are drawn and labelled. Reports page errors, activities that did not finish, and lines 乐乐 says without a clip.
// Usage: python3 -m http.server 8765 &   then   NODE_PATH=$(npm root -g) node tools/play_test.js [base-url] [lessons, e.g. 1-32]
const { chromium } = require('playwright');

const BASE = process.argv[2] || 'http://localhost:8765/';
const [from, to] = (process.argv[3] || '1-32').split('-').map(Number);
const sleep = ms => new Promise(r => setTimeout(r, ms));
// WRONG=1: before each right answer, tap one or two wrong ones (checks the "try again" paths and the hints)
const WRONG = !!process.env.WRONG;
async function tapWrong(page, right, n = 1){
  const wrong = await page.evaluate(right => [...document.querySelectorAll('.stage [data-v]:not(.used)')].map(b => b.dataset.v).filter(v => !right.includes(v)), right);
  for (const v of [...new Set(wrong)].slice(0, n)){
    await page.click(`.stage [data-v="${v.replace(/"/g, '\\"')}"]:not(.used)`, {timeout: 3000, force: true}).catch(() => {});
    await sleep(450);
  }
}

async function writeChar(page){
  // draw each stroke along its median (Hanzi Writer's own coordinates → screen)
  const strokes = await page.evaluate(async () => {
    const c = window.__quiz.answer;
    const data = await fetch('hanzi/' + c.codePointAt(0).toString(16) + '.json').then(r => r.json());
    const box = document.querySelector('.grid-box .hw svg') || document.querySelector('.grid-box .hw');
    const r = box.getBoundingClientRect();
    const size = r.width, pad = Math.round(size * 0.08);
    const t = HanziWriter.getScalingTransform(size, size, pad);
    return data.medians.map(m => m.map(([x, y]) => ({x: r.left + t.x + x * t.scale, y: r.top + size - t.y - y * t.scale})));
  });
  for (const pts of strokes){
    await page.mouse.move(pts[0].x, pts[0].y);
    await page.mouse.down();
    for (let k = 1; k < pts.length; k++){
      const a = pts[k - 1], b = pts[k];
      for (let s = 1; s <= 4; s++) await page.mouse.move(a.x + (b.x - a.x) * s / 4, a.y + (b.y - a.y) * s / 4);
    }
    await page.mouse.up();
    await sleep(380);
  }
}

async function playActivity(page, l, key){
  let lastQ = await page.evaluate(() => window.__quiz && window.__quiz.n || 0);   // questions of earlier activities do not count
  await page.evaluate(h => { location.hash = h; }, `#/lesson/${l}/${key}`);
  await sleep(250);
  let drawn = false, wroteReal = 0, wroteHook = 0;
  const t0 = Date.now();
  while (Date.now() - t0 < 120000){
    const s = await page.evaluate(() => {
      const vis = el => el && !el.hidden && el.offsetParent !== null;
      const done = !!document.querySelector('.overlay .big-star');
      const cards = [...document.querySelectorAll('.sound-card:not(.seen),.char-card:not(.seen),.word-card:not(.seen),.tone-card:not(.seen)')].filter(vis).length;
      const bigBtns = [...document.querySelectorAll('.stage .btn.big')].filter(vis).map(b => b.textContent);
      return {done, cards, bigBtns, q: window.__quiz && window.__quiz.n || 0, draw: !!document.querySelector('.draw-wrap')};
    });
    if (s.done) return {ok: true, wroteReal, wroteHook};
    if (s.draw && !drawn){
      const r = await page.evaluate(() => { const b = document.querySelector('.draw-wrap canvas').getBoundingClientRect(); return {x: b.left, y: b.top, w: b.width, h: b.height}; });
      await page.mouse.move(r.x + r.w * 0.3, r.y + r.h * 0.4); await page.mouse.down();
      await page.mouse.move(r.x + r.w * 0.6, r.y + r.h * 0.5, {steps: 8}); await page.mouse.up();
      await page.click('.word-bank .wchip');
      await sleep(100);
      await page.click('.stage .btn.green.big');
      drawn = true; await sleep(400); continue;
    }
    if (s.q > lastQ){
      lastQ = s.q;
      await sleep(420);   // a new question ignores taps for a moment
      const q = await page.evaluate(() => window.__quiz);
      if (q.type === 'trace'){ await page.evaluate(() => window.__pass()); }
      else if (q.type === 'write'){
        await writeChar(page);
        await sleep(600);
        const finished = await page.evaluate(() => !!document.querySelector('.grid-box.win'));
        if (finished) wroteReal++; else { wroteHook++; await page.evaluate(() => window.__pass && window.__pass()); }
      }
      else if (q.taps){
        if (WRONG) await tapWrong(page, [q.taps[0]]);
        for (const t of q.taps){
          const sel = `.stage [data-v="${t.replace(/"/g, '\\"')}"]:not(.used)`;
          await page.click(sel, {timeout: 3000, force: true});
          await sleep(60);
        }
      } else {
        if (WRONG) await tapWrong(page, [String(q.answer)], 2);
        try {
          await page.click(`.stage [data-v="${String(q.answer).replace(/"/g, '\\"')}"]`, {timeout: 3000, force: true});
        } catch (e) {
          const have = await page.evaluate(() => [...document.querySelectorAll('[data-v]')].map(x => x.dataset.v));
          console.log(`lesson ${l} ${key}: no button for ${JSON.stringify(q)}; buttons: ${JSON.stringify(have)}`);
          return {ok: false};
        }
      }
      await sleep(250);
      continue;
    }
    if (s.cards){
      const n = s.cards;
      for (let k = 0; k < n; k++){
        await page.evaluate(() => {
          const el = [...document.querySelectorAll('.sound-card:not(.seen),.char-card:not(.seen),.word-card:not(.seen),.tone-card:not(.seen)')][0];
          if (el) el.click();
        });
        await sleep(120);
      }
      await sleep(200);
      continue;
    }
    if (s.bigBtns.length){
      // 开始 / 拼！ / 下一个 / 我读好了
      const label = s.bigBtns.find(t => /下一个/.test(t)) || s.bigBtns.find(t => /拼！/.test(t)) || s.bigBtns.find(t => /开始|读好了/.test(t)) || s.bigBtns[0];
      await page.evaluate(label => { const b = [...document.querySelectorAll('.stage .btn.big')].find(x => x.textContent === label && !x.hidden); if (b) b.click(); }, label);
      await sleep(350);
      continue;
    }
    await sleep(150);
  }
  return {ok: false};
}

(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM || undefined});
  const page = await browser.newPage({viewport: {width: 1024, height: 900}});
  const errors = [];
  page.on('pageerror', e => errors.push(`pageerror ${page.url()}: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error' && !/music\.mp3/.test(m.text())) errors.push(`console ${page.url()}: ${m.text()}`); });
  await page.addInitScript(() => { window.__quiz = {}; window.__fastSpeech = true; window.__clipMiss = []; });
  await page.goto(BASE + '#/', {waitUntil: 'load'});
  await page.click('.splash .btn.green');
  await sleep(200);
  const failed = [];
  let acts = 0, real = 0, hook = 0;
  for (let l = from; l <= to; l++){
    await page.evaluate(h => { location.hash = h; }, `#/lesson/${l}`);
    await sleep(150);
    const list = await page.evaluate(l => window.__zhActs(l), l);
    for (const key of list){
      const r = await playActivity(page, l, key);
      acts++;
      if (!r.ok) failed.push(`lesson ${l} ${key}`);
      real += r.wroteReal || 0; hook += r.wroteHook || 0;
    }
    const done = await page.evaluate(l => JSON.parse(localStorage.getItem('zhongwen-leyuan-v1')).done[l] || {}, l);
    process.stdout.write(`lesson ${l}: ${Object.keys(done).length}/${list.length} done\n`);
  }
  const miss = await page.evaluate(() => [...new Set(window.__clipMiss)]);
  await browser.close();
  console.log(`${acts} activities played, ${failed.length} did not finish${failed.length ? ': ' + failed.join(', ') : ''}`);
  console.log(`characters written with real strokes: ${real}, finished by the test hook: ${hook}`);
  console.log(`lines without a clip: ${miss.length}${miss.length ? '\n  ' + miss.slice(0, 40).join('\n  ') : ''}`);
  console.log(errors.length ? errors.slice(0, 30).join('\n') : 'no page errors');
  process.exit(failed.length || errors.length ? 1 : 0);
})();
