# A Thread owns the Voice, not a Run

A Voice — the musical identity of one agent, and the Register it plays in — is
keyed on `threadId`, not `runId`. Runs are the obvious unit and the wrong one:
human-in-the-loop approval ends a Run and resumes on a new `runId` within the
same thread, so run-keyed Registers would relocate an agent's pitch range every
time a developer approved a tool call. The listener would hear an agent leave and
a new one arrive when nothing happened but a yes.

## Consequences

A Thread has no defined end, so Voices have to be reaped. A Voice stays Audible
while its Thread has an open Run, while its last Run ended in an unanswered
Interrupt, and for a short linger after ordinary completion; Registers are
reclaimed least-recently-audible once exhausted. None of that would be necessary
under run-keying — it is the price of an agent sounding like itself across turns.
