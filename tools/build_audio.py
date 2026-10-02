"""Record 乐乐's voice: one MP3 per phrase in tools/phrases.json, plus audio/manifest.js.

Voice: Kokoro-82M v1.1-zh (Apache-2.0), run locally with onnxruntime. Chinese text becomes phonemes with
misaki[zh] (jieba + pypinyin + tone sandhi); lesson texts are read with the pinyin written in index.html
(tools/phrases.json carries it), so characters with two readings (长, 了, 地) are always read right.
A phrase that is a single pinyin syllable (bā, ǚ, zhī) is one sound for the pinyin games. Said on its own the
model gives every syllable the same rise and fall, so the textbook tone shape (一声平, 二声扬, 三声拐弯, 四声降)
is put on it with Praat's PSOLA (parselmouth): the four tones always sound clearly different.

Usage:
  pip install onnxruntime numpy "misaki[zh]" lameenc praat-parselmouth
  # model files from https://huggingface.co/onnx-community/Kokoro-82M-v1.1-zh-ONNX :
  #   onnx/model.onnx, tokenizer.json and voices/<VOICE>.bin, all in one folder (voices/ inside it)
  NODE_PATH=$(npm root -g) node tools/export_phrases.js
  python3 tools/build_audio.py path/to/kokoro-zh [--all] [--redo "phrase" ...] [--show]
Existing clips are reused, so re-running only records new phrases (plus any passed with --redo, or everything
with --all). --show prints the pinyin each phrase would be read with, without recording.
A clip is named after its content, so browsers never play a stale cached copy.
"""
import hashlib, json, os, re, sys
import numpy as np
import lameenc

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(ROOT, 'audio')
VOICE = 'zf_078'      # of the 58 Chinese voices, the one speech recognition understood best (and a lively one)
SPEED = 0.88          # a little slower than normal speech, for young children
RATE = 24000
HOP = 600             # samples per duration step of the model

# Readings for lines that are not lesson texts, where the automatic reading would be wrong or unclear.
PINYIN_FIX = {
    '它是哪个声母开头的？': 'tā shì nǎ ge shēng mǔ kāi tóu de',
    '哪个字和图片一样？': 'nǎ ge zì hé tú piàn yí yàng',
    '这个拼音是哪个字？': 'zhè ge pīn yīn shì nǎ ge zì',
    '哪个拼音和图片一样？': 'nǎ ge pīn yīn hé tú piàn yí yàng',
    '哪个词和图片一样？': 'nǎ ge cí hé tú piàn yí yàng',
    '缺了哪个字？': 'quē le nǎ ge zì',
    '读一读，缺了哪个词？': 'dú yi dú quē le nǎ ge cí',
    '前音轻短后音重，两音相连猛一碰。': 'qián yīn qīng duǎn hòu yīn zhòng liǎng yīn xiāng lián měng yí pèng',
    '做得好！': 'zuò de hǎo',
    '差一点点，再来一次！': 'chà yì diǎn diǎn zài lái yí cì',
}

HAN = re.compile(r'[㐀-鿿]')
TONED = {'ā': ('a', 1), 'á': ('a', 2), 'ǎ': ('a', 3), 'à': ('a', 4), 'ō': ('o', 1), 'ó': ('o', 2), 'ǒ': ('o', 3), 'ò': ('o', 4),
         'ē': ('e', 1), 'é': ('e', 2), 'ě': ('e', 3), 'è': ('e', 4), 'ī': ('i', 1), 'í': ('i', 2), 'ǐ': ('i', 3), 'ì': ('i', 4),
         'ū': ('u', 1), 'ú': ('u', 2), 'ǔ': ('u', 3), 'ù': ('u', 4), 'ǖ': ('ü', 1), 'ǘ': ('ü', 2), 'ǚ': ('ü', 3), 'ǜ': ('ü', 4)}
SYLLABLE = re.compile('^[a-zü' + ''.join(TONED) + ']+$')


def is_syllable(p):
    return bool(SYLLABLE.match(p))


# ---------------------------------------------------------------- pinyin -> phonemes
_g2p = None
_queue = []
_forcing = False


