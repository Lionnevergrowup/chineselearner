"""Render the background music loop: audio/music.mp3.

An original, cheerful tune on the pentatonic scale (do re mi sol la), 96 BPM, 16 bars (about 40 s):
a plucked zither-like melody, soft plucked chords, a low bass, a wooden block and a small hand drum.
Everything is synthesized here, so the music has no licence restrictions.
The last bar ends on a rest, so the loop joins without a bump.

Usage: pip install numpy lameenc; python3 tools/make_music.py
"""
import os
import numpy as np
import lameenc

RATE = 32000
BPM = 96
BEAT = 60 / BPM
BAR = 4 * BEAT
BARS = 16
rng = np.random.default_rng(11)

CHORDS = {'C': [60, 64, 67], 'Am': [57, 60, 64], 'F': [57, 60, 65], 'G': [55, 59, 62], 'Dm': [57, 62, 65]}
ROOT = {'C': 48, 'Am': 45, 'F': 41, 'G': 43, 'Dm': 50}
FIFTH = {'C': 43, 'Am': 52, 'F': 48, 'G': 50, 'Dm': 45}
PROGRESSION = ['C', 'C', 'Am', 'Am', 'C', 'F', 'G', 'C',
               'C', 'Am', 'F', 'C', 'Am', 'G', ('Dm', 'G'), 'C']

# melody on the pentatonic scale: (beat, length in beats, midi note)
A4, C5, D5, E5, G5, A5, C6 = 69, 72, 74, 76, 79, 81, 84
MELODY_BARS = [
    [(0, 1, E5), (1, 1, G5), (2, 1.5, A5), (3.5, .5, G5)],
    [(0, 1, E5), (1, 1, D5), (2, 2, C5)],
    [(0, 1, D5), (1, 1, E5), (2, 1, G5), (3, 1, E5)],
    [(0, 1, D5), (1, 1, C5), (2, 2, A4)],
    [(0, .5, C5), (.5, .5, D5), (1, 1, E5), (2, 1, G5), (3, 1, A5)],
    [(0, 1.5, C6), (1.5, .5, A5), (2, 2, G5)],
    [(0, 1, A5), (1, 1, G5), (2, 1, E5), (3, 1, D5)],
    [(0, 3, E5)],
    [(0, 1, G5), (1, 1, A5), (2, 1, C6), (3, 1, A5)],
    [(0, 1, G5), (1, 1, E5), (2, 2, D5)],
    [(0, .5, E5), (.5, .5, G5), (1, 1, A5), (2, 1, G5), (3, 1, E5)],
    [(0, 1, D5), (1, 1, E5), (2, 2, C5)],
    [(0, 1, A4), (1, 1, C5), (2, 1, D5), (3, 1, E5)],
    [(0, 1.5, G5), (1.5, .5, E5), (2, 2, D5)],
    [(0, 1, E5), (1, 1, D5), (2, 1, C5), (3, 1, D5)],
    [(0, 3, C5)],          # beat 4 rests, so the loop can restart
]

hz = lambda m: 440.0 * 2 ** ((m - 69) / 12)


def pluck(f, dur, bright=0.5, decay=0.996):
    """Karplus-Strong string."""
    n = int((dur + 0.6) * RATE)
    period = max(2, int(RATE / f))
    buf = rng.uniform(-1, 1, period)
    buf = np.convolve(buf, [bright, 1 - bright], mode='same')  # soften the first burst
    out = np.empty(n)
    for i in range(n):
        out[i] = buf[i % period]
        buf[i % period] = decay * 0.5 * (buf[i % period] + buf[(i + 1) % period])
    return out * (1 - np.exp(-np.arange(n) / RATE * 300))


def zither(f, dur):
    """A bright pluck with a little vibrato at the end of long notes, like a guzheng."""
    s = pluck(f, dur, bright=0.75, decay=0.9975)
    t = np.arange(len(s)) / RATE
    if dur > BEAT * 1.2:   # gentle pitch wobble by resampling the tail
        wob = 1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - 0.25) * 3, 0, 1)
        idx = np.clip(np.cumsum(wob) - wob[0], 0, len(s) - 1)
        s = np.interp(idx, np.arange(len(s)), s)
    return s * np.exp(-t * 1.2)


