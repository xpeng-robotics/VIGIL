[Documentation](../README.md) / [Review archive](README.md)

# Model-visible frame identifiers

## Finding and correction — 2026-11-05

The earlier observation formatter used `<episode_id>:step_<n>` as the model-visible
frame label. Dataset IDs contain task-authoring information. In the corrected
125-task state-verification selection, every ID contains an explicit state token
that agrees with its configured initial expected state. For example, an ID can
contain `microwave_closed` while the instruction asks whether it is open or closed.
The ID therefore provides an answer cue outside the RGB observation.

The formatter now emits only `step_<n>`, independent of the episode ID or a custom
metadata frame label. These labels remain stable within an episode and distinguish
the current frame from earlier steps. Internal trace IDs and dataset filenames
remain available to the evaluator and replay tools.

Regression checks cover all four state words, metadata overrides, the actual
model request, correction retries and retained conversation history.

## Consequences for existing results

The completed revised-pack Qwen3.6-27B run (W 42.4%, B 36.0%) used the earlier
formatter. Its 1,000 saved trajectories and 14,714 steps still pass settlement,
per-episode-score and aggregate consistency checks. Those checks do not establish
that model observations were free of answer cues. The repair does not rescore or
replace historical trajectories, and its effect on model performance is unmeasured.

New experiments must use a fresh output directory; the runtime fingerprint changes
and prevents resuming a pre-fix run under the repaired formatter. A new full model
run is required before attributing performance to this corrected observation contract.

A separate audit of the 20 original primary paper archives inspected all 244,480
recorded steps. Every saved `agent_diagnostics.prompt_surface.frame_ids` entry
contained only labels of the form `obs_<n>`, without dataset episode IDs. This
checks the archived frame-label diagnostics, not complete outgoing requests or
every possible input channel. It does not establish the frame-label format of
other historical campaigns. Historical W/B agreement from a trace scorer alone
is not an audit of the model input channel.
