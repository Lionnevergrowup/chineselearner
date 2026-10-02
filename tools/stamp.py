"""Write the version of the page and of the audio files into index.html.

- APP_VERSION: the version number shown on the page ("版本 3 · 2026-10-02"). It goes up by one for
  every update: when anything differs from the last commit, the number becomes the last commit's number + 1
  (running this again before committing keeps that number). The page also compares it with the live site
  to offer "新版本 … 来啦，点这里更新！".
- AUDIO_VERSION: the page loads `audio/manifest.js?v=<version>` and `audio/music.mp3?v=<version>`, so a
  browser can never combine a new page with an older, cached clip list (whose clips may no longer exist).

Run before every commit: python3 tools/stamp.py
(tools/build_audio.py and tools/make_music.py also run it.)
"""
import datetime, hashlib, os, re, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_RE = re.compile(r"var APP_VERSION = \{n:(\d+), date:'([^']*)'\};")


def version(path):
    p = os.path.join(ROOT, path)
    if not os.path.exists(p):
        return '0'
    with open(p, 'rb') as f:
        return hashlib.sha1(f.read()).hexdigest()[:10]


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout


def app_version(html):
    """(number, date) for this update."""
    n, date = (int(m.group(1)), m.group(2)) if (m := APP_RE.search(html)) else (0, '')
    try:
        try:
            committed = APP_RE.search(git('show', 'HEAD:index.html'))
        except subprocess.CalledProcessError:
            committed = None   # index.html is not in the last commit yet
        base = int(committed.group(1)) if committed else 0
        changed = bool(git('status', '--porcelain', '--untracked-files=no').strip()) or bool(git('ls-files', '--others', '--exclude-standard').strip())
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return n, date   # no git: leave it as it is
    if changed and n <= base:
        return base + 1, datetime.date.today().isoformat()
    return n, date


def main():
    page = os.path.join(ROOT, 'index.html')
    html = open(page, encoding='utf-8').read()
    new = re.sub(r"var AUDIO_VERSION = \{manifest:'[^']*', music:'[^']*'\};",
                 f"var AUDIO_VERSION = {{manifest:'{version('audio/manifest.js')}', music:'{version('audio/music.mp3')}'}};", html)
    n, date = app_version(new)
    new = APP_RE.sub(f"var APP_VERSION = {{n:{n}, date:'{date}'}};", new)
    if new != html:
        open(page, 'w', encoding='utf-8').write(new)
    print(f'index.html: version {n} ({date});', re.search(r'var AUDIO_VERSION = [^;]*;', new).group(0))


if __name__ == '__main__':
    main()
