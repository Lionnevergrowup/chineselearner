"""Copy the stroke-order data of every character the game asks a child to write into hanzi/.

The data is the hanzi-writer-data package (derived from Make Me a Hanzi, Arphic Public License,
see hanzi/ARPHICPL.TXT). Each character is saved as hanzi/<code point in hex>.json, which is
the file the page loads (hanziFile() in index.html).

Usage:
  python3 tools/build_hanzi.py [path/to/hanzi-writer-data]
Without a path the files are downloaded from the jsdelivr CDN.
"""
import json, os, re, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'hanzi')
CDN = 'https://cdn.jsdelivr.net/npm/hanzi-writer-data@2.0.1/'


def write_chars():
    html = open(os.path.join(ROOT, 'index.html'), encoding='utf-8').read()
    chars = []
    for m in re.finditer(r"write:\[([^\]]*)\]", html):
        for c in re.findall(r"'([^']+)'", m.group(1)):
            if c not in chars:
                chars.append(c)
    return chars


def load(c, src):
    if src:
        with open(os.path.join(src, c + '.json'), encoding='utf-8') as f:
            return json.load(f)
    url = CDN + urllib.parse.quote(c) + '.json'
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else None
    os.makedirs(OUT, exist_ok=True)
    chars = write_chars()
    keep = set()
    for c in chars:
        name = format(ord(c), 'x') + '.json'
        keep.add(name)
        data = load(c, src)
        with open(os.path.join(OUT, name), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    for name in os.listdir(OUT):
        if name.endswith('.json') and name not in keep:
            os.remove(os.path.join(OUT, name))
    print(f'{len(chars)} characters: {"".join(chars)}')


if __name__ == '__main__':
    import urllib.parse
    main()
