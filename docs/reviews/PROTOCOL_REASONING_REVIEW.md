[Documentation](../README.md) / [Review archive](README.md)

# Action protocol and reasoning review — 2026-11-03

**Follow-up:** the revised selection and nine Drawer repairs are now the default;
see [the adoption record](REVISED_DATA_ADOPTION.md). Counts and unchanged-data
statements below describe the earlier review snapshot.

This review checks the current release implementation. It does not attribute an
unavailable historical patch or claim new model scores.

| Reported issue | Current finding and disposition |
| --- | --- |
| Replace the 1,000-task dataset | The revised upstream subset is staged and compared. The default release still uses the older pack; migration and simulator acceptance remain unfinished. |
| Confused pick/act protocol | No `act`-to-`pick` alias exists. A separate execution-boundary defect was confirmed and fixed: the rollout runner did not call its existing public action validator. |
| Think text enters later context | Confirmed and fixed for inline reasoning blocks in conversation history and both correction-retry paths. Unfinished reasoning cannot supply an action. |
| Use native JSON/tool mode | Current JSON-object mode does not enforce an action schema. Native tools are not implemented end to end; unsupported configuration now fails before rollout. |

## Execution boundary

`vigil/actions.py` declares four public skills and validates their arguments.
Previously, `vigil/eval/runner.py` passed any parsed action to the environment
without using that validator. `vigil/envs/thor.py` includes lower-level THOR
adapters, so an answer naming `PickupObject` and an object ID could bypass pixel
grounding. A missing `interact_pixel.intent` could reach the adapter's default
`ground` behavior. A public prompt alone did not enforce the protocol.

The shared runner now validates every action before `env.step`, including custom
agents. Rejections consume the normal protocol-failure step budget and preserve
the attempted action and empty executed arguments. The existing judge,
settlement and offline scorer handle these failures. The change is identified
by `action_validation_policy: public_registry_v1` in new traces.

The intended mapping is explicit:

| Model invocation | Meaning |
| --- | --- |
| `interact_pixel`, intent `ground` | Indicate the pixel target; no pickup |
| `interact_pixel`, intent `pick` | Pixel-resolve the target and attempt `PickupObject` |
| `interact_pixel`, intent `pickup` | Existing registered alias for `pick` |
| Top-level `pick` or `act` | Invalid public skill |
| `interact_pixel`, intent `act` | Invalid interaction intent |
| Top-level `PickupObject` or `Interact` | Invalid public skill; no direct simulator execution through rollout |

`Agent.act()` names the Python interface. It is not an action in the model
protocol. Tests also establish that picking an object does not earn PG grounding
credit: only the intended `ground` interaction does. This does not establish
what a historical, unavailable “pick/act” patch changed.

## Reasoning separation

The old parser removed only closed think blocks during action extraction.
Conversation recording and correction requests copied the original response.
Consequently, a complete reasoning block reappeared in the next request, while
an unfinished block containing action-shaped JSON could be executed.

`vigil/agent/parser.py` now guards reasoning boundaries, including nested blocks
and responses whose opening tag belongs to the server template. Unfinished or
mismatched blocks do not produce actions. `vigil/agent/model.py` applies the
same separation to history and both correction paths. Quoted tag literals inside
valid JSON and the declared final-answer `thought` field are preserved.

Native `reasoning`/`reasoning_content`, raw responses and retry attempts remain
reviewer evidence. They are not converted into executable answers or later
assistant messages. The diagnostic policy is `visible_content_v1`. This is not
a general semantic/repetition collapse detector; no serving-stack performance
claim follows from these offline tests.

## API choice and score acceptance

Use server-side reasoning separation with a parser appropriate to the model.
As a separate experiment, strict JSON Schema for the existing text action is
a smaller protocol change than native tool calls. Native tools additionally
need tool definitions, call parsing, single-action enforcement and tool-result
history. The current client rejects tool/function fields in `extra_body` rather
than pretending those paths are complete. See the
[API guide](../reference/API_ALIGNMENT.md#json-constraints-versus-native-tools)
for implementation boundaries and official serving references.

These fixes change possible trajectories. Run new experiments in fresh output
directories; do not overwrite old results, relax fingerprints or rescore old
actions as if a corrected agent had generated them. Offline rescoring remains
useful for consistency checks of the actual saved execution.

The requested revised data changes 82 tasks' execution inputs and still contains
nine known Dresser setup defects. Synchronize pack/tasks/houses, repair and
freeze that baseline, then finish simulator acceptance before using it for new
full-pack scores. See the [data comparison](REVISED_PACK_COMPARISON.md).

## Validation evidence

The new suites cover reasoning history and wire payloads, invalid action
execution barriers, pick/ground semantics, protocol settlement/rescore parity
and unsupported native-tool settings. Related parser, backend, configuration,
runner, scoring, settlement, integrity and paper-alignment suites passed
**231 tests**. The complete offline suite then passed **668 tests**, including
export-content and documentation-link checks. The result is retained locally in
`outputs/protocol-reasoning-review/full-suite.log` and `full-suite.xml`.
The bundled replay also passes `verify-run --require-frames` for its two
episodes and five steps (W = B = 1/2).

Tests use local fixtures and mocked provider/simulator responses. They do not
establish a fresh live rollout, vLLM deployment or revised-pack score. No model
service or GPU job was started for this review.
