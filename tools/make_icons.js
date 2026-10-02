// Draw the site icons from icons/icon.svg (乐乐 the lion):
//   favicon.ico (16, 32 and 48 px, for browser tabs), icons/apple-touch-icon.png (180 px, iPhone home screen),
//   icons/icon-192.png and icons/icon-512.png (Android, app install), icons/icon-maskable-512.png (Android round icons).
// Usage: NODE_PATH=$(npm root -g) node tools/make_icons.js   (needs the playwright package)
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const svg = fs.readFileSync(path.join(ROOT, 'icons', 'icon.svg'), 'utf8');
const SKY = 'linear-gradient(180deg,#ffe2cf,#fff8e6)';   // the start screen's sky
// 16 px tab icon: bigger eyes, no small details (eye shine, cheeks, mouth), so the face still reads
const small = svg.replace(/<circle[^>]*fill="#fff"\/>/g, '').replace(/<circle[^>]*fill="#ff8f6b"[^>]*\/>/g, '')
  .replace(/<path[^>]*stroke="#5a3426"[^>]*\/>/, '').replace(/r="2\.4" fill="#3a2440"/g, 'r="3.6" fill="#3a2440"');

// lion: share of the icon the lion fills; bg: the sky behind it (none = transparent)
async function render(page, size, {lion = 1, bg = false, art = svg} = {}){
  await page.setViewportSize({width: size, height: size});
  await page.setContent(`<html><body style="margin:0;width:${size}px;height:${size}px;display:grid;place-items:center;background:${bg ? SKY : 'transparent'}">
    <div style="width:${size * lion}px;height:${size * lion}px">${art.replace('<svg ', '<svg width="100%" height="100%" ')}</div></body></html>`);
  return page.screenshot({omitBackground: !bg, clip: {x: 0, y: 0, width: size, height: size}});
}

// An .ico file holding PNG images (supported by every current browser)
function ico(pngs){
  const head = Buffer.alloc(6 + 16 * pngs.length);
  head.writeUInt16LE(0, 0); head.writeUInt16LE(1, 2); head.writeUInt16LE(pngs.length, 4);
  let offset = head.length;
  pngs.forEach(([size, png], i) => {
    const e = 6 + 16 * i;
    head.writeUInt8(size >= 256 ? 0 : size, e); head.writeUInt8(size >= 256 ? 0 : size, e + 1);
    head.writeUInt16LE(1, e + 4); head.writeUInt16LE(32, e + 6);
    head.writeUInt32LE(png.length, e + 8); head.writeUInt32LE(offset, e + 12);
    offset += png.length;
  });
  return Buffer.concat([head, ...pngs.map(p => p[1])]);
}

(async () => {
  const browser = await chromium.launch({executablePath: process.env.CHROMIUM || undefined});
  const page = await browser.newPage({deviceScaleFactor: 1});
  const out = (name, buf) => { fs.writeFileSync(path.join(ROOT, name), buf); console.log(`${name}: ${buf.length} bytes`); };
  const tab = [];
  for (const s of [16, 32, 48]) tab.push([s, await render(page, s, {art: s <= 16 ? small : svg})]);
  out('favicon.ico', ico(tab));
  out('icons/apple-touch-icon.png', await render(page, 180, {lion: 0.8, bg: true}));
  out('icons/icon-192.png', await render(page, 192, {lion: 0.8, bg: true}));
  out('icons/icon-512.png', await render(page, 512, {lion: 0.8, bg: true}));
  out('icons/icon-maskable-512.png', await render(page, 512, {lion: 0.62, bg: true}));   // inside the round safe zone
  await browser.close();
})();
