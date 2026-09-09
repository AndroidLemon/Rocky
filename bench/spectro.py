"""Render a probe WAV as an annotated spectrogram so the output can be checked
visually against the timestamps it's supposed to align with.

Usage: python spectro.py notes|phases|sustain|<schedule.json> <wav> <png>

Passing a probe's schedule JSON (probe_chords.json, probe_melody.json) draws
sections and pitch reference lines straight from what the probe actually
scheduled, so this can't go stale against those probes.
"""

import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import soundfile as sf

GAP = 1.0


def layout(kind):
    """Returns [(label, start_s, dur_s)]."""
    if kind.endswith(".json"):
        events = json.load(open(kind))["events"]
        return [(e["label"], e["start"], e["dur"]) for e in events]
    if kind == "notes":
        spans = [("60", 5), ("60+64", 5), ("60+64+67", 5), ("60", 5)]  #

    elif kind == "phases":
        spans = [("reasoning", 8), ("tool", 8), ("needs-you", 8), ("error", 8)]
    elif kind == "sustain":
        spans = [("minimal/off", 6), ("minimal/masked", 6),
                 ("loud/off", 6), ("loud/masked", 6)]
    else:
        return None
    out, t = [], 0.0
    for label, dur in spans:
        out.append((label, t, dur))
        t += dur + GAP
    return out


def main():
    kind, wav_path, png_path = sys.argv[1], sys.argv[2], sys.argv[3]
    audio, sr = sf.read(wav_path)
    mono = audio.mean(axis=1) if audio.ndim > 1 else audio

    fig, ax = plt.subplots(figsize=(16, 6))
    # 4096 window: ~12Hz resolution, enough to resolve individual MIDI pitches
    spec, freqs, times, _ = ax.specgram(
        mono, NFFT=4096, Fs=sr, noverlap=3072, cmap="magma",
        vmin=-140, vmax=-40, scale="dB",
    )
    ax.set_ylim(0, 4000)
    ax.set_ylabel("Hz")
    ax.set_xlabel("seconds")
    ax.set_title(png_path)

    from_json = kind.endswith(".json")
    sections = layout(kind)
    if sections:
        for i, (label, start, dur) in enumerate(sections):
            ax.axvline(start, color="cyan", lw=1.2, alpha=0.9)
            ax.axvline(start + dur, color="cyan", lw=0.6, ls=":", alpha=0.6)
            # json schedules can have dense per-note events: short labels,
            # alternating height so they stay readable
            short = label.split(":")[-1] if from_json else label
            ax.text(start + 0.15, 3750 if i % 2 == 0 else 3400, short,
                    color="cyan", fontsize=8 if from_json else 11,
                    va="top", fontweight="bold")

    # Reference lines for the scheduled pitches.
    if from_json:
        pitch_refs = [(p, f"{p} {440.0 * 2 ** ((p - 69) / 12):.0f}Hz")
                      for p in sorted({p for e in json.load(open(kind))["events"]
                                       for p in e["pitches"]})]
    elif kind == "notes":
        pitch_refs = [(60, "C4 261Hz"), (64, "E4 330Hz"), (67, "G4 392Hz")]
    else:
        pitch_refs = []
    for midi, name in pitch_refs:
        hz = 440.0 * 2 ** ((midi - 69) / 12)
        ax.axhline(hz, color="lime", lw=0.8, ls="--", alpha=0.7)
        ax.text(0.1, hz + 40, name, color="lime", fontsize=9)

    fig.tight_layout()
    fig.savefig(png_path, dpi=110)
    print(f"wrote {png_path}")

    # Per-section energy, so silence is caught numerically too.
    if sections:
        for label, start, dur in sections:
            skip = min(0.5, dur / 4)  # short per-note events can't skip 0.5s
            seg = mono[int((start + skip) * sr):int((start + dur) * sr)]
            print(f"  {label:<10} rms {np.sqrt((seg**2).mean()):.4f}")


if __name__ == "__main__":
    main()