def g2p():
    """misaki's Chinese G2P; while _queue holds syllables, characters are read with them instead of pypinyin's guess."""
    global _g2p
    if _g2p is None:
        from misaki import zh
        _g2p = zh.ZHG2P(version='1.1')
        front = _g2p.frontend
        orig = front._get_initials_finals

        def forced(word):
            if not _queue:
                return orig(word)
            initials, finals = [], []
            for c in word:
                if HAN.match(c):
                    ini, fin = split_syllable(_queue.pop(0))
                    initials.append(ini)
                    finals.append(fin)
                else:
                    a, b = orig(c)
                    initials += a
                    finals += b
            return initials, finals
        front._get_initials_finals = forced
        # With the pinyin given, its neutral tones are already right: keep only the sandhi pinyin does not write
        # (3rd tone before 3rd tone; 一 and 不 are written as said). The automatic neutral-tone rules would
        # otherwise read 大地 as dàdi and 鹅鹅鹅 as é e e.
        tm = front.tone_modifier
        full = tm.modified_tone

        def modified(word, pos, finals):
            if not _forcing:
                return full(word, pos, finals)
            finals = tm._bu_sandhi(word, finals)
            finals = tm._yi_sandhi(word, finals)
            return tm._three_sandhi(word, finals)
        tm.modified_tone = modified
    return _g2p


def split_syllable(s):
    """'shì' -> ('sh', 'iii4'), 'yǔ' -> ('', 'v3'), 'men' -> ('m', 'en5'): the form misaki's frontend uses."""
    from pypinyin.contrib.tone_convert import to_initials, to_finals_tone3
    ini = to_initials(s, strict=True)
    fin = to_finals_tone3(s, strict=True, neutral_tone_with_five=True)
    if not fin[-1].isdigit():
        fin += '5'
    base, tone = fin[:-1], fin[-1]
    if base == 'i' and ini in ('z', 'c', 's'):
        base = 'ii'
    elif base == 'i' and ini in ('zh', 'ch', 'sh', 'r'):
        base = 'iii'
    return ini, base + tone


def syllable_phonemes(s, tone=None):
    from misaki.zh_frontend import ZH_MAP
    ini, fin = split_syllable(s)
    return (ZH_MAP[ini] if ini else '') + ZH_MAP[fin[:-1]] + str(tone or fin[-1])


def text_phonemes(text, pinyin=None):
    """Phonemes for a Chinese phrase; with pinyin (one syllable per character) the characters are read that way."""
    global _queue, _forcing
    g = g2p()
    if pinyin:
        syl = pinyin.split()
        if len(syl) != len(HAN.findall(text)):
            raise SystemExit(f'pinyin does not match the characters: {text!r} / {pinyin!r}')
        _queue = list(syl)
        _forcing = True
    try:
        ph = g(text)[0]
    finally:
        left, _queue, _forcing = _queue, [], False
    if left:
        raise SystemExit(f'not every syllable was used for {text!r}: {left}')
    if '❓' in ph:
        raise SystemExit(f'unknown sound in {text!r}: {ph}')
    return ph


ZH_BACK = None


def phonemes_to_pinyin(ph):
    """Readable form of the phonemes (for --show): ㄋㄧ2ㄏㄠ3 -> n i2 h ao3."""
    global ZH_BACK
    if ZH_BACK is None:
        from misaki.zh_frontend import ZH_MAP
        ZH_BACK = {v: k for k, v in ZH_MAP.items() if len(v) == 1 and not v.isdigit() and v not in ';:,.!?/—…"()“” R'}
    return ''.join(ZH_BACK.get(c, c) + (' ' if c.isdigit() else '') for c in ph)


# ---------------------------------------------------------------- the model
class Kokoro:
    def __init__(self, folder, voice=VOICE):
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, (os.cpu_count() or 2))
        self.sess = ort.InferenceSession(os.path.join(folder, 'onnx', 'model.onnx') if os.path.exists(os.path.join(folder, 'onnx')) else os.path.join(folder, 'model.onnx'),
                                         so, providers=['CPUExecutionProvider'])
        self.vocab = json.load(open(os.path.join(folder, 'tokenizer.json'), encoding='utf-8'))['model']['vocab']
        self.voice = np.fromfile(os.path.join(folder, 'voices', voice + '.bin'), dtype=np.float32).reshape(-1, 1, 256)
        self.names = [i.name for i in self.sess.get_inputs()]

    def run(self, ph, speed=SPEED):
        missing = [c for c in ph if c not in self.vocab]
        if missing:
            raise SystemExit(f'phonemes not in the model: {missing} in {ph!r}')
        ids = [self.vocab[c] for c in ph]
        if len(ids) > 500:
            raise SystemExit(f'phrase too long: {ph!r}')
        toks = np.array([[0, *ids, 0]], dtype=np.int64)
        audio, dur = self.sess.run(None, {self.names[0]: toks, self.names[1]: self.voice[len(ids)].astype(np.float32),
                                          self.names[2]: np.array([speed], dtype=np.float32)})
        return audio.reshape(-1).astype(np.float32), dur.reshape(-1)


