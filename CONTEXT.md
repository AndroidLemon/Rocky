# Rocky

Rocky sonifies live agent activity. It sits transparently in front of an AG-UI
endpoint, listens to the event stream, and generates continuous music that tells
a developer what their agents are doing without them reading a log.

## Language

### Agent identity

**Thread**:
One continuous agent conversation, durable across many turns. This is what a
developer means when they say "my agent".
_Avoid_: agent, session, conversation

**Run**:
A single turn of a Thread, opened by `RUN_STARTED` and closed by `RUN_FINISHED`
or `RUN_ERROR`. A Thread accumulates many Runs; approving an Interrupt ends one
Run and begins another.
_Avoid_: request, invocation, turn, execution

**Voice**:
The musical identity of one Thread. A Voice owns a Register for as long as it is
Audible, so a Thread sounds like itself across every Run it contains.
_Avoid_: channel, track, agent slot

**Audible**:
The condition of a Voice being heard and holding its Register: its Thread has an
open Run, or its last Run ended in an unanswered Interrupt, or it is still within
the linger period after ending. A Voice that is not Audible surrenders its
Register to the next Thread that needs one.
_Avoid_: active, live, playing, alive

### How Rocky hears

**Adapter**:
Whatever turns one harness's native signals into AG-UI events for Rocky. The
Claude Code plugin is one; it forwards hook payloads and Rocky translates them.
Any harness that can POST AG-UI events needs no Adapter at all.
_Avoid_: integration, connector, bridge, proxy

### What Rocky hears

**Phase**:
What an agent is doing right now, expressed as sound. Never the agent's own
application data — AG-UI's `STATE_SNAPSHOT` and `STATE_DELTA` carry that, and
Rocky ignores it.
_Avoid_: state, status, mode

**Ensemble Phase**:
The single Phase the music expresses at any moment, reduced by priority across
every audible Voice. Only one can sound at a time.
_Avoid_: global state, master phase, overall status

**Stall**:
An open Run that has emitted nothing for longer than the stall threshold.
Inferred by Rocky; no AG-UI event announces it.
_Avoid_: hang, timeout, silence, idle

**Interrupt**:
A Run that ended because the agent needs a human decision. Distinguished from
ordinary completion only by its outcome, and it means the opposite: work is
paused, not finished.
_Avoid_: pause, block, approval, HITL

**Capture**:
A recorded event stream, replayable at its original timing. Rocky's music is
tuned against Captures, never against live agents.
_Avoid_: fixture, recording, trace, log

### What Rocky plays

**Register**:
The pitch range allocated to one Voice. Two Voices in different Registers sound
simultaneously and remain separable to a listener.
_Avoid_: octave, band, channel

**Home**:
The fixed tonic (C, in v1). Every Run arrives at Home and every Interrupt
leaves it, so resolution back to Home is what "the human answered" sounds like.
_Avoid_: key, root, tonic, center

**Drone**:
The root pedal that sounds whenever a Run is open and nothing else is. It means
"a Run is open"; its absence means silence between Runs.
_Avoid_: pad, bed, hum, idle tone

**Chord**:
The pitch set held for one tool call in flight, from `TOOL_CALL_START` until
its result (never shorter than the minimum hold). Its quality is chosen by the
tool's category (shell, read, mutate, network, agent), so a listener can tell
what kind of work is happening. Concurrent calls union their Chords.
_Avoid_: note, hit, blip, voicing, trigger

**Gesture**:
Any musical response to one event: Arrival (`RUN_STARTED`), Chord, Arpeggio
(`TEXT_MESSAGE_START`), Interrupt, Error, Release (`RUN_FINISHED`). The grammar
is the table of Gestures in `rocky/harmony.py`.
_Avoid_: cue, sound, effect, sfx, motif

**Style Prompt**:
One of the text descriptions whose embedding contributes to the music's overall
character. A fixed set, encoded once; only their weights change while running.
_Avoid_: prompt, preset, vibe, patch

**Blend Weights**:
The normalized weighting across Style Prompts that produces the current sound.
Blending interpolates between Style Prompts — it does not layer them.
_Avoid_: mix, levels, faders
