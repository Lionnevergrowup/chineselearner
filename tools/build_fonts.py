"""Make the two fonts the page loads, cut down to the characters it uses.

- fonts/kai.woff2: AR PL KaitiM GB (Arphic Public License, fonts/LICENSE-ArphicPL.txt), a textbook-style
  Kai script, with every Chinese character in index.html. It is the font the stroke-order data in
  hanzi/ was made from, so the characters to read and to write look the same.
- fonts/andika-400.woff2, fonts/andika-700.woff2: Andika (SIL Open Font License, fonts/OFL-Andika.txt)
  with the letters and tone marks pinyin needs (ā á ǎ à … ǖ ǘ ǚ ǜ), from Google Fonts.

Usage:
  pip install fonttools brotli
  # gkai00mp.ttf is in the Debian / Ubuntu package fonts-arphic-gkai00mp
  python3 tools/build_fonts.py /usr/share/fonts/truetype/arphic-gkai00mp/gkai00mp.ttf
Run it again after adding characters to the lessons.
"""
import os, re, subprocess, sys, tempfile, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, 'fonts')
HAN = re.compile(r'[㐀-鿿]')
CJK_PUNCT = '，。！？、：；“”‘’（）《》…·'
PINYIN = ''.join(chr(c) for c in range(0x20, 0x7f)) + 'āáǎàōóǒòēéěèīíǐìūúǔùǖǘǚǜüÜ…→·'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'


def page_han():
    html = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
    return ''.join(sorted(set(HAN.findall(html)))) + CJK_PUNCT


def kai(src):
    text = page_han()
    with tempfile.NamedTemporaryFile('w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(text)
    out = os.path.join(FONTS, 'kai.woff2')
    subprocess.run([sys.executable, '-m', 'fontTools.subset', src, f'--text-file={f.name}', '--flavor=woff2',
                    f'--output-file={out}', '--no-hinting', '--desubroutinize', '--layout-features=*',
                    '--name-IDs=*', '--name-languages=*'], check=True, capture_output=True)
    os.unlink(f.name)
    print(f'kai.woff2: {len(text)} characters, {os.path.getsize(out) // 1024} KB')


def andika():
    for weight in (400, 700):
        q = urllib.parse.urlencode({'family': f'Andika:wght@{weight}', 'text': PINYIN})
        req = urllib.request.Request('https://fonts.googleapis.com/css2?' + q, headers={'User-Agent': UA})
        css = urllib.request.urlopen(req, timeout=30).read().decode()
        url = re.search(r'url\((https://[^)]+)\)', css).group(1)
        data = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=30).read()
        out = os.path.join(FONTS, f'andika-{weight}.woff2')
        open(out, 'wb').write(data)
        print(f'andika-{weight}.woff2: {len(data) // 1024} KB')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    kai(sys.argv[1])
    andika()
