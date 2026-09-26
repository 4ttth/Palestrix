"""Synthesizes soundtrack.wav for the PalestrIX film, cue-locked to index.html.

    python soundtrack.py          # → soundtrack.wav (60 s, 48 kHz, stereo)

Everything is generated from numpy: a slow additive pad, a soft pulse under
the product chapters, and small tuned cues on the on-screen events (log
lines, Palestras awards, flag solves, sandbox detections). The cue times are
copied from the timeline in index.html; move one there, move it here.
"""

import wave

import numpy as np

SR = 48_000
DUR = 60.0
N = int(SR * DUR)
t = np.arange(N) / SR
rng = np.random.default_rng(11)

L = np.zeros(N)
R = np.zeros(N)


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def env(start, attack, hold, release, length=None):
    """Linear-attack, exponential-release envelope over the whole timeline."""
    e = np.zeros(N)
    a0, a1 = int(start * SR), int((start + attack) * SR)
    h1 = int((start + attack + hold) * SR)
    end = min(N, int((start + attack + hold + release * 6) * SR))
    if a1 > a0:
        e[a0:a1] = np.linspace(0, 1, a1 - a0)
    e[a1:h1] = 1
    if end > h1:
        k = np.arange(end - h1) / SR
        e[h1:end] = np.exp(-k / release)
    return e


def add(sig, pan=0.0, gain=1.0):
    global L, R
    L += sig * gain * np.cos((pan + 1) * np.pi / 4)
    R += sig * gain * np.sin((pan + 1) * np.pi / 4)


# ---- pad: four chords, additive voices with slow detune and breathing ----
CHORDS = [  # start, midi notes
    (0.0, [50, 57, 62, 66, 69, 76]),      # Dmaj9
    (8.0, [47, 54, 62, 66, 69, 73]),      # Bm11
    (19.0, [43, 55, 59, 62, 66, 73]),     # Gmaj7#11
    (26.4, [45, 52, 61, 64, 69, 76]),     # A6/9
    (34.0, [47, 54, 62, 65, 69, 74]),     # Bm(add b6) — the sandbox darkens
    (41.0, [43, 55, 59, 62, 66, 71]),     # Gmaj7
    (47.1, [45, 57, 61, 64, 69, 76]),     # A
    (52.3, [50, 57, 62, 66, 69, 78]),     # Dmaj9, brighter voicing
    (56.0, [38, 50, 57, 62, 66, 69, 76]), # Dmaj9 with low root — resolve
]
XF = 1.6
for i, (start, notes) in enumerate(CHORDS):
    end = CHORDS[i + 1][0] if i + 1 < len(CHORDS) else DUR
    w = np.clip((t - (start - XF / 2)) / XF, 0, 1) * np.clip(((end + XF / 2) - t) / XF, 0, 1)
    if i == 0:
        w *= np.clip((t - 0.6) / 3.0, 0, 1)
    for j, m in enumerate(notes):
        f = hz(m)
        for d, p in ((-0.09, -0.6), (0.09, 0.6)):
            ph = rng.uniform(0, 2 * np.pi)
            lfo = 0.75 + 0.25 * np.sin(2 * np.pi * (0.07 + 0.013 * j) * t + ph)
            v = np.sin(2 * np.pi * (f + d) * t + ph) + 0.18 * np.sin(2 * np.pi * 2 * (f + d) * t)
            add(v * w * lfo, pan=p * (0.3 + 0.1 * j), gain=0.020 / (1 + 0.15 * j))

# air: filtered noise swell that follows the pad
air = np.convolve(rng.standard_normal(N), np.ones(24) / 24, mode="same")
add(air * np.clip(t / 6, 0, 1) * 0.012, pan=-0.3)
add(np.roll(air, 4000) * np.clip(t / 6, 0, 1) * 0.012, pan=0.3)

# ---- pulse: a soft kick and sub under the product chapters ----
BPM = 100
beat = 60 / BPM
pulse_on = lambda s: 8.2 <= s < 52.0 and not (33.7 <= s < 34.6)  # noqa: E731
k_len = int(0.45 * SR)
kt = np.arange(k_len) / SR
kick = np.sin(2 * np.pi * (42 * kt + (95 - 42) * (1 - np.exp(-kt * 28)) / 28)) * np.exp(-kt * 9)
s = 8.2
while s < DUR:
    if pulse_on(s):
        i0 = int(s * SR)
        g = 0.13 * min(1.0, (s - 8.2) / 3 + 0.35)
        seg = kick[: max(0, min(k_len, N - i0))]
        add(np.pad(seg, (i0, N - i0 - len(seg))), gain=g)
    s += beat

# hat-like tick on the offbeat through the arena, for drive
s = 26.4 + beat / 2
while s < 33.6:
    i0 = int(s * SR)
    n = int(0.05 * SR)
    hh = np.diff(rng.standard_normal(n + 1)) * np.exp(-np.arange(n) / SR * 90)
    add(np.pad(hh, (i0, N - i0 - n)), pan=0.35, gain=0.018)
    s += beat