def woodblock(f=1100, dur=0.08):
    t = np.arange(int(dur * RATE)) / RATE
    return (np.sin(2 * np.pi * f * t) + 0.4 * np.sin(2 * np.pi * 2.7 * f * t)) * np.exp(-t * 60)


def drum(dur=0.25):
    t = np.arange(int(dur * RATE)) / RATE
    f = 120 * np.exp(-t * 8) + 60
    return np.sin(2 * np.pi * np.cumsum(f) / RATE) * np.exp(-t * 14)


def add(track, at, sound, gain):
    i = int(at * RATE)
    j = min(len(track), i + len(sound))
    track[i:j] += gain * sound[:j - i]


def render():
    total = int((BARS * BAR + 2.0) * RATE)     # 2 s of room for the reverb tail
    mel, chords, bass, perc = (np.zeros(total) for _ in range(4))
    for b, prog in enumerate(PROGRESSION):
        start = b * BAR
        halves = prog if isinstance(prog, tuple) else (prog, prog)
        for half, name in enumerate(halves):
            beat0 = half * 2
            # broken chord on the off-beat
            if not (b == BARS - 1 and half == 1):
                for k, m in enumerate(CHORDS[name]):
                    add(chords, start + (beat0 + 1) * BEAT + k * 0.06, pluck(hz(m), BEAT * 1.2, bright=0.3, decay=0.994), 0.45)
            # bass: root, then fifth
            if not (b == BARS - 1 and half == 1):
                add(bass, start + beat0 * BEAT, pluck(hz(ROOT[name]), BEAT * 1.6, bright=0.2, decay=0.998), 0.9)
            if half == 0 and not isinstance(prog, tuple) and b != BARS - 1:
                add(bass, start + 2 * BEAT, pluck(hz(FIFTH[name]), BEAT * 1.4, bright=0.2, decay=0.998), 0.7)
        # hand drum on beat 1, wooden block on beats 2 and 4 (and a soft one on the last eighth)
        add(perc, start, drum(), 0.55)
        for beat, g in ((1, 0.16), (3, 0.16), (3.5, 0.08)):
            if b == BARS - 1 and beat >= 3:
                continue
            add(perc, start + beat * BEAT, woodblock(), g)
        for beat, length, note in MELODY_BARS[b]:
            add(mel, start + beat * BEAT, zither(hz(note), length * BEAT), 0.6 * (0.92 + 0.16 * rng.random()))
    dry = mel + 0.4 * chords + 0.55 * bass + perc
    # small room reverb (convolution with a decaying noise burst)
    t = np.arange(int(1.3 * RATE)) / RATE
    ir = rng.uniform(-1, 1, len(t)) * np.exp(-t * 4.0)
    ir = np.convolve(ir, np.ones(6) / 6, mode='same')   # darker tail
    ir /= np.sqrt(np.sum(ir ** 2))
    n = len(dry) + len(ir)
    wet = np.fft.irfft(np.fft.rfft(dry, n) * np.fft.rfft(ir, n), n)[:len(dry)]
    mix = dry + 0.18 * wet
    # fold the tail back onto the start so the loop is seamless, then cut to exactly 16 bars
    loop_len = int(BARS * BAR * RATE)
    loop = mix[:loop_len].copy()
    tail = mix[loop_len:]
    loop[:len(tail)] += tail
    loop = np.tanh(loop / np.abs(loop).max() * 1.2) / np.tanh(1.2)   # gentle limiter
    return (loop * 0.9 * 32767).astype(np.int16)


def main():
    pcm = render()
    enc = lameenc.Encoder()
    enc.set_bit_rate(64)
    enc.set_in_sample_rate(RATE)
    enc.set_channels(1)
    enc.set_quality(2)
    mp3 = enc.encode(pcm.tobytes()) + enc.flush()
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'audio', 'music.mp3')
    with open(out, 'wb') as f:
        f.write(mp3)
    print(f'{out}: {len(pcm) / RATE:.1f} s, {len(mp3) // 1024} KB')
    import stamp
    stamp.main()


if __name__ == '__main__':
    main()