# ---------------------------------------------------------------- one syllable with an exact tone
# Chao tone letters as (time fraction, level 1..5)
CONTOUR = {
    1: [(0, 4.9), (0.5, 4.9), (1, 4.7)],
    2: [(0, 3.0), (0.3, 2.8), (1, 5.0)],
    3: [(0, 2.3), (0.45, 1.0), (0.62, 1.0), (1, 3.8)],
    4: [(0, 5.0), (0.15, 5.1), (1, 1.4)],
    5: [(0, 3.0), (1, 2.2)],
}
DURATION = {1: 1.15, 2: 1.2, 3: 1.4, 4: 1.0, 5: 0.8}   # syllables are said at normal speed, then slowed down
LOW, HIGH = 160.0, 300.0   # pitch range of the voice for tone level 1 and 5 (set from the voice in main())


def trim(x, thr=0.01, pad=0.03):
    idx = np.where(np.abs(x) > thr * (np.abs(x).max() or 1))[0]
    if not len(idx):
        return x
    return x[max(0, idx[0] - int(pad * RATE)): min(len(x), idx[-1] + int(pad * RATE))]


def impose_tone(x, tone):
    import parselmouth
    from parselmouth.praat import call
    x = trim(x)
    snd = parselmouth.Sound(x.astype(np.float64), RATE)
    p = snd.to_pitch(time_step=0.005, pitch_floor=90, pitch_ceiling=600)
    f = p.selected_array['frequency']
    voiced = np.where(f > 0)[0]
    manip = call(snd, 'To Manipulation', 0.005, 90, 600)
    if len(voiced) >= 3:
        t0, t1 = p.xs()[voiced[0]], p.xs()[voiced[-1]]
        pt = call(manip, 'Extract pitch tier')
        call(pt, 'Remove points between', 0, snd.duration)
        for frac, lev in CONTOUR[tone]:
            call(pt, 'Add point', t0 + frac * (t1 - t0), LOW * (HIGH / LOW) ** ((lev - 1) / 4))
        call([pt, manip], 'Replace pitch tier')
        ds = DURATION[tone]
        if abs(ds - 1) > 1e-3:
            dt = call(manip, 'Extract duration tier')
            call(dt, 'Add point', max(0, t0 - 0.001), 1.0)
            call(dt, 'Add point', t0 + 0.02, ds)
            call(dt, 'Add point', t1, ds)
            call(dt, 'Add point', min(snd.duration, t1 + 0.001), 1.0)
            call([manip, dt], 'Replace duration tier')
    out = call(manip, 'Get resynthesis (overlap-add)')
    return out.values[0].astype(np.float32)


# Finals on their own, as the pinyin games write them (uī, iū, ǖn …), sound like these syllables.
SPEAK_AS = {'i': 'yi', 'u': 'wu', 'ü': 'yu', 'ui': 'wei', 'iu': 'you', 'ie': 'ye', 'üe': 'yue', 'in': 'yin', 'un': 'wen',
            'ün': 'yun', 'ing': 'ying'}
MARKS = {'a': 'āáǎà', 'o': 'ōóǒò', 'e': 'ēéěè', 'i': 'īíǐì', 'u': 'ūúǔù', 'ü': 'ǖǘǚǜ'}


def with_tone(base, t):
    """Put tone t on a plain syllable, where pinyin writes it: on a or e, on the o of ou, else on the last vowel."""
    if not 1 <= t <= 4:
        return base
    i = base.find('a')
    if i < 0:
        i = base.find('e')
    if i < 0 and 'ou' in base:
        i = base.find('o')
    if i < 0:
        i = max(k for k, c in enumerate(base) if c in MARKS)
    return base[:i] + MARKS[base[i]][t - 1] + base[i + 1:]


def syllable(kokoro, s):
    """One syllable on its own (the model says it most clearly that way), with the exact tone shape put on it."""
    tone, plain = 5, ''
    for c in s:
        if c in TONED:
            tone = TONED[c][1]
            plain += TONED[c][0]
        else:
            plain += c
    if plain in SPEAK_AS:
        s = with_tone(SPEAK_AS[plain], tone)
    ph = syllable_phonemes(s, 1 if tone == 5 else tone)
    x, dur = kokoro.run(ph, 1.0)
    return impose_tone(speech_only(x, ph, dur), tone)


