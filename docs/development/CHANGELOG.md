[Documentation](../README.md) / Development

# Release changes and validation

## 2026-11-06 — make the README a complete run guide

- Document simulator installation, model configuration, a first episode, saved
  result inspection, full-pack execution and resume in both README languages.
- Keep the original benchmark video and the hardware-demo link. Place the brief
  benchmark-version note alongside batch evaluation and link detailed paper
  comparisons from there.

## 2026-11-06 — clarify the README introduction

- Introduce the evaluation question, simulator scope and included tools in two
  short paragraphs. Move the real-robot demo link below the introduction at
  normal text size, while retaining the benchmark overview as the lead video.

## 2026-11-06 — explain the hardware recordings and obscure faces

- Keep the original 152-second benchmark overview at the top of both READMEs.
  Embed the reviewed hardware walkthrough in the film guide, linked below the
  overview. Retain the chaptered local player for downloaded releases.
- Replace the mixed trailer with a 68-second introduction and two complete
  robot-view walkthroughs. Restore per-decision explanations, decision indices
  and chapter playback progress; identify trace-only closure annotations.
- Obscure human faces in all four full hardware recordings and their posters.
  Build the walkthrough from those reviewed, redacted inputs. Keep original
  action sequences and source playback timing; update hashes and editing notes.

## 2026-11-06 — bring hardware footage forward

- Add a 50-second trailer beginning with recorded robot motion, followed by a
  controlled-intervention replay and an archived simulation closure failure.
  Preserve experiment labels, complete sources and a reproducible edit manifest.
- Make the trailer the local player's entry point; keep the longer research film
  and all four hardware recordings accessible. Add a compact hardware link below
  the working GitHub overview player in both READMEs.

## 2026-11-06 — embed the overview video

- Replace the linked cover in both READMEs and the film guide with the uploaded
  GitHub video attachment. Keep the local MP4 and chaptered player available for
  downloaded source releases.

## 2026-11-06 — organize the paper and code entry points

- Show the full paper title at the top of both READMEs, with a compact VIGIL and
  NeurIPS label. Keep the film, quick start, model evaluation and citation in order.
- Link the cover directly to the MP4 and label its open/download behavior.
  GitHub-native attachment playback remains a separate pending upload.
- Put rendering requirements beside evaluation setup and state which paper
  evidence is available before introducing checks that require original archives.
- Add offline CI for Linux and macOS, covering tests, task validation, recorded
  evidence and clean source export. Include the workflow in the export allowlist.

## 2026-11-06 — simplify the reading path

- Lead both README pages with the film cover and remove the author/affiliation
  block. Keep paper, project and documentation links together in one short row.
- Organize the documentation around exploring, evaluating and reproducing;
  reveal detailed references and maintenance guides on demand.
- Move replay audit and advanced workspace details after the first-use steps,
  and label historical review pages consistently.
- Retain the native-control MP4 player and its byte-range preview server. A GIF
  is not a seekable video; README attachment upload is a separate publication step.


## Documentation and video playback

- Refocused the English and Chinese entry points on one film, recorded replay and a first model evaluation. Detailed references live in the documentation map.
- Replaced the non-seekable README GIF with the film poster linked to the original MP4. The source player has four main chapters, an expandable full timeline and a shared layout for hardware recordings.
- Added `python3 scripts/media/preview.py`, a standard-library-only, loopback-bound server with byte-range and HEAD support. It serves only presentation assets and starts no evaluations.
- Resolve directory-index symlinks before serving a page, so nested landing pages cannot expose files outside the presentation directory.
- Kept footage, source manifests, scoring, historical results and model-input contracts unchanged.


This records public changes assembled for the 0.1.0 release candidate. The source
tree is distributed without development history; entries identify the resulting
behavior and evidence rather than inventing commit references. Publication gates
remain in [the release checklist](RELEASE_CHECKLIST.md).

## 2026-11-05 — improve onboarding and contribution paths

- Add a source ZIP option to both quickstarts and a concise troubleshooting guide
  with commands for replay, environment checks, model setup and recovery.
  Consolidate installation remedies there to keep one maintained reference.
- Add GitHub-discoverable support, contribution, issue and pull-request templates
  without adding more files to the repository root.
- Include these guides and templates in source exports and existing link checks.

## 2026-11-05 — simplify the repository root

- Group the Chinese guide and changelog under `docs/`, configuration examples
  under `examples/config/`, and the Conda specification under `scripts/deploy/`.
- Keep third-party notices beside their license texts and generate the source
  manifest at `docs/development/release_manifest.json`.
- Keep Conda environment creation separate from the editable package install,
  so the relocated YAML does not change how relative package paths resolve.
- Update links, package license metadata and source export paths. Existing
  startup commands, benchmark data and runtime behavior remain unchanged.

## 2026-11-05 — reconcile release and camera-ready evidence

- Distinguish the pre-fix release run from the original primary paper archives.
  All 244,480 saved primary-archive frame-label diagnostics use `obs_<n>`.
