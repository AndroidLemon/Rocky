# Measured sound-design findings

Facts established by probing `mrt2_base` directly, not by reasoning about it.
Several contradict assumptions made while designing, so they are recorded here
rather than rediscovered later.

## Words meaning "less" produce literal silence

Three separate prompt families generated **pure digital silence** (RMS 0.0000):

- `"minimal sustained organ, dry, no drums, no melody"`
- `"almost silence, faint low hum, still"`
- `"clean sustained synthesizer tone, simple, few harmonics, pure"`

This model treats `minimal`, `sparse`, `faint`, `almost silence`, `no melody`,
`simple`, `pure` and `few harmonics` as instructions, not as stylistic colour.

**Rule: every Style Prompt must describe something actively playing.** Contrast
between phases comes from register, brightness and density — never from how
little is happening.

The first two probe sessions were invalidated by this. Two of four phases and
most of the note ladder were inaudible, so the listening feedback gathered from
them was worthless.

## Unused pitches must be masked (`-1`), not off (`0`)

The notes vector takes `-1` masked · `0` off · `1` continuation · `2` onset.
Setting the 127 unused pitches to `0` starves the model:

| unused pitches | onset RMS | RMS after 6 s | sustain ratio |
|---|---|---|---|
| `0` (explicitly off) | 0.077 | 0.011 | 0.15× |
| `-1` (masked) | 0.147 | 0.083 | **0.57×** |

With `0`, a held note decays to nothing within a few seconds — a 30-second tool
call would sound identical to a one-second one, which removes the entire value
of sustaining notes for the duration of work.

**Consequence:** with unused pitches masked, "no notes held" no longer means
silence — the model plays freely. Idle-is-silence must therefore be produced by
gating output gain on the active note count. The MIDI gate is load-bearing, not
a convenience.

## Note conditioning does control pitch

Held pitches show markedly more energy in their fundamental's band than when
released, measured across a 1→2→3→1 ladder:

| pitch | held | released | ratio |
|---|---|---|---|
| 61 (C#4, 277 Hz) | 0.0281 | 0.0096 | 2.92× |
| 82 (A#5, 932 Hz) | 0.0165 | 0.0044 | 3.76× |

The mechanism behind Registers is real.

## Registers must be spaced inharmonically

Adding notes does **not** increase total energy — measured RMS across a ladder
went 0.108 → 0.092 → 0.085 as voices were added. The model redistributes rather
than stacks.

Two pitch layouts fail for separability:

- **Consonant intervals** (C4+E4+G4, a major triad) share partials by
  construction. Three notes were indistinguishable from one.
- **Octave-spaced registers** (C2 / C4 / C6), as originally specified in the
  design, fuse maximally — C4 and C6 are harmonics of C2.

Register spacing should avoid both octaves and simple consonant ratios.

## Phases are spectrally distinct with corrected prompts

| phase | prompt | signature |
|---|---|---|
| reasoning | slow warm cello, low register, smooth sustained bowing | dense low harmonic stack, sustained |
| tool | bright fast marimba, mid register, busy repeating pattern | vertical striations, rhythmic |
| needs-you | loud ringing high bell, insistent, repeating chime | strong bands ~1130 Hz and ~2800 Hz |
| error | harsh distorted low buzz, grinding, unstable | broadband noise, no harmonic structure |

## Chord tones render as real, separate bands

Probing the event-grammar idea (steps/tool calls open chords): every tone of a
held chord shows up in its own fundamental band, measured across
home → dom7 → cluster → home with continuous state (`bench/probe_chords.py`,
verdicts from `bench/measure_timeline.py`):

- The **added seventh** of a dom7 is a real band: 70 (466 Hz) held vs unheld
  = 12.43×. A four-note chord is not a smeared triad.
- **Adjacent semitones resolve separately**: the 60/61/62 cluster tracked at
  12.27× and 5.74×. Dissonant tension chords are renderable.
- Consonance fusion works *for* chords here: the triad fuses into one percept
  (as the register finding predicted), while its quality-defining tones remain
  spectrally present.

Listened 2026-09-09: dom7, major and cluster **do read as distinct chord
qualities** to a human ear, in isolation with a fixed Style Prompt. Not yet
checked under a busy Style Prompt or across key changes.

**Caveat: held chords decay across a continuous run.** Section RMS fell
0.070 → 0.056 → 0.042 → 0.021 over 32 s even with masking (`-1`) and onsets at
each section change. Onsets re-energize the model and pure sustain fades;
long-held harmony will need periodic re-articulation, not a single onset.

## Sequenced melodies land on schedule — faster is better

Scheduled onsets (diminished arpeggio 60/63/66/69) track their time windows at
every rate tested, and adherence *improves* with rate
(`bench/probe_melody.py`):

| rate | held vs unheld, worst pitch | best pitch |
|---|---|---|
| 1 note/s | 2.06× | 4.05× |
| 2 notes/s | 3.12× | 8.51× |
| 4 notes/s | 4.97× | 12.46× |

Frequent onsets are the model's strong suit (consistent with the sustain-decay
caveat above — section RMS also stayed flat ~0.11 across all melody sections
where held chords decayed). Streaming-text melody at 4 notes/s is comfortably
inside the engine's ability; 250 ms is a workable minimum gesture duration.

## A drone survives under a melody — if it shares no harmonics

A Bb2 pedal (46) held under the 2/s melody kept tracking at 5.27× while every
melody note above it also tracked. The redistribute-don't-stack behavior did
not kill the pedal. Drone-under-melody is a usable texture for
streaming-with-context (e.g. reasoning melody over a phase drone).

## Method note

A spectrogram of each probe, checked before playing it to a human, catches
silence and non-separation without spending anyone's attention. Both failures
above were invisible in the code and obvious in the picture. `bench/spectro.py`
renders one with section boundaries annotated.

Two additions from the chord/melody round:

- **Analyzers must read the probe's schedule, not re-declare it.** The new
  probes write a `<name>.json` schedule next to the WAV; `measure_timeline.py`
  and `spectro.py` consume it. (`analyze_phases.py` went stale by hardcoding
  section layout and silently measured the wrong slices.)
- **Choose probe pitches so no note's harmonic lands in another's measurement
  band.** A first melody draft used a Cm7 arpeggio and a C3 drone: C4's 3rd
  harmonic sat exactly on G4's band and the octave-related drone was masked by
  its own upper octave — both produced fake "DOES NOT TRACK" verdicts that
  vanished with a diminished pattern and a harmonically clear drone.