# ---- cues ----
def bell(at, midi, gain=0.08, decay=0.7, pan=0.0):
    f = hz(midi)
    e = env(at, 0.004, 0.0, decay)
    v = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-np.clip(t - at, 0, None) * 6)
    add(v * e, pan=pan, gain=gain)


def tick(at, gain=0.05, pan=0.0, f=3200):
    e = env(at, 0.001, 0.0, 0.018)
    add(np.sin(2 * np.pi * f * t) * e, pan=pan, gain=gain)


def boom(at, gain=0.5):
    e = env(at, 0.01, 0.05, 0.9)
    sweep = np.sin(2 * np.pi * (38 * (t - at) + 60 * (1 - np.exp(-np.clip(t - at, 0, None) * 12)) / 12))
    add(sweep * e, gain=gain)


def swell(at, length=1.2, gain=0.08):
    """Reverse-noise rise that lands on `at`."""
    start = at - length
    k = np.clip((t - start) / length, 0, 1) ** 3 * (t < at)
    sm = np.convolve(rng.standard_normal(N), np.ones(8) / 8, mode="same")
    add(sm * k, pan=-0.2, gain=gain)
    add(np.roll(sm, 777) * k, pan=0.2, gain=gain)


# wordmark lands
swell(5.15, 1.4, 0.10)
boom(5.15, 0.55)
bell(5.15, 81, 0.05, 2.5)
bell(5.17, 88, 0.03, 2.5, pan=0.4)

# lab log lines, healthcheck, and the reaper
for i, at in enumerate([9.35, 9.85, 10.35, 10.85, 11.35, 11.85]):
    tick(at, 0.035, pan=0.5, f=2600 + 120 * i)
bell(12.45, 78, 0.05, 0.6, pan=0.3)
bell(12.95, 81, 0.06, 0.9, pan=0.3)
for s_ in np.arange(14.3, 17.2, 0.12):  # fast-forwarded clock
    tick(float(s_), 0.012 + 0.02 * (s_ - 14.3) / 3, pan=0.6, f=2200)
boom(17.25, 0.3)
bell(17.25, 62, 0.05, 1.2)

# palestras awards: rising arpeggio
for at, m in [(20.1, 76), (21.0, 79), (21.8, 83), (22.55, 88)]:
    bell(at, m, 0.08, 0.9, pan=-0.2)
    bell(at + 0.05, m + 12, 0.025, 0.6, pan=0.3)

# arena: solves blip, first blood rings
for at in [27.9, 28.3, 28.65, 29.8, 30.2, 30.6, 31.0, 31.35, 31.7]:
    bell(at, 86, 0.03, 0.25, pan=0.4)
bell(29.2, 81, 0.07, 1.4)
bell(29.22, 88, 0.05, 1.4, pan=-0.4)
bell(29.3, 69, 0.04, 1.0)
tick(29.3, 0.03)

# sandbox: low detections, then the verdict
for at, m in [(36.0, 57), (36.9, 58), (37.8, 60), (38.7, 61)]:
    bell(at, m, 0.07, 0.8, pan=0.3)
boom(39.45, 0.25)
bell(39.45, 50, 0.07, 1.6)

# tenancy: walls draw, the packet is refused
for i in range(8):
    tick(42.5 + i * 0.09, 0.02, pan=-0.6 + i * 0.17, f=4200)
boom(44.35, 0.22)
tick(44.35, 0.06, f=1200)

# academy modules fill
for i in range(10):
    tick(48.8 + i * 0.07, 0.015, pan=-0.3 + 0.06 * i, f=3600)

# end card
swell(56.75, 1.6, 0.11)
boom(56.75, 0.6)
bell(56.75, 74, 0.05, 3.0)
bell(56.77, 81, 0.04, 3.0, pan=0.4)
bell(56.79, 86, 0.025, 3.0, pan=-0.4)


# ---- reverb: stereo exponential-noise convolution ----
def reverb(x, seconds=2.6, seed=0):
    n = int(seconds * SR)
    r = np.random.default_rng(seed)
    ir = r.standard_normal(n) * np.exp(-np.arange(n) / SR * (6.9 / seconds))
    ir = np.convolve(ir, np.ones(6) / 6, mode="same")  # darken
    ir /= np.sqrt(np.sum(ir**2))
    size = 1 << int(np.ceil(np.log2(len(x) + n)))
    y = np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[: len(x)]
    return y


L = 0.78 * L + 0.32 * reverb(L, seed=1)
R = 0.78 * R + 0.32 * reverb(R, seed=2)

# master: fade in/out, soft clip, normalize to -1 dBFS
fade = np.clip(t / 0.4, 0, 1) * np.clip((DUR - t) / 1.4, 0, 1)
L *= fade
R *= fade
L, R = np.tanh(L * 1.6) / 1.6, np.tanh(R * 1.6) / 1.6
peak = max(np.abs(L).max(), np.abs(R).max())
g = 10 ** (-1 / 20) / peak
pcm = (np.stack([L, R], axis=1) * g * 32767).astype("<i2")

with wave.open("soundtrack.wav", "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("wrote soundtrack.wav", pcm.shape)
