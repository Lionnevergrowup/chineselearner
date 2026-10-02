// Writes tools/phrases.json: every line the game can speak (window.__zhPhrases in index.html)
// and the pinyin of every lesson text (window.__zhPinyin), so tools/build_audio.py reads each character right.
// Usage: NODE_PATH=$(npm root -g) node tools/export_phrases.js   (needs the `playwright` package)
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM || undefined});
  const page = await browser.newPage();
  await page.goto('file://' + path.resolve(__dirname, '..', 'index.html'));
  const data = await page.evaluate(() => ({phrases: window.__zhPhrases(), pinyin: window.__zhPinyin()}));
  await browser.close();
  fs.writeFileSync(path.join(__dirname, 'phrases.json'), JSON.stringify(data, null, 1) + '\n');
  console.log(`${data.phrases.length} phrases (${Object.keys(data.pinyin).length} with their pinyin) -> tools/phrases.json`);
})();
