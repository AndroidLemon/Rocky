"""Schedule-driven pitch verdicts: did each scheduled note actually sound?

Time-resolved successor to measure_pitch.py. Reads the schedule JSON the probe
wrote next to its WAV, so this analyzer cannot go stale the way
analyze_phases.py did. For every (section, pitch) it compares band energy
inside that pitch's scheduled windows against windows where the pitch was not
scheduled (excluding any window overlapping a scheduled occurrence). If the
bands don't track the schedule, the event grammar has no renderer.

Usage: python measure_timeline.py <wav> <schedule.json>
"""

import json
import sys

import numpy as np
import soundfile as sf


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def band_energy(mono, sr, start, dur, f0, width=0.025):
    # width tightened vs measure_pitch so adjacent semitones (the cluster
    # chord) stay in separate bands
    skip = min(1.0, 0.25 * dur)
    seg = mono[int((start + skip) * sr):int((start + dur) * sr)]
    spec = np.abs(np.fft.rfft(seg))
    freqs = np.fft.rfftfreq(len(seg), 1 / sr)
    m = (freqs > f0 * (1 - width)) & (freqs < f0 * (1 + width))
    return float(spec[m].sum() / max(spec.sum(), 1e-9))


def main():
    wav_path, sched_path = sys.argv[1], sys.argv[2]
    audio, sr = sf.read(wav_path)
    mono = audio.mean(axis=1) if audio.ndim > 1 else audio
    events = json.load(open(sched_path))["events"]

    print(f"{wav_path}  ({len(events)} scheduled events)\n")
    for e in events:
        vals = "  ".join(
            f"{p}:{band_energy(mono, sr, e['start'], e['dur'], hz(p)):.4f}"
            for p in e["pitches"])
        print(f"  {e['label']:<14} {e['start']:7.2f}s  {vals}")

    # verdict per (section, pitch): held windows vs clean unheld windows
    groups = {}
    for e in events:
        prefix = e["label"].split(":")[0]
        for p in e["pitches"]:
            groups.setdefault((prefix, p), []).append(e)

    def overlaps_held(e, p):
        for f in events:
            if p in f["pitches"] and \
               e["start"] < f["start"] + f["dur"] and \
               f["start"] < e["start"] + e["dur"]:
                return True
        return False

    print("\nverdict per section+pitch (band tracks its schedule?):")
    failures = 0
    for (prefix, p), evs in sorted(groups.items()):
        on = np.mean([band_energy(mono, sr, e["start"], e["dur"], hz(p))
                      for e in evs])
        off_evs = [e for e in events
                   if p not in e["pitches"] and not overlaps_held(e, p)]
        if not off_evs:
            print(f"  {prefix:<10} {p}: no contrast available")
            continue
        off = np.mean([band_energy(mono, sr, e["start"], e["dur"], hz(p))
                       for e in off_evs])
        ratio = on / max(off, 1e-9)
        verdict = "tracks" if ratio > 1.5 else "DOES NOT TRACK"
        failures += verdict != "tracks"
        print(f"  {prefix:<10} {p} ({hz(p):.0f}Hz): held {on:.4f}"
              f" vs unheld {off:.4f} = {ratio:.2f}x  {verdict}")
    print(f"\n{failures} failing section+pitch pairs")


if __name__ == "__main__":
    main()
