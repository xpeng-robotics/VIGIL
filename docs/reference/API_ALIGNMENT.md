[Documentation](../README.md) / Reference

# API, image and coordinate alignment

Changing a provider endpoint should preserve the benchmark input. Use the same
prompt policy, dialogue history, generation settings, coordinate mode and RGB
frame. Provider authentication and JSON envelopes differ; model checkpoints and
server-side image processors can still differ even when requests match.

## Choose a public API

| Public backend | System instruction | Current RGB | Output budget |
| --- | --- | --- | --- |
| `openai-compatible`, `openai`, `vllm` | `messages[0]`, role `system` | `image_url`, inline PNG data URL | `max_tokens`, or explicit `max_tokens_field: max_completion_tokens` |
| `gemini` | `systemInstruction.parts` | `inlineData`, `mimeType: image/png` | `generationConfig.maxOutputTokens` |
| `anthropic`, `claude` | top-level `system` | base64 `image.source` | `max_tokens` |

Gemini now retains the system role instead of prepending a user turn. Anthropic
preserves the supplied system text without appending a provider-specific JSON
instruction. Gemini's default key travels in `x-goog-api-key`; custom gateway
header authentication remains available. The API contracts are described in the
[Gemini reference](https://ai.google.dev/api/generate-content) and
[Anthropic reference](https://platform.claude.com/docs/en/api/messages).

For an OpenAI-compatible vision model with normalized coordinates, put this in
`vigil.json`, fill in the endpoint and model, and supply the key through
`VIGIL_API_KEY`:

```json
{
  "backend": "openai-compatible",
  "base_url": "https://your-endpoint.example/v1",
  "model": "your-vision-model",
  "max_tokens": 4096,
  "temperature": 0.2,
  "top_p": 0.9,
  "supports_json_mode": false,
  "coord_mode": "normalized_1000",
  "coord_prompt_mode": "explicit",
  "image_detail": "default",
  "request_max_retries": 2,
  "request_retry_delay_s": 2
}
```

Then use `vigil doctor` and `vigil smoke --out-dir outputs/new-api-smoke`.
For models requiring a completion-token budget, set
`"max_tokens_field": "max_completion_tokens"`. Set `temperature` and `top_p` to
`null` if the reference request omits them; the adapter does not silently remove
unsupported sampling settings after an error. For native Gemini/Anthropic, use
their backend, omit `base_url` to select the official endpoint, and leave
`max_tokens_field` and `image_detail` at their defaults.

`supports_json_mode: false` disables provider format constraints. VIGIL still
requires the same action JSON in the model answer. This is necessary when
matching historical requests that did not request a JSON MIME/response format.
The flag controls OpenAI/Gemini format fields; Anthropic uses the benchmark
prompt without adding a format hint. Native adapters honor a configured
`api_key_header` for gateways as well as their official default key header.
Gemini-specific options belong under `extra_body.generationConfig`, for example
`{"generationConfig":{"thinkingConfig":{"includeThoughts":true}}}`. Other
provider options such as `reasoning_effort` or `chat_template_kwargs` belong in
`extra_body`; reserved benchmark fields cannot be overridden there.

## Action protocol and reasoning history

The model returns one JSON action in message content. For example, using pixel
coordinates:

```json
{"skill_name":"interact_pixel","arguments":{"intent":"pick","x":320,"y":240}}
```

`pick` is an interaction intent, not a top-level skill. `act` is the Python agent
method, not a model action. The public skills are `navigate`, `look`,
`interact_pixel` and `report`. Use `ground` to indicate an object without picking
it up. Existing registered aliases such as `pickup` normalize to `pick`; there
is no `act`-to-`pick` conversion.

The shared rollout runner validates the public skill and required arguments
before calling the environment. Missing `intent`, missing pick coordinates,
incomplete reports and direct simulator calls such as `PickupObject` become
protocol failures. Their attempted actions stay in the trace; no simulator
action is executed. This closes an earlier gap where the validator existed but
was not connected to execution. The trace records
`action_validation_policy: public_registry_v1`.

Provider reasoning fields stay in reviewer evidence and are not replayed in
later assistant messages. The compatible adapter accepts both `reasoning` and
`reasoning_content`. For text-only gateways, complete `<think>`/`<thinking>`
blocks are removed from action parsing, dialogue history and correction requests.
An unfinished or mismatched reasoning block supplies no executable action,
including when the API also supplies an empty or nonempty native reasoning
field. Nested blocks must all close before an answer can be parsed.
Raw responses and retry attempts remain in the trace. A quoted tag inside valid
JSON is preserved, as is the benchmark's optional short `thought` field in the
final JSON. History and correction requests retain only the parsed protocol
fields; unrelated prose and fields do not reenter the next request. Diagnostics
record `assistant_history_policy: canonical_payload_v1`. Empty chat content
remains empty even if a legacy envelope also contains draft `text`.

Prefer a model-compatible server reasoning parser. The
[vLLM reasoning reference](https://docs.vllm.ai/en/stable/features/reasoning_outputs/)
describes channel separation and supported parsers. That separation is not a
general detector of repetitive or semantically collapsed reasoning. Inspect
the saved finish reason, token use and raw response; do not execute a draft
action recovered from reasoning-only output.

## JSON constraints versus native tools

| Mode | Current release behavior |
| --- | --- |
| `supports_json_mode: false` | Ordinary text generation; VIGIL still parses the action JSON |
| `supports_json_mode: true` with a compatible API | Requests `response_format: {"type":"json_object"}`; does not constrain the action schema |
| Strict JSON Schema | Proposed separate experiment; no dedicated public configuration mode yet |
| Native `tool_calls` | Not supported end to end; tool/function settings in `extra_body` are rejected before rollout |

The next structured-decoding experiment should constrain the existing
`skill_name`/`arguments` answer with a JSON schema while retaining server-side
reasoning separation. vLLM supports this combination; see its
[structured output documentation](https://docs.vllm.ai/en/stable/features/structured_outputs/).
Do not manually append a JSON prefix after a textual `</think>` and assume that
it implements the server's tokenizer/parser protocol.

Native tools additionally require tool definitions, `tool_calls` decoding and
tool-result history. The client must enforce one action per simulator step and
reuse the same validator, coordinate adapter and evaluator. Merely enabling
vLLM's tool parser does not implement these client behaviors. Constraint behavior
also depends on tool choice, schema strictness and parser support; see the
[vLLM tool reference](https://docs.vllm.ai/en/stable/features/tool_calling/).
Syntactic constraints do not guarantee the correct target, action or task result.

Record the server version, checkpoint/tokenizer/template revisions, reasoning
parser and decoding settings for each experiment. History or action-boundary
fixes require fresh rollouts; rescoring old trajectories cannot reconstruct the
actions a corrected agent would have taken. Keep free-output and constrained
experiments separate, with new output directories and fingerprints.

## Image processing

The runtime saves the simulator's current RGB array as a lossless PNG at its
native render size (default **640 × 480**). The API client base64-encodes those
same bytes. It does not resize, crop, pad, convert to JPEG, reorder RGB channels,
or normalize pixel values. Native provider adapters rewrap the same base64
payload. A malformed/unsupported inline image fails the request instead of
silently becoming a text-only request.

Only the current image is sent. The previous 20 dialogue turns are text-only
under the baseline profile; segmentation and evaluator state remain hidden.
Each model turn records `image_input` with the exact bytes' SHA-256, PNG width
and height, MIME type, `transform: none`, and requested image detail. This lives
in reviewer evidence, never in model-visible observation text.

OpenAI `image_detail: default` omits the field, matching the historical request.
`auto`, `low` and `high` explicitly send a detail preference and change the run
fingerprint. Server-side resolution, tiling and vision-token limits remain a
provider responsibility; byte-identical input does not prove identical internal
vision preprocessing. Record these serving settings for reproduction.

Qwen chat templates and image processors belong to the serving checkpoint. Send
ordinary chat messages through the API; do not apply a second chat template in
the benchmark client. Record the checkpoint revision, processor/template revision,
vision-token limits and thinking configuration. A custom template requires its
own recorded serving configuration. The official
[Qwen model card](https://huggingface.co/Qwen/Qwen3-VL-32B-Instruct) demonstrates
both processor-side templating and OpenAI-compatible serving. VIGIL passes
`extra_body.chat_template_kwargs` through unchanged and never guesses a template
from the model name.

## Coordinate contract

| Setting | Meaning |
| --- | --- |
| `coord_mode: pixel` or empty | Model x/y refer to the original RGB pixel grid |
| `coord_mode: normalized_1000` | Model x/y use 0–1000 on each axis |
| `coord_prompt_mode: explicit` | Describe the selected coordinate convention |
| `coord_prompt_mode: none` | Suppress the extra hint, for explicitly selected historical requests |

The historical adapter first rounds each model value to an integer with Python
`round`, then maps it **once**:

```text
pixel_x = round(round(model_x) / 1000 * (width - 1))
pixel_y = round(round(model_y) / 1000 * (height - 1))
```

At 640 × 480: `(495,790)` maps to `(316,378)`, `(500,500)` to `(320,240)`, and
`(1000,1000)` to `(639,479)`. There is no heuristic unit detection, clamping or
second normalization. Out-of-image mapped coordinates are invalid actions.
`drop` operates on the held object and requires no coordinate.

Traces retain requested and executed arguments plus adapter input/output and
image dimensions. Resolved object identity stays in separate evaluator evidence;
it is not added to the interaction signature used to count retries. The previous
`explicit` hint incorrectly requested normalized coordinates even in pixel mode;
it now describes the selected mode.

Recovered source settings are model-specific:

| Historical model | Coordinates / hint | Public transport notes |
| --- | --- | --- |
| Qwen3.6-27B | normalized_1000 / none | 4096 tokens; existing historical helper also selects its correction retries |
| Qwen3.5-27B, Qwen3-VL-32B variants, InternVL3.5-38B | normalized_1000 / explicit | 4096 tokens; no JSON response constraint |
| Gemini 3.1 Pro, Doubao Seed 1.8 | normalized_1000 / explicit | Native Gemini or compatible chat; retain model-specific thinking options |
| GPT-5.4 | pixel / none | `max_completion_tokens`; omit temperature/top_p as in the old request path |
| Claude Sonnet 4, MiMo-Embodied-7B | pixel / none | Native Messages or compatible chat; no JSON response constraint |

These recovered settings are not immutable checkpoint manifests and are not a
universal preset. From 2026-11-04, general release defaults are 4096 tokens,
temperature 0.6, top-p 0.9 and the neutral-report policy. The earlier Qwen
experiment uses explicit temperature 0.2 / 4096 tokens; paper mainline also uses
a different prompt policy. Use the complete saved configuration and a compatible
runtime for recovery, or a new output directory for changed conditions. See
[paper alignment](PAPER_ALIGNMENT.md) before claiming paper reproduction.

## Retries and resuming

Transport retries (`request_max_retries`, `request_retry_delay_s`) now apply to
all three API formats. Defaults are 2 retries and 1 second; native providers
previously had no retry loop. HTTP 429/500/502/503/504 and network failures retry
the identical request body. Authentication failures and malformed responses
remain explicit errors. A successful turn records its transport attempt count.

HTTP 200 alone does not establish a valid model response. All three adapters check
the response envelope and text-block types; malformed candidates/messages become
`model_request_error`, so a gateway failure cannot count as a valid failed task.
Supported empty answers, truncation, refusals and safety-blocked responses remain
model outcomes. This follows the nullable content/finish fields in the
[Chat Completions reference](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
the candidate and prompt-blocking fields in the
[Gemini reference](https://ai.google.dev/api/generate-content), and Anthropic's
[stop-reason guidance](https://platform.claude.com/docs/en/build-with-claude/handling-stop-reasons).
These checks cover the supported text response forms, not every provider extension.

Model correction retries are separate: `protocol_retry_limit` and
`observation_echo_retry_limit`, both default zero. They add prompts and therefore
change the experiment. Neither is the paper's interaction **retry** metric.
All these settings enter run fingerprints and are forwarded to workers. A changed
configuration or this corrected runtime requires a fresh output directory.

## Validation scope

Offline tests cover provider request bodies, system/history ordering, identical
RGB bytes, completion budgets, image rejection, bounded retries, explicit
coordinate prompts, rounding, boundary behavior, drop, and separate target
evidence. A private comparison with the original client also matched five request
families after documented authentication/envelope field mappings and reproduced
the original PNG bytes. These checks do not certify an external provider's
checkpoint, server processor or live model outputs.

The historical main and feedback source maps cover 30,000 episodes. All **68,189
interactions with recorded normalized-coordinate adapters** match the current
rounding/mapping exactly. Another 17,837 interactions use pixels or lack a
normalized adapter record; no normalized-coordinate claim is inferred for them.
