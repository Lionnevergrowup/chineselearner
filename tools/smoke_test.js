// Open every lesson and every activity in a headless browser and report page errors.
// Usage: python3 -m http.server 8765 &   then   NODE_PATH=$(npm root -g) node tools/smoke_test.js [http://localhost:8765/] [out-dir]
const { chromium } = require('playwright');
const fs = require('fs');

const BASE = process.argv[2] || 'http://localhost:8765/';
const OUT = process.argv[3] || null;

(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM || undefined});
  const errors = [];
  for (const vp of [{width: 390, height: 844, name: 'phone'}, {width: 1180, height: 820, name: 'tablet'}]){
    const page = await browser.newPage({viewport: {width: vp.width, height: vp.height}, deviceScaleFactor: 1});
    page.on('pageerror', e => errors.push(`[${vp.name}] pageerror ${page.url()}: ${e.message}`));
    page.on('console', m => { if (m.type() === 'error') errors.push(`[${vp.name}] console ${page.url()}: ${m.text()}`); });
    await page.goto(BASE + '#/', {waitUntil: 'load'});
    await page.click('.splash .btn.green');
    await page.waitForTimeout(300);
    if (OUT) await page.screenshot({path: `${OUT}/${vp.name}-home.png`, fullPage: true});
    const n = await page.evaluate(() => document.querySelectorAll('.lesson-btn').length);
    for (let l = 1; l <= n; l++){
      await page.evaluate(h => { location.hash = h; }, `#/lesson/${l}`);
      await page.waitForTimeout(150);
      const acts = await page.evaluate(() => [...document.querySelectorAll('.act-card')].map(b => b.getAttribute('aria-label')));
      if (OUT && vp.name === 'phone' && (l === 1 || l === 7 || l === 19)) await page.screenshot({path: `${OUT}/${vp.name}-lesson${l}.png`, fullPage: true});
      for (let k = 0; k < acts.length; k++){
        await page.evaluate(([l, k]) => { document.querySelectorAll('.act-card')[k].click(); }, [l, k]);
        await page.waitForTimeout(250);
        const hash = await page.evaluate(() => location.hash);
        if (OUT && vp.name === 'phone' && (l === 1 || l === 7 || l === 13 || l === 24)) await page.screenshot({path: `${OUT}/${vp.name}-${hash.replace(/[#/]+/g, '-')}.png`});
        await page.evaluate(h => { location.hash = h; }, `#/lesson/${l}`);
        await page.waitForTimeout(100);
      }
    }
    for (const h of ['#/stickers', '#/parents']){
      await page.evaluate(h => { location.hash = h; }, h);
      await page.waitForTimeout(200);
      if (OUT) await page.screenshot({path: `${OUT}/${vp.name}-${h.slice(2)}.png`, fullPage: true});
    }
    // parents page: every setting, a few ticks, then clearing the progress (answering the grown-up sum)
    const segs = await page.evaluate(() => document.querySelectorAll('.seg button').length);
    for (let k = 0; k < segs; k++){
      await page.evaluate(k => document.querySelectorAll('.seg button')[k].click(), k);
      await page.waitForTimeout(60);
    }
    for (let k = 0; k < 3; k++){ await page.evaluate(() => document.querySelector('.check-btn').click()); await page.waitForTimeout(60); }
    await page.evaluate(() => [...document.querySelectorAll('.btn.red')].pop().click());
    await page.waitForTimeout(150);
    const sum = await page.evaluate(() => document.querySelector('.gate label').textContent.match(/(\d+) \+ (\d+)/).slice(1).map(Number).reduce((a, b) => a + b));
    await page.fill('.gate input', '1');
    await page.evaluate(() => document.querySelector('.overlay .btn.red').click());
    await page.waitForTimeout(100);
    await page.fill('.gate input', String(sum));
    await page.evaluate(() => document.querySelector('.overlay .btn.red').click());
    await page.waitForTimeout(200);
    const cleared = await page.evaluate(() => document.querySelector('.overlay h1') && document.querySelector('.overlay h1').textContent);
    if (cleared !== '记录已清除') errors.push(`[${vp.name}] reset did not finish: ${cleared}`);
    // with pinyin hidden and the short game length, a lesson still opens and plays its first screen
    await page.evaluate(() => { location.hash = '#/lesson/27/sentence'; });
    await page.waitForTimeout(300);
    if (OUT) await page.screenshot({path: `${OUT}/${vp.name}-nopinyin-sentence.png`});
    await page.close();
  }
  await browser.close();
  console.log(errors.length ? errors.join('\n') : 'no errors');
  process.exit(errors.length ? 1 : 0);
})();
