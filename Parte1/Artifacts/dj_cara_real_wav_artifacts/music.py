import wave
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# Load the WAV
w = wave.open('dj_cara_real.wav', 'rb')
n, sr = w.getnframes(), w.getframerate()
raw = w.readframes(n)
data = np.frombuffer(raw, dtype=np.int16).reshape(-1, 2)

left  = data[:, 0].astype(np.float64)
right = data[:, 1].astype(np.float64)
diff  = (left + right) / 2              # the "side" channel — this is where it lives

# Take whatever time window you want to inspect (here: first 20s)
interval = 0
for i in range(math.ceil((11*60 + 12)/48)):
    seg = diff[interval:interval + sr * 48]
    interval += sr * 47

    fig = plt.figure(figsize=(30, 5))
    ax = plt.Axes(fig, [0, 0, 1, 1])
    ax.set_axis_off()
    fig.add_axes(ax)

    ax.specgram(
        seg,
        NFFT=2048,          # frequency resolution
        Fs=sr,
        noverlap=2048 - 64, # hop size = 64 samples -> fine time resolution, needed to resolve character shapes
        cmap='gray'         # grayscale reads more clearly than color maps for text
    )
    ax.set_ylim(18800, 21200)   # crop to the band where the image sits

    plt.savefig(f'hidden_message_mono_{i}.png', dpi=150)