def frame_db(x):
    """Loudness of every model step (HOP samples), in dB below the loudest one."""
    e = np.array([np.sqrt(np.mean(x[i:i + HOP] ** 2)) for i in range(0, len(x), HOP)])
    return 20 * np.log10(e / (e.max() or 1) + 1e-9)


# How long each initial sounds before the vowel's voicing starts, in model steps (25 ms).
LEADIN = {'b': 1, 'd': 1, 'g': 1, 'm': 1, 'n': 1, 'l': 1, 'r': 2, 'p': 3, 't': 3, 'k': 3, 'j': 3, 'z': 3, 'zh': 3,
          'q': 5, 'c': 5, 'ch': 5, 'f': 5, 'h': 4, 'x': 5, 's': 5, 'sh': 5, '': 1}
VOICED_INITIAL = set('mnlr') | {''}


def voiced_frames(x):
    import parselmouth
    p = parselmouth.Sound(x.astype(np.float64), RATE).to_pitch(time_step=HOP / RATE, pitch_floor=90, pitch_ceiling=600)
    f, t = p.selected_array['frequency'], p.xs()
    n = int(np.ceil(len(x) / HOP))
    out = np.zeros(n, bool)
    for fi, ti in zip(f, t):
        if fi > 0:
            out[min(n - 1, int(ti * RATE / HOP))] = True
    return out


def first_initial(ph):
    from misaki.zh_frontend import ZH_MAP
    back = {v: k for k, v in ZH_MAP.items() if k in LEADIN}
    for c in ph:
        if c not in SEPARATORS and c not in PAUSES:
            return back.get(c, '')
    return ''


