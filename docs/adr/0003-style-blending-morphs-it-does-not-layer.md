# Per-agent identity lives in Registers, not Style Prompts

The obvious way to make several agents sound like a band is to give each one its
own Style Prompt and blend them. Magenta RealTime 2 will not do that. Blending is
a weight-normalized mean of 768-dimensional MusicCoCa embeddings, quantized
afterward to 12 RVQ tokens (`core/src/mlx_engine.cpp`, `reblend_musiccoca_tokens`)
— an interpolation, not a mix. Blending "jazz trio" with "industrial techno" at
even weights yields one hybrid texture that is neither, never a bassist playing
over a beat.

Per-agent identity therefore lives in the note channel, where Registers give real
simultaneity and separable voices. Style Prompts carry the ensemble's mood only.

## Consequences

Style is a single global value with at most six prompt slots (`kMaxPrompts = 6`),
so it can express the reduced Ensemble Phase but never per-agent character.

Because the blend is quantized after weighting, it moves as a step function:
small weight changes can produce identical tokens and no audible change, then
several flip at once. Magenta's own Collider example throttles weight updates to
10 Hz to avoid re-invoking the quantizer needlessly. Smooth crossfading is not
what this channel does — do not design around it.