- Include the corrected camera-ready closure-outcome figure separately from
  historical film illustrations, and document its unchanged W/B/FR/NR counts.
- Keep historical recordings, scoring code and benchmark inputs unchanged.

## 2026-11-05 — isolate model-visible frame labels

- Replace dataset-derived frame IDs with episode-local step labels. State-bearing
  task IDs no longer enter current observations, retries or conversation history.
- Add request-level regressions and document the affected pre-fix model result.
  Scoring and dataset inputs remain unchanged; post-fix model performance requires
  a new run. See the [frame-ID review](../reviews/FRAME_ID_REVIEW.md).
- Simplify the README overview entry and add clickable robot-video thumbnails.
  Move paper audit links to the reproduction instructions.

## 2026-11-05 — complete revised-pack model and evidence checks

- Complete a fresh Qwen3.6-27B run over all 1,000 corrected tasks with eight
  macOS simulator workers: W 42.4%, B 36.0%, no unresolved infrastructure errors.
  Uncached settlement, per-episode scores and aggregate scores agree.
- Decode all 14,714 RGB frames and match their hashes and dimensions to model
  input records. Verify all 4,686 normalized-coordinate conversions against
  executed arguments and preserve canonical assistant history.
- Compare the full historical/current selections and the 909 equal-input,
  44 changed-input and 47 removed/added groups. Historical W/B are 46.7%/37.8%;
  equal parsed inputs still differ. Scoring agreement is not an exact online
  reproduction claim. Record the request settings and largest family difference
  in the [metric alignment guide](../reference/METRIC_ALIGNMENT.md#2026-11-05-revised-pack-model-check).
- Update both READMEs, runtime/adoption notes and release checks with completed
  evidence. Document host sleep during local evaluation; runtime, task inputs,
  prompts, sampling and scoring formulas are unchanged by this documentation.

## 2026-11-04 — validate clean runtime installation and release artifacts

- Record clean installed-wheel checks on macOS and Linux, with three real
  scripted scene checks on each. The macOS check downloaded Unity into an empty
  cache; Linux used verified public wheels and an official archive prepared on
  another machine, with Xvfb/Mesa CPU rendering and no model calls.
- Add the tested Linux Python dependency constraints to source exports. Document
  missing `ensurepip`, slow downloads, exact Unity hashes and the scope of these
  runtime checks. Preserve the original Dresser audit in the review archive.
- Record scanner-generated component inventories and license checks for the
  candidate source and wheel, alongside disclosure and media-hash checks.
  Final artifacts must be rescanned when their bytes change.
- Synchronize the renderer-concurrency regression's child processes explicitly.
  A short fixed sleep could report insufficient overlap on a busy host even
  when the scheduler respected its limits. Runtime concurrency is unchanged.
- Correct the paper/metric alignment guides to match the 4096-token / 0.6 release
  defaults and the metric checker's frozen paper selection. Separate malformed
  model actions from infrastructure errors in the smoke-check criteria.
- Publish the current-versus-retained input comparison with raw and normalized
  JSON hashes. Distinguish 909 shared tasks with equal parsed inputs from 44
  shared tasks with changed inputs and 47 additions/removals; identical IDs
  alone must not imply identical inputs in score comparisons.
- The reconciled runtime passes 711 offline tests, the 20-model main and neutral
  historical panels, the 10-model corrected feedback panel, and two full
  recursive aggregate comparisons. Full-pack live acceptance was still pending
  at that checkpoint; the completed run is recorded in the 2026-11-05 entry.

## 2026-11-04 — reconcile release fixes, reasoning boundaries and defaults

- Integrate the earlier completion/experiment-identity and malformed-response
  checks with the revised 1,000-task pack and the reorganized `.agent/`, docs
  and maintainer tools. Parent-directory rescoring honors nested run status;
  different recorded experiments cannot contribute to one aggregate.
- Preserve the ground/pick clarification and native reasoning evidence. Always
  guard inline thinking boundaries, including nested blocks and empty native
  reasoning fields. Empty chat answers never fall back to envelope draft text.
- Keep only parsed protocol fields in assistant history and correction requests;
  preserve protocol `thought`, with raw provider output retained in trace
  evidence. Record the history policy as `canonical_payload_v1`. Normal text
  prefixes remain parseable. Runtime and prompt changes require fresh rollouts.
- Retain the merged 0.6 temperature / 4096-token defaults across all public
  entry points. Test both these defaults and explicit 0.2 / 4096 historical
  settings across the three API formats. Existing configuration values win.
- Preserve the optional installation/smoke helper as
  `scripts/deploy/quickstart.sh`; smoke mode does not run developer tests.
  Export the helper and its regression tests with the source release.
- Add focused offline regressions for the review findings. No new live-model
  or full-pack score-reproduction claim is made by these changes.

## 2026-11-03 — adopt revised data and correct Drawer targets

- Add optional `--render-devices 0,1` to distribute renderer slots across already
  assigned GPUs, with child-local environments, cancellation-safe slot release
  and device-list fingerprints. Preserve the existing default device selection.

- Make the revised 1,000-task selection the default, with 258 iTHOR and 742
  ProcTHOR tasks across 67 built-in scenes and 456 bundled houses.
- Version nine retained SV targets as actual Drawers, aligning their setup,
  instruction and report bindings. Freeze one corrected initial pose; retain
  all budgets. All nine pass 18 real-simulator correct/incorrect report checks.
- Complete the 1,000-task macOS initialization audit without failures: 527 new
  checks and 473 successful checks reused only for identical inputs/runtime.
  One Linux Qwen3.6-27B RGB episode also passes independent evidence verification;
  full model results remain pending.
- Preserve the original paper selection and target hashes for historical
  score checks. Label film counts as original paper data, and update current
  documentation and provenance. See the [adoption record](../reviews/REVISED_DATA_ADOPTION.md).
- Show an explicit 16-worker, 16-renderer capacity configuration; setting
  workers alone still respects the existing renderer cap.

## 2026-11-03 — enforce action boundaries and separate reasoning from history

- Connected the existing public action validator to the rollout runner before
  environment execution. Direct simulator calls and incomplete public actions
  now remain explicit protocol failures, with attempted actions preserved.
- Keep inline think blocks out of subsequent dialogue and correction requests;
  unfinished reasoning cannot supply an executable action. Preserve original
  responses, native reasoning fields and retry attempts as trace evidence.
- Reject native tool/function configuration that the text-action client cannot
  execute end to end. Document JSON-object mode, proposed schema constraints and
  native tool calling as distinct capabilities and experimental conditions.
- Added action-boundary, pick/ground, reasoning-history and provider-wire
  regressions. These runtime changes require fresh rollout directories;
  historical trajectories and score formulas are unchanged. See the
  [protocol review](../reviews/PROTOCOL_REASONING_REVIEW.md).

## 2026-11-03 — compare the requested revised data baseline

- Compared the fixed upstream revised pack, all 1,000 selected executable tasks
  and 456 referenced houses with the local release. Recorded 38 replacements and
  82 tasks with changed execution inputs, matching the upstream data-fix subset.
- Documented the nine unchanged Dresser defects, revised SM budgets, stale
  revision-report counts and the historical paper checksum boundary. Static
  loading and dry-run checks pass; the default release data is not changed by
  this comparison.

## 2026-11-03 — distinguish scoring parity from valid simulation

- Established a concrete repair scope for the Dresser defects: ten real Drawer
  bindings and two initial poses need review. Two isolated binding candidates
  pass four real-Unity scripted report checks with correct W/B and uncached score
  parity. This is repair feasibility evidence; the canonical pack is unchanged.
- Rechecked the existing environments, saved rollouts and all three historical
  scoring panels; documented 635 passing offline tests and the limits of those
  checks.
- Confirmed ten Dresser state-verification tasks request unsupported open/close
  setup actions on both cached macOS builds. Added the concrete release blocker
  to both READMEs and the runtime/checklist guides. Task files, archived scores
  and score formulas are unchanged; full-pack live acceptance remains incomplete.

## 2026-11-02 — validate initialization and record scene provenance

- Require confirmed success for scene creation, initial teleport and every setup
  action before requesting a model turn. Failed initialization remains simulator
  infrastructure evidence and cannot enter final task metrics.
- Recognize a repeated setup state setter only when the exact object's metadata
  already confirms its intended state; record that evidence in the trace. This
  avoids rejecting a valid starting state merely because THOR refuses to repeat
  an on/off/open/closed transition.
- Removed the unused `prior` package from the simulator extra, installed-wheel
  setup guidance and experiment identity; bundled houses load directly from JSON.
- Recorded operating system and process architecture in the runtime fingerprint
  so recovery cannot silently cross incompatible renderer platforms.
- Added a public provenance manifest for all 465 houses. The 47 imported scenes
  match a pinned ProcTHOR-10K revision; the 418 generated scenes are distributed
  as frozen evaluation inputs. Task and house bytes are unchanged.
- Aligned the data coverage table with the paper's PG/DA/VS/SV/AI/SI/SM/CR names.
- Validated both historical warning scenes with the cached macOS Unity build:
  initialization, RGB and target grounding pass. Published that runtime's package
  constraints and validation scope; these diagnostics do not use a model.
- Avoided treating a complete four-part package version pin in a requirements or
  constraints text file as an IP address. Address URLs/comments and exact known
  private-value matches remain checked.

## 2026-11-02 — reject incomplete or mixed evidence and malformed API responses

- Applied each nested run's completion state and selected IDs when rescoring a
  parent directory. Old unselected traces can no longer change its denominator.
- Reject incompatible recorded experiment fingerprints across directory and
  explicit-file scoring inputs. Legacy untracked evidence still requires review.
- Validate supported provider response envelopes and text fields before accepting
  a model answer. Broken HTTP 200 responses become infrastructure failures; valid
  empty, truncated and refused outputs retain their model-outcome classification.
- Protect output directories containing only retained frames or run metadata.
  Recovery requires a matching fingerprint and explicit `--resume-existing`.
- Added regression cases for these boundaries. Prompts, request serialization,
  RGB input, coordinate conversion, retry behavior and score formulas are unchanged.

## 2026-11-02 — audit API rollout, offline evaluation and concurrency

- Shared completed-trace structure and infrastructure checks between offline
  scoring, run verification and resume. Broken step sequences can no longer pass
  offline scoring while failing verification. Scoring formulas are unchanged.
- Prevented scoring outputs from overwriting existing files and direct single
  episode runs from overwriting retained rollout evidence. Pack recovery remains
  fingerprint-checked through `run --resume-existing`.
- Offset the compatible API replica pool across isolated episode workers, so
  their first requests no longer all target the first endpoint.
- Exposed simulator startup/render limits and effective concurrency in the UI.
  Clarified per-run API bounds versus provider RPM/TPM and multi-job quotas.
- Added a direct saved-rollout evaluation path to both READMEs and documented
  supported evidence formats, fresh score outputs and offline validation scope.

## 2026-11-02 — simplify the benchmark entry and repository structure

- Follow-up review fixed a global `--config` being overwritten by UI defaults;
  custom `init` paths now carry through to the printed UI command. The UI rejects
  `--no-config` with guidance instead of silently ignoring it.
- Bound pack task loading, fingerprints and worker arguments to `--episode-root`,
  preventing same-named working-directory files from replacing selected tasks.
  Explicit files remain supported by `run-episode`.
- Closed the missing-status `report` bypass. Run directories require verified
  evidence; independent summaries are labeled unverified and checked for invalid
  counts, duplicate IDs and nonfinite rates. Scoring formulas are unchanged.

- Moved the complete assistant instructions to `.agent/AGENTS.md`, with no root
  instruction file. README and the contributor guide provide explicit discovery.
- Rewrote both READMEs around task coverage, recorded replay, model configuration,
  one real episode and scaled evaluation. Split documentation into guides,
  reference, development and review records; grouped maintainer tools by purpose.
- Added offline `vigil catalog`, using executable task definitions for examples,
  budgets and simulator counts. Added `vigil init --model ... --base-url ...`
  without copying environment credentials into the file or overwriting settings.
- Made installed `vigil ui` choose an available port, matching `bash start.sh`.
  Promoted `vigil run` in help while retaining the `run-pack` alias.
- Removed the duplicate quickstart/progress shell entry points. Use the standard
  installation instructions, `vigil smoke` and `vigil progress`. Maintainer script
  paths changed; see [the tool map](../../scripts/README.md). Scoring, task data, model
  prompts and observation/coordinate contracts are unchanged.

## 2026-11-02 — license the project and strengthen publication checks

- Added the approved Apache-2.0 license for original code, task definitions and
  benchmark annotations, project notices and SPDX wheel metadata. Source and
  wheel distributions retain all three upstream license texts.
- Extended the disclosure checker to source ZIPs and optional exact matching
  against private JSON configuration values, including encoded credentials and
  endpoint addresses. Private values never appear in reports.
- Added checks for encoded addresses, quoted environment credentials, additional
  credential/configuration files and unsafe archive entries. Redacted sensitive
  filenames in both findings and the media-review list.
- Licensing does not close the remaining scene-provenance, tested-runtime and
  publication checks documented in the release checklist.

## 2026-11-02 — align API transport, images, coordinates and feedback statistics

- Traced five paper retry discrepancies to a failure-label fallback used for
  truncated aggregates. Added a complete paired-evidence checker and separate
  published/corrected targets. The original scorer and archived outcomes remain
  unchanged; corrected means are documented with integer event counts.
- Preserved Gemini system instructions and Anthropic prompt text, added explicit
  completion-token fields, retained original PNG bytes across provider formats,
  rejected images that cannot be transported, and excluded thinking blocks from
  parsed visible answers. Model turns record image hashes and dimensions.
- Unified bounded transport retries across providers and exposed their settings,
  image detail and correction retry limits through configuration, CLI, workers
  and resume fingerprints. Native providers now share the default two retries;
  model correction retries remain disabled by default.
- Corrected explicit pixel-mode guidance; retained the historical round-then-scale
  normalized coordinate formula. Recorded adapter input/output and dimensions,
  rejected out-of-image coordinates, kept resolved objects outside action retry
  signatures, and restored coordinate-free `drop` execution. These runtime fixes
  require fresh output directories; they do not establish new live model parity.

## 2026-10-30 — add complete recorded demos to the research film

- Added 44 seconds of dedicated fridge, apple and kettle demos after the eight
  task introductions. The film is 152 seconds, with data and metric explanations
  retained and no workbench walkthrough.
- Showed every action and before/after observation, executed pixel locations,
  original reports and closure outcomes. Failed attempts remain; feedback
  intervention cases are labeled. The kettle opening receives a four-second
  comparison before all 16 post-attainment actions and no-report exhaustion.
- Rebuilt captions, chapter links and the animated preview around the demos.
  Original recordings, benchmark data and scoring remain unchanged.

## 2026-10-30 — explain tasks, data and evaluation in the film

- Replaced the workbench walkthrough with a research overview: each of the eight
  task families receives its own example before dataset and metric explanations.
- Recomputed family, simulator and scene counts from the frozen release. Added
  six actual ProcTHOR floor layouts, labeled as evaluator-side assets.
- Extracted native RGB illustrations from the paper and retained labeled archived
  fridge/apple actions. Explained W, B, their gap, FR, NR and IL. The film is now
  108 seconds with English captions; task data, runtime and scoring are unchanged.

## 2026-10-30 — prevent private content in public artifacts

- Added an offline public-content gate before release export, plus a standalone
  directory/wheel checker. It reports locations without echoing suspected values.
- Recorded example export checks transport-field variants, IPs, private hosts,
  provenance filenames and compressed PNG text metadata before copying evidence.
- Rejected credentials in endpoint URLs and nested request options before they
  can enter metadata or worker arguments. Config representations hide keys; the
  workbench redacts nested and encoded credentials, including invalid old settings.
- Expanded private-file ignore rules, narrowed wheel static assets and replaced
  a test's private IP with a documentation-only address. Added disclosure checks
  and guidance for media, Git history and history-free public exports.

## 2026-10-30 — introduce the benchmark before showing results

- Replaced the opening final-score comparison with a five-second VIGIL
  introduction, followed by the task instruction and the first episode's reset
  observation. Removed the unrelated episode montage before the first action.
- Moved the paired final-outcome recap to 01:22, after the demonstrations. The
  original action sequences retain their timing; the film remains 90 seconds.
- Updated the poster, English captions, player chapters and footage map to the
  same order. Original observations, traces and scores are unchanged.

## 2026-10-30 — improve film clarity

- Replaced the README's low-resolution GIF entrance with a full-resolution
  poster linking to the original 1080p MP4. The GIF remains an optional preview.
- Removed full-screen stretching of 640 × 480 observations, reduced action
  playback enlargement and replaced the kettle's 8.3× crop with full observations
  and small, labeled 2× details. Cut directly between action observations to
  remove blended camera poses.
- Recaptured the original response with larger browser typography; recorded the
  authoring-only CSS and source hashes. UI screenshot crops no longer upscale.
- Changed video encoding from CRF 23 to 17, and generated the 960-pixel,
  256-color GIF without a second lossy video intermediate. Original RGB, traces,
  scoring and the application's UI stylesheet remain unchanged.

## 2026-10-30 — complete the local archive inventory

- Included the previously omitted local archive roots. Found
  31 models with complete 1,000-episode runs across 197 directories, including
  ablations and copies. Twenty-two truncated feedback aggregates retain intact
  individual episode files; two older aggregates have stale coverage.
- Reran the current paper gate: main panel 20/20 and neutral-report panel 20/20,
  each with 20,000 episodes and exact overall/family W/B counts.
- Located all ten feedback sources. Their W/B/FR/NR deltas match exactly;
  five feedback retry means still disagree with the paper. Corrected the
  earlier misclassification of the `proprio_minimal` feedback profile.
- No scoring, model input or original result files changed. This is an offline
  archive audit, not new rollout reproduction. Source maps and detailed local
  inventory are excluded from the public export.

## 2026-10-30 — audit existing rollouts and reject incomplete scoring inputs

- Reaudited 18,000 archived episodes. Eight identified main-paper runs match
  overall/family W/B and uncached scalar scores; missing historical diagnostics
  and unmatched references are documented in the [rollout audit](../reviews/ROLLOUT_SCORE_REVIEW.md).
- Offline scoring rejects historical error records, inconsistent aggregate
  coverage, incomplete run status and unfinished or infrastructure-failed traces.
- The paper checker derives report matching from the executed report instead
  of trusting saved match flags. State reports and correct negative reports
  retain their existing W/B definitions.
- Batch execution checks request/simulator failures before generating final
  aggregate metrics, preserving nonzero exit and resume behavior.
- Added 18 focused regression cases and isolated workbench tests from local
  experiment outputs. Full offline suite: 407 passing tests. Scoring formulas,
  prompts, task data and existing rollouts are unchanged.

## 2026-10-30 — enforce architecture boundaries

- Flattened `src/vigil/` to the root `vigil/` package. Updated launchers, helper
  scripts, data/resource lookup, explicit package discovery and export paths.
  Source users can run `python -m vigil` without installation.
- Replaced eager root imports with lazy public API exports and removed the 30
  pre-publication module aliases. Earlier internal import paths require the
  migration map in [Architecture](ARCHITECTURE.md); public root symbols and
  CLI commands remain stable.
- Moved batch execution, workers, cancellation and aggregation from the CLI into
  `eval/batch.py`. Moved task selection and episode resolution into `data/`.
- Extracted shared pure task predicates into `data/conditions.py` and environment
  result types into `envs/types.py`. Environment code no longer imports the judge.
  Condition and scoring logic are preserved.
- Deferred AI2-THOR imports until explicit simulator construction. Offline state,
  CLI and recorded-workbench paths no longer load the episode runtime or simulator.
- Added cold-process import guards and layer-boundary regression checks, covering
  failures that static import checks missed. See the [critical review](../reviews/ARCHITECTURE_REVIEW.md).

## 2026-10-30 — layered code and a shorter first-use path

- Moved implementation into `agent/` (including provider backends), `eval/`,
  `data/` and `envs/`. Model request/history logic now lives with the agent.
  Earlier Python import paths remain aliases; CLI and scoring contracts stay
  unchanged. Source data discovery and whole-package fingerprints follow the
  new layout. `python -m vigil` is also supported.
- Added four project skills in `.agent/skills/`, linked from `AGENTS.md`, plus
  current architecture and contributor guides. Replaced the old proposed
  architecture with a pointer to the implemented layout.
- Rewrote both READMEs around replay, configuration, one real episode and result
  inspection. Full-pack execution is a separate optional step. CLI selection now
  accepts PG/DA/VS/SV/AI/SI/SM/CR without altering stored task identifiers.
- Separated UI read directories from new evaluation output (`--out-dir`, default
  `outputs`). Credential snapshots live in owner-only temporary storage outside
  result folders. Public exports include only hash-verified curated recordings,
  excluding incidental runs and hidden configuration files.
- Added direct home-page links to the six film trajectories and a visible sticky
  run action bar. The installed wheel retains its self-contained two-episode demo.
- Runtime fingerprints change with the refactor. Existing results can be
  inspected; live runs using the new revision need a fresh output directory.

## 2026-10-30 — clearer demonstrations and real workbench walkthrough

- Recut the 90-second film: shortened the repeated fridge sequence, held a
  magnified before/after view of the kettle lid, and added the eight-family
  benchmark scope and 20 seconds of actual workbench captures.
- Added two complete state-verification recordings with byte-identical initial
  RGB and opposite reports. The curated set now contains six episodes, 43 actions
  and 49 original observations. Both new cases pass independent settlement and
  score recomputation; neither changes the benchmark contract.
- Fixed film outcome timing: B settles when the final action's evidence appears,
  including budget exhaustion, instead of waiting for the editorial end hold.
- Updated the English captions, chapter navigation, source hashes, previews and
  portable replay instructions. UI shots are labeled as edited captures; original
  step observations and evaluator overlays remain distinct from model input.

## 2026-10-29 — recorded cases and trajectory film

- Added four complete curated recordings: verified fridge opening, apple pick and
  place, an unsupported fridge report, and post-attainment kettle interaction.
  Their 41 actions and 45 original PNGs retain per-case models and profiles.
- Added a portable archive exporter that checks raw/parsed/executed actions,
  coordinate adapters, all source settlement fields, scalar score summaries and
  frames before producing a replay. Private transport fields are excluded.
- The workbench displays archived model action text as well as executed pixels,
  identifies curated recordings and their feedback profile, and uses the paper’s
  PG/DA/VS/SV and AI/SI/SM/CR display names without changing task identifiers.
  Removed redundant provider transport responses from the small built-in demo;
  model output, evaluator evidence and scores are retained.
- Recut the 90-second film around real demonstrations, pixel markers, paired
  playback and a post-attainment action counter. Two feedback-intervention cases
  remain labeled; a separate paper comparison supplies the 19.7 pp result.
- Updated both README entries, the player, captions, source manifest and export
  allowlist. Curated records ship in the source distribution, outside the wheel.

See [recordings and verification](../../examples/recorded-runs/README.md) and
[film sources and rebuilding](../VIDEO.md). No model or simulator was started.

## 2026-10-29 — release data and distribution audit

- Documented the canonical task distribution: eight families of 125 tasks,
  with 265 iTHOR and 735 ProcTHOR tasks referencing 69 built-in scene names and
  465 bundled house specifications.
- Clarified archive size, wheel/data separation and the external simulator asset
  requirement. The complete source ZIP is approximately 7.2 MB.
- Parsed all 1,000 executable configs and resolved all 735 ProcTHOR task references
  through the public house loader, without starting Unity or calling a model.
  No house reference is missing or unused. Task and scene bytes are unchanged.
- Recorded source-revision gaps and two retained generation warnings for targeted
  review. These checks do not establish full runtime coverage or paper reproduction.

See [data coverage and validation scope](../reference/DATA.md). The project license,
runtime reproducibility specification and publication checks remain unresolved.

## 2026-10-29 — scoring and worker failure review

- Directory scoring now rejects broken or missing selected traces instead of
  silently shrinking the metric denominator. Run directories and their trace
  folders follow `run_status.json`; explicit files allow a different subset.
- Redacted HTTP/transport failure details and formatted exception chains across
  the compatible, Gemini and Anthropic clients, including encoded credentials.
- Classified Anthropic gateway error envelopes as request failures; genuine
  model refusals and empty outputs remain model responses.
- Fatal worker exceptions cancel pending work and active isolated episode
  processes. The first error is preserved and run state records failure or
  cancellation; completed artifacts remain available for compatible resume.

Eighteen fault-injection cases failed before these fixes. See the
[second review](../reviews/RELIABILITY_REVIEW.md) for reproductions, regression coverage
and limits. The complete source suite passes 341 tests. Existing live evidence
remains consistent across eight episodes and 81 steps, with W = B = 4/8.
No new model requests or simulator evaluations were used.

## 2026-10-29 — visual refresh and adversarial repository review

- Reworked the overview, navigation, metric cards and replay surfaces; the first
  screen now includes a real recorded RGB observation and immediate replay access.
- Added `bash start.sh` and macOS `start.command`. Source browsing requires only
  Python 3.10+, without package installation; automatic interpreter discovery and
  port selection reduce first-launch failures. Existing CLI installation still works.
- Rejected non-boolean trace/judge evidence. Both run-directory reports and the UI
  now verify the settlement/score/aggregate chain before showing final metrics.
- Removed configured API keys from evaluator child command lines; each child gets
  the effective credential through its own environment.
- Closed result-directory and metadata symlink escapes. Isolated malformed runs
  in the library and cleared stale display values when changing runs.
- Removed full-run score/frame enumeration from single-frame requests. Added
  interpreter-specific simulator installation hints and early missing-runtime errors.

Seventeen adversarial cases failed before the corresponding fixes. See the
[review report](../reviews/WORKBENCH_REVIEW.md) for severity, reproduction, implementation
links, regression evidence and remaining limits. All model/simulator evidence
used during this review is recorded; no new model or GPU workload was launched.
The full source regression suite passes 319 tests, and the existing eight-episode,
81-step live recording remains consistent under the stricter evidence checks.

## 2026-10-29 — onboarding and offline run inspection

| Change | Result for users | Implementation / evidence |
| --- | --- | --- |
| Project instructions and a documentation map | Assistants and contributors have one root entry, concrete commands and benchmark constraints | [AGENTS.md](../../.agent/AGENTS.md), [guide map](../README.md) |
| Chinese onboarding and deployment guides | Clear routes for recorded replay, desktop/API use, existing cloud hosts and multi-GPU serving | [中文入口](../README.zh-CN.md), [installation](../guides/INSTALLATION.md), [deployment](../guides/DEPLOYMENT.md) |
| Evaluation and trajectory guides | Explain worker/render capacity, selection, resume, W/B, evidence and manual multi-machine limits | [evaluation](../guides/EVALUATION.md), [trace analysis](../guides/TRACE_ANALYSIS.md) |
| Public `vigil verify-run` | Rebuild cached settlements from steps and compare saved scores and aggregate; optionally check frame headers | [run inspection](../../vigil/eval/inspection.py), [regression tests](../../tests/test_run_inspection.py) |
| Portable `vigil progress` and shell wrapper | Fix GNU-only `find -printf` on macOS; count the latest selected episodes and avoid implying that file counts are valid metrics | [progress command](../guides/TRACE_ANALYSIS.md), [CLI](../../vigil/cli.py) |
| Export includes user and assistant guides | Root documentation is present in the history-free public copy | [exporter](../../scripts/release/export_public_release.py), [release checks](../../tests/test_release_hygiene.py) |

The new inspection commands were exercised on the bundled two-episode example and
the saved eight-episode live experiment (81 steps). Both agree exactly at settlement,
episode-score and aggregate levels. This is offline re-verification of existing
live evidence, not another API run. Added failure-injection checks cover incomplete
runs, invalid selections, missing evidence, inconsistent settlements/scores/aggregate,
step ordering and optional frame retention.

The complete source suite passes 295 tests at this stage, including export
manifest checks and relative links across the shipped Markdown documentation.

## 2026-10-29 — public interactive workbench

- Added `vigil ui`: configure a model, choose tasks, run selected episodes, inspect
  progress, stop owned work and replay RGB with pixel/action/judge overlays.
- Packaged two real recorded episodes so first use needs no simulator or API key.
  Static UI files and demo images are included in the wheel; no frontend build is
  required. Missing benchmark data does not prevent viewing the example.
- Reused the CLI runner, shared configuration validation and scorer. UI opening
  starts no evaluation. Only one owned run is active per workbench.
- Saved model settings and immutable per-run snapshots with owner-only permissions.
  HTTP responses omit keys; mutations require same-origin/session checks. Run file
  access stays inside the selected results directory. The server binds to loopback.
- Corrected task difficulty display and pixel-marker scaling. Incomplete, cancelled
  and infrastructure-failed runs do not present stale W/B as final metrics.
- Propagated cancellation through bounded episode processes and queued render slots;
  stopping the workbench run cleans up only its owned processes.

Code: [workbench](../../vigil/web/app.py), [process execution](../../vigil/eval/process.py),
[configuration](../../vigil/config.py). Evidence: [UI tests](../../tests/test_web_app.py),
[process tests](../../tests/test_process_runner.py). At this stage the source and exact
export each passed 273 offline tests. The installed wheel's HTTP UI, demo scores
and RGB assets were checked from a clean environment without a key, simulator or
benchmark data. Browser review exercised replay, filtering and local setup checks.

## 2026-10-29 — API integration and real subset

- Fixed proxy-prefix URLs ending in `/v1` so compatible requests reach the correct
  chat-completions route.
- Honored custom Gemini authentication headers. Detected HTTP 200 gateway error
  envelopes as request failures instead of empty model answers; preserved genuine
  Gemini safety responses as model responses.
- Kept failures and error text credential-safe. Existing provider settings,
  coordinate adapters and the benchmark action contract remained explicit.

Code: [model configuration](../../vigil/agent/backends/base.py),
[Gemini adapter](../../vigil/agent/backends/gemini.py),
[compatible adapter](../../vigil/agent/backends/openai_compatible.py).
Evidence: [backend tests](../../tests/test_backends.py),
[live integration regressions](../../tests/test_live_alignment_fixes.py).
The backend/usability/integrity selection passed 88 tests at this stage.

A `gemini-3-flash-preview` API experiment covered one task in each of eight families,
four iTHOR and four ProcTHOR episodes, with original budgets: 81 steps, W = 4/8,
B = 4/8, no infrastructure or protocol failures. This small subset establishes
end-to-end execution and internal result consistency, not full benchmark quality.
[The review record](../reviews/REVIEW.md#live-api-follow-up-2026-10-29) contains selection
indices, generation settings and the measured scope. The public demo retains two
sanitized recordings from this experiment; private endpoints and credentials are
not part of the release.

## 2026-10-28 — result integrity review and usability foundation

| Problem addressed | Fix | Regression evidence |
| --- | --- | --- |
| Cached settlement could disagree with trace evidence and alter W/B | Check outcomes, budgets, counts and diagnostics against steps; share judge failure/report semantics | [settlement](../../vigil/eval/settlement.py), [integrity tests](../../tests/test_review_integrity.py) |
| Paper evidence could omit final truth or include invalid report placement | Require per-step boolean world evidence and consistent terminal/count fields | [paper checker](../../vigil/eval/paper_alignment.py), [paper tests](../../tests/test_paper_alignment.py) |
| Provider extensions could overwrite model or generation fields | Reject conflicting fields, honor native options, separate Gemini reasoning from action text | [backends](../../vigil/agent/backends/base.py), [backend tests](../../tests/test_backends.py) |
| Parallel writers or interrupted resumes could leave misleading aggregates | Output locking, atomic state, completion checks and matching experiment fingerprints | [run state](../../vigil/eval/state.py), [integrity tests](../../tests/test_review_integrity.py) |
| Imported action validity and standalone infrastructure exit codes could drift | Preserve validity metadata and return nonzero for infrastructure failures | [scoring](../../vigil/eval/scoring.py), [CLI](../../vigil/cli.py) |
| Starting a model run required too much configuration | `init`, `smoke`, `run`, `doctor`, `report`, data discovery and CLI/file/environment precedence | [configuration](../../vigil/config.py), [usability tests](../../tests/test_usability.py) |
| Long or concurrent execution lacked simple bounds | One worker by default, bounded episode processes, explicit concurrency and resume | [process tests](../../tests/test_process_runner.py) |
| Discarding images risked changing model input | `--no-frames` removes retained files while preserving RGB input during execution | [simulator runner](../../vigil/eval/runner.py), [runner tests](../../tests/test_sim_runner.py) |

The review stage passed 243 tests and 4,000 synthetic contract comparisons across
the 1,000 task definitions. Published target transcription matched 40 rows and 720
numeric cells. Synthetic event comparisons do not execute a model or Unity;
transcription checks do not reproduce historical trajectories.

## Remaining limits

- A complete new 1,000-episode model run and the full historical trajectory gate
  are not established by the eight-episode experiment. Table 3 feedback retry
  discrepancies remain documented in [paper alignment](../reference/PAPER_ALIGNMENT.md).
- Cloud and multi-node serving examples require target-host validation. There is
  no automatic cluster provisioning, renderer placement or certified shard merge.
- Dependency ranges are not a reproducibility lockfile. Capture installed versions,
  serving configuration and weight revisions for each experiment.
- The UI is a personal local/SSH tool. It does not provide multi-user scheduling.
- The final project license and publication links still require completion before
  publishing. Third-party notices are retained in exports and distributions.