def speech_only(x, ph, dur):
    """Cut off the stray murmur the model makes while it waits to start (its leading pad) and after the last sound.
    The speech starts a few steps before the pad's predicted end: it is found where the first vowel's voicing starts,
    less the time the first initial sounds before it (b: 25 ms, s: 125 ms). The end is where the last syllable has
    faded 15 dB below its own peak."""
    e, v = frame_db(x), voiced_frames(x)
    cum = np.concatenate([[0], np.cumsum(dur)]).astype(int)
    lead = cum[1]
    ini = first_initial(ph)
    v0 = None
    for i in range(max(0, lead - 12), min(len(e), lead + 8)):
        if v[i] and e[i] > -20:
            v0 = i
            break
    if v0 is None:
        start = max(0, lead - 2)
    else:
        if ini in VOICED_INITIAL:   # a nasal or a glide starts softer than the vowel
            while v0 > max(0, lead - 14) and v[v0 - 1] and e[v0 - 1] > -24:
                v0 -= 1
        start = max(0, v0 - LEADIN.get(ini, 1))
    spans = syllable_spans(ph)
    if spans:
        a, b = spans[-1][0], spans[-1][1]
        s0, s1 = cum[a + 1], min(len(e), cum[b + 2])
        peak = e[s0:s1].max() if s1 > s0 else 0
        end = s1
        while end > s0 and e[end - 1] < peak - 15:
            end -= 1
        end = min(len(e), end + 3)
    else:
        end = len(e)
    y = x[start * HOP:end * HOP].copy()
    fi, fo = min(len(y) // 4, int(0.008 * RATE)), min(len(y) // 4, int(0.06 * RATE))
    if fi:
        y[:fi] *= np.linspace(0, 1, fi)
    if fo:
        y[-fo:] *= np.linspace(1, 0, fo)
    return y


SEPARATORS = set(' /')
PAUSES = set(';:,.!?—…')


def syllable_spans(ph):
    """[(first token, tone token, tone, ends a phrase)] for every syllable in the phonemes."""
    out, start = [], None
    for i, c in enumerate(ph):
        if c in SEPARATORS or c in PAUSES or c in '"()“”':
            continue
        if start is None:
            start = i
        if c in '12345':
            rest = ph[i + 1:].lstrip(' /R')
            out.append((start, i, int(c), not rest or rest[0] in PAUSES))
            start = None
    return out


def fix_final_tones(x, ph, dur):
    """The model lets a first or second tone that ends a phrase fall (鸽子的鸽 sounds like 各子的各): give every such
    syllable its level (1) or rising (2) shape back, starting from where its pitch begins (Praat PSOLA)."""
    import parselmouth
    from parselmouth.praat import call
    cum = np.concatenate([[0], np.cumsum(dur)]) * HOP
    todo = []
    snd = parselmouth.Sound(x.astype(np.float64), RATE)
    pitch = snd.to_pitch(time_step=0.005, pitch_floor=90, pitch_ceiling=600)
    f, t = pitch.selected_array['frequency'], pitch.xs()
    for a, b, tone, final in syllable_spans(ph):
        if not final or tone not in (1, 2):
            continue
        s0, s1 = cum[a + 1] / RATE, cum[b + 2] / RATE   # +1: the model's leading pad token
        sel = (t >= s0) & (t < s1) & (f > 0)
        v, tv = f[sel], t[sel]
        if len(v) < 6:
            continue
        n = len(v)
        onset = float(np.median(v[:max(2, n // 4)]))
        end = float(np.median(v[-max(2, n // 4):]))
        change = 12 * np.log2(end / onset)
        if tone == 1 and change < -1.2:
            points = [(tv[0], onset), (tv[-1], onset * 2 ** (-0.5 / 12))]
        elif tone == 2 and change < 2.5:
            low = min(onset, float(np.min(v[:max(2, n // 2)])))
            points = [(tv[0], low), (tv[0] + 0.3 * (tv[-1] - tv[0]), low * 2 ** (-0.3 / 12)), (tv[-1], low * 2 ** (5 / 12))]
        else:
            continue
        todo.append((tv[0], tv[-1], points))
    if not todo:
        return x
    manip = call(snd, 'To Manipulation', 0.005, 90, 600)
    pt = call(manip, 'Extract pitch tier')
    for t0, t1, points in todo:
        call(pt, 'Remove points between', t0 - 0.004, t1 + 0.004)
        for tt, hz in points:
            call(pt, 'Add point', float(tt), float(hz))
    call([pt, manip], 'Replace pitch tier')
    return call(manip, 'Get resynthesis (overlap-add)').values[0].astype(np.float32)


def phrase_audio(kokoro, phrase, pinyin_of):
    if is_syllable(phrase):
        return syllable(kokoro, phrase)
    ph = text_phonemes(phrase, pinyin_of.get(phrase) or PINYIN_FIX.get(phrase))
    n = len(HAN.findall(phrase))
    speed = 0.82 if n <= 2 else SPEED   # single words a little slower
    x, dur = kokoro.run(ph, speed)
    return speech_only(fix_final_tones(x, ph, dur), ph, dur)


# ---------------------------------------------------------------- loudness and MP3
LOUDNESS_DB = -8      # loudness of the spoken parts before limiting (RMS, dBFS); phones play quietly, so this is loud
CEILING = 0.94        # peak limit
MAX_BOOST_DB = 12


def _window_min(g, n):
    pad = np.concatenate([np.full(n, g[0]), g, np.full(n, g[-1])])
    return np.lib.stride_tricks.sliding_window_view(pad, 2 * n + 1).min(axis=1)


def _smooth(g, n):
    k = n // 2
    pad = np.concatenate([np.full(k, g[0]), g, np.full(k, g[-1])])
    c = np.concatenate([[0.0], np.cumsum(pad, dtype=np.float64)])
    return ((c[2 * k + 1:] - c[:-2 * k - 1]) / (2 * k + 1)).astype(np.float32)


def level(x):
    """Bring the spoken parts to LOUDNESS_DB, then limit peaks to CEILING (no clipping)."""
    x = np.asarray(x, np.float32)
    f = max(1, int(RATE * 0.05))
    rms = np.array([np.sqrt(np.mean(x[i:i + f] ** 2)) for i in range(0, max(1, len(x) - f), f)])
    if not len(rms) or rms.max() == 0:
        return x
    active = rms[rms > 0.1 * rms.max()]
    gain = min(10 ** ((LOUDNESS_DB - 20 * np.log10(np.sqrt(np.mean(active ** 2)))) / 20), 10 ** (MAX_BOOST_DB / 20))
    y = x * gain
    need = np.minimum(1.0, CEILING / np.maximum(np.abs(y), 1e-9)).astype(np.float32)
    n = max(1, int(RATE * 0.006))
    need = np.minimum(need, _smooth(_window_min(need, n), n))
    return np.clip(y * need, -CEILING, CEILING)


def to_mp3(pcm):
    x = np.asarray(pcm, dtype=np.float32)
    peak = np.abs(x).max() or 1.0
    loud = np.where(np.abs(x) > 0.01 * peak)[0]
    if len(loud):
        pad = int(0.07 * RATE)
        x = x[max(0, loud[0] - pad): loud[-1] + pad]
    x = level(x)
    for _ in range(4):
        mp3 = _lame(x)
        peak = _decoded_peak(mp3)
        if peak is None or peak <= 0.995:
            break
        x = x * (0.985 / peak)
    return mp3


def _lame(x):
    x = np.clip(np.asarray(x, np.float32) * 32767, -32767, 32767).astype(np.int16)
    enc = lameenc.Encoder()
    enc.set_bit_rate(48)
    enc.set_in_sample_rate(RATE)
    enc.set_channels(1)
    enc.set_quality(2)
    return enc.encode(x.tobytes()) + enc.flush()


def _decoded_peak(mp3):
    """Peak of the decoded MP3 (the encoder can overshoot), or None without PyAV."""
    try:
        import av, io
        with av.open(io.BytesIO(mp3), format='mp3') as c:
            x = np.concatenate([fr.to_ndarray().astype(np.float32).reshape(-1) for fr in c.decode(audio=0)])
        return float(np.abs(x).max() / (32768 if np.abs(x).max() > 2 else 1))
    except ImportError:
        return None


def clip_name(mp3):
    return hashlib.sha1(mp3).hexdigest()[:12] + '.mp3'


def old_manifest():
    path = os.path.join(AUDIO, 'manifest.js')
    if not os.path.exists(path):
        return {}
    return json.loads(open(path, encoding='utf-8').read().split('=', 1)[1].strip().rstrip(';'))


def write_manifest(manifest):
    # remove clips no longer used (only voice clips, which are named by their hash; music.mp3 stays)
    keep = set(manifest.values())
    for f in os.listdir(AUDIO):
        if re.fullmatch(r'[0-9a-f]{12}\.mp3', f) and f not in keep:
            os.remove(os.path.join(AUDIO, f))
    with open(os.path.join(AUDIO, 'manifest.js'), 'w', encoding='utf-8') as f:
        f.write('// Generated by tools/build_audio.py: phrase -> recorded clip\n')
        f.write('window.ZH_CLIPS = ' + json.dumps(manifest, ensure_ascii=False, indent=0) + ';\n')
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import stamp
    stamp.main()


def voice_range(kokoro):
    """Tone levels 1 and 5 from the voice's own pitch in an ordinary sentence."""
    import parselmouth
    a, _ = kokoro.run(text_phonemes('小朋友，你好！我们一起来读书吧。'), SPEED)
    f = parselmouth.Sound(a.astype(np.float64), RATE).to_pitch(pitch_floor=90, pitch_ceiling=600).selected_array['frequency']
    med = float(np.median(f[f > 0]))
    return med * 0.74, med * 1.38


def main(folder, redo=(), everything=False, show=False):
    global LOW, HIGH
    data = json.load(open(os.path.join(ROOT, 'tools', 'phrases.json'), encoding='utf-8'))
    phrases, pinyin_of = data['phrases'], data['pinyin']
    if show:
        for p in phrases:
            if not is_syllable(p):
                print(p, '|', phonemes_to_pinyin(text_phonemes(p, pinyin_of.get(p) or PINYIN_FIX.get(p))))
        return
    kokoro = Kokoro(folder)
    LOW, HIGH = voice_range(kokoro)
    print(f'voice {VOICE}: tones between {LOW:.0f} and {HIGH:.0f} Hz')
    os.makedirs(AUDIO, exist_ok=True)
    old = {} if everything else old_manifest()
    manifest, made = {}, 0
    for k, p in enumerate(phrases):
        if p in old and p not in redo and os.path.exists(os.path.join(AUDIO, old[p])):
            manifest[p] = old[p]
            continue
        mp3 = to_mp3(phrase_audio(kokoro, p, pinyin_of))
        manifest[p] = clip_name(mp3)
        with open(os.path.join(AUDIO, manifest[p]), 'wb') as f:
            f.write(mp3)
        made += 1
        if made % 100 == 0:
            print(f'  {k + 1}/{len(phrases)}', flush=True)
    write_manifest(manifest)
    print(f'{len(phrases)} phrases, {made} new clips')


if __name__ == '__main__':
    args = sys.argv[1:]
    redo = set(args[args.index('--redo') + 1:]) if '--redo' in args else set()
    args = args[:args.index('--redo')] if '--redo' in args else args
    everything = '--all' in args
    show = '--show' in args
    args = [a for a in args if a not in ('--all', '--show')]
    if not args and not show:
        sys.exit(__doc__)
    main(args[0] if args else None, redo, everything, show)
