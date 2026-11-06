"use strict";
const $ = (id) => document.getElementById(id);
const state = {
  token: "",
  episodes: [],
  runs: [],
  selected: new Set(),
  page: 0,
  run: null,
  replay: null,
  step: 0,
  timer: null,
  dirty: false,
  polling: false,
  readiness: {},
};
const labels = {
  S1_pixel_grounding: "PG · Pixel grounding",
  S2_distance_approach: "DA · Distance approach",
  S3_view_search: "VS · View search",
  S4_state_recognition: "SV · State verification",
  S4_state_verification: "SV · State verification",
  T1_grounded_interaction: "AI · Approach and interact",
  T2_search_then_interact: "SI · Search and interact",
  T3_sequential_manipulation: "SM · Sequential manipulation",
  T4_constraint_resolving: "CR · Constraint resolving",
};
const text = (id, value) => {
  $(id).textContent = value ?? "";
};
const element = (tag, value, cls) => {
  const el = document.createElement(tag);
  if (value != null) el.textContent = value;
  if (cls) el.className = cls;
  return el;
};
const pretty = (value) =>
  typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2);
const percent = (value) =>
  typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "—";
function notice(message, success = false) {
  text("notice", message);
  $("notice").hidden = false;
  $("notice").className = `notice${success ? " success" : ""}`;
}
async function api(path, body) {
  const response = await fetch(
    path,
    body === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Vigil-Token": state.token,
          },
          body: JSON.stringify(body),
        },
  );
  const data = await response.json();
  if (!response.ok)
    throw Error(data.error || `Request failed (${response.status})`);
  return data;
}
async function perform(button, action) {
  const old = button.textContent;
  button.disabled = true;
  button.dataset.busy = "true";
  try {
    await action();
  } catch (error) {
    notice(error.message);
  } finally {
    button.disabled = false;
    button.textContent = old;
    delete button.dataset.busy;
    updateSelection();
  }
}
function route() {
  const page = location.hash.slice(1).split("/")[0] || "overview";
  const known = ["overview", "evaluate", "results"].includes(page)
    ? page
    : "overview";
  document
    .querySelectorAll(".page")
    .forEach((p) => (p.hidden = p.id !== `page-${known}`));
  document.querySelectorAll("nav a").forEach((a) => {
    a.classList.toggle("active", a.dataset.page === known);
    if (a.dataset.page === known) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  text(
    "page-title",
    {
      overview: "Overview",
      evaluate: "Run an evaluation",
      results: "Results & replay",
    }[known],
  );
  if (state.view !== known) {
    state.view = known;
    window.scrollTo(0, 0);
  }
  if (known === "results") refreshRuns().catch((e) => notice(e.message));
}
function loadConfig(c) {
  $("backend").value =
    c.backend === "vllm"
      ? "openai-compatible"
      : c.backend === "claude"
        ? "anthropic"
        : c.backend || "openai-compatible";
  $("model").value = c.model || "";
  $("base-url").value = c.base_url || "";
  $("api-key").value = "";
  $("clear-key").checked = false;
  $("api-key-header").value = c.api_key_header || "Authorization";
  $("timeout").value = c.timeout ?? 120;
  $("max-tokens").value = c.max_tokens ?? 4096;
  $("temperature").value = c.temperature === null ? "" : (c.temperature ?? 0.6);
  $("top-p").value = c.top_p === null ? "" : (c.top_p ?? 0.9);
  $("top-k").value = c.top_k ?? "";
  $("coord-mode").value = c.coord_mode || "";
  $("json-mode").value = c.supports_json_mode === false ? "0" : "1";
  $("extra-body").value = pretty(
    c.extra_body || c.request_extra_body_json || {},
  );
  text(
    "key-hint",
    c.key_configured
      ? "A key is configured. Leave this field blank to keep it."
      : "Leave blank for an unauthenticated server or an environment key.",
  );
  text("config-state", c.model ? `Saved · ${c.model}` : "Not configured");
  state.dirty = false;
  updateUrlHint();
}
function updateUrlHint() {
  text(
    "url-hint",
    ["gemini", "anthropic", "openai"].includes($("backend").value)
      ? "Leave blank for the official API, or enter your gateway's full endpoint."
      : "A server root, /v1, or full endpoint URL.",
  );
}
function modelValues() {
  const optional = (id) =>
    $(id).value.trim() === "" ? null : Number($(id).value);
  const extra = JSON.parse($("extra-body").value || "{}");
  if (!extra || Array.isArray(extra) || typeof extra !== "object")
    throw Error("Provider options must be a JSON object.");
  return {
    backend: $("backend").value,
    model: $("model").value.trim(),
    base_url: $("base-url").value.trim(),
    api_key: $("api-key").value,
    clear_api_key: $("clear-key").checked,
    api_key_header: $("api-key-header").value.trim() || "Authorization",
    timeout: Number($("timeout").value),
    max_tokens: Number($("max-tokens").value),
    temperature: optional("temperature"),
    top_p: optional("top-p"),
    top_k: optional("top-k"),
    coord_mode: $("coord-mode").value,
    coord_prompt_mode: $("coord-mode").value ? "explicit" : "",
    supports_json_mode: $("json-mode").value === "1",
    extra_body: extra,
  };
}
function filteredTasks() {
  const query = $("task-search").value.toLowerCase().trim();
  return state.episodes.filter(
    (e) =>
      (!$("family-filter").value ||
        e.task_family === $("family-filter").value) &&
      (!$("difficulty-filter").value ||
        e.difficulty === $("difficulty-filter").value) &&
      (!query ||
        `${e.instruction} ${e.episode_id} ${e.scene}`
          .toLowerCase()
          .includes(query)),
  );
}
function renderTasks() {
  const rows = filteredTasks(),
    size = 15;
  state.page = Math.min(
    state.page,
    Math.max(0, Math.ceil(rows.length / size) - 1),
  );
  $("task-rows").replaceChildren();
  for (const row of rows.slice(state.page * size, (state.page + 1) * size)) {
    const tr = element("tr"),
      select = element("td"),
      box = element("input");
    box.type = "checkbox";
    box.checked = state.selected.has(row.episode_id);
    box.setAttribute("aria-label", `Select ${row.episode_id}`);
    box.addEventListener("change", () => {
      box.checked
        ? state.selected.add(row.episode_id)
        : state.selected.delete(row.episode_id);
      updateSelection();
    });
    select.append(box);
    const task = element("td");
    task.append(
      element(
        "span",
        labels[row.task_family] || row.task_family,
        "task-family",
      ),
      element("p", row.instruction),
    );
    const scene = element("td");
    scene.append(
      element("span", row.scene),
      element("p", `${row.platform} · ${row.difficulty}`),
    );
    tr.append(select, task, scene, element("td", `${row.max_steps} steps`));
    $("task-rows").append(tr);
  }
  if (!rows.length) {
    const tr = element("tr"),
      td = element("td", "No matching tasks.", "empty");
    td.colSpan = 4;
    tr.append(td);
    $("task-rows").append(tr);
  }
  text(
    "page-count",
    rows.length
      ? `${state.page * size + 1}–${Math.min((state.page + 1) * size, rows.length)} of ${rows.length} tasks`
      : "0 tasks",
  );
  $("previous-page").disabled = state.page === 0;
  $("next-page").disabled = (state.page + 1) * size >= rows.length;
  updateSelection();
}
function updateSelection() {
  const n = state.selected.size;
  text("selection-count", `${n} selected`);
  text(
    "launch-run",
    `Run ${n || "selected"} ${n === 1 ? "episode" : "episodes"} →`,
  );
  const active = state.runs.some((r) => r.can_stop);
  $("launch-run").disabled =
    !n || active || $("launch-run").dataset.busy === "true";
  $("model-form")
    .querySelectorAll("input, select, textarea, button")
    .forEach((control) => {
      control.disabled = active || control.dataset.busy === "true";
    });
  text(
    "run-hint",
    `${n} real ${n === 1 ? "episode" : "episodes"} · uses your model API and local simulator.`,
  );
}
async function refreshRuns() {
  const runs = await api("/api/runs");
  state.runs = runs;
  const chosen = state.run || $("run-select").value;
  $("run-select").replaceChildren();
  for (const r of [...runs].sort((a, b) =>
    a.demo ? 1 : b.demo ? -1 : b.name.localeCompare(a.name),
  )) {
    const option = element(
      "option",
      `${r.demo ? "Recorded example" : r.name} — ${r.model || "model"} · ${r.completed}/${r.total}`,
    );
    option.value = r.id;
    $("run-select").append(option);
  }
  state.run = runs.some((r) => r.id === chosen)
    ? chosen
    : (
        runs.find((r) => !r.demo && r.state !== "invalid") ||
        runs.find((r) => r.demo)
      )?.id;
  $("run-empty").hidden = !!state.run;
  $("run-detail").hidden = !state.run;
  if (state.run) {
    $("run-select").value = state.run;
    await renderRun();
  }
  updateSelection();
}
async function renderRun() {
  const id = state.run;
  if (!id) return;
  if (state.currentRun?.id !== id) {
    state.currentRun = null;
    text("run-name", "Loading evaluation…");
    for (const field of ["run-model", "run-state", "metric-total"])
      text(field, "");
    for (const field of [
      "metric-world",
      "metric-benchmark",
      "metric-completed",
    ])
      text(field, "—");
    $("result-rows").replaceChildren();
    $("download-results").hidden = true;
    $("verification-state").hidden = true;
    $("stop-run").hidden = true;
    $("run-warning").hidden = true;
    $("run-progress").value = 0;
  }
  const r = await api(`/api/runs/${id}`);
  if (id !== state.run) return;
  state.currentRun = r;
  text("run-name", r.name);
  text(
    "run-model",
    r.recording
      ? `${r.model} · ${r.recording.feedback === "none" ? "No action feedback" : "Action-feedback intervention"}`
      : r.demo ? `${r.model} · saved observations and results` : r.model,
  );
  text("run-state", r.demo ? "Recorded example" : r.state.replaceAll("_", " "));
  $("run-state").className =
    `badge ${r.state === "complete" ? "good" : ["failed", "infrastructure_error", "cancelled"].includes(r.state) ? "bad" : ""}`;
  $("stop-run").hidden = !r.can_stop;
  $("download-results").hidden = !r.metrics;
  $("verification-state").hidden = !r.metrics;
  $("verification-state").className = "badge good";
  $("download-results").href = `/api/runs/${id}/download`;
  text("metric-completed", r.completed);
  text("metric-total", `of ${r.total} selected episodes`);
  text("metric-world", percent(r.metrics?.world_success_rate));
  text("metric-benchmark", percent(r.metrics?.success_rate));
  $("run-progress").max = r.total || 1;
  $("run-progress").value = r.completed;
  $("run-warning").hidden = !r.demo && !r.recording && !!r.metrics;
  text(
    "run-warning",
    r.verification_error
      ? `Evidence check failed: ${r.verification_error} Final metrics are withheld.`
      : r.recording && r.metrics
        ? `${r.recording.scope} Profile: ${r.recording.profile}.`
      : r.demo
        ? "Recorded example: 2 real episodes for exploring the interface. These are sample results, not a full benchmark evaluation."
        : r.state === "running"
          ? "Evaluation in progress. Final W/B metrics appear when all selected tasks finish."
          : "This run is incomplete or has infrastructure errors. Final metrics are withheld; inspect the log and episode traces.",
  );
  $("result-rows").replaceChildren();
  for (const e of r.episodes) {
    const tr = element("tr"),
      task = element("td");
    task.append(
      element("span", labels[e.task_family] || e.task_family, "task-family"),
      element("p", e.instruction || e.episode_id),
    );
    const outcome = element("td");
    outcome.append(
      element(
        "span",
        e.state,
        "badge " +
          (e.state === "success" ? "good" : e.state === "failure" ? "bad" : ""),
      ),
    );
    if (e.reason) outcome.append(element("p", e.reason.replaceAll("_", " ")));
    const action = element("td"),
      button = element(
        "button",
        e.has_trace ? "Replay →" : e.latest_frame ? "Live view →" : "Waiting",
        "button small-button",
      );
    button.disabled = !e.has_trace && !e.latest_frame;
    button.addEventListener("click", () =>
      openReplay(e.episode_id).catch((error) => notice(error.message)),
    );
    action.append(button);
    const bit = (v) => (v === true ? "✓" : v === false ? "✕" : "—");
    tr.append(
      task,
      outcome,
      element("td", `${bit(e.world_success)} / ${bit(e.success)}`),
      element("td", e.steps),
      action,
    );
    $("result-rows").append(tr);
  }
  if ($("log-details").open) await loadLogs();
  if ($("replay").open && state.replay?.live && state.replayRun === id)
    await refreshLiveReplay();
}
async function loadLogs() {
  if (state.run) {
    const data = await api(`/api/runs/${state.run}/logs`);
    text("run-log", data.text || "No process log for this recorded result.");
  }
}
async function openReplay(episode, run = state.run) {
  stopPlayback();
  state.replayRun = run;
  state.replay = await api(
    `/api/runs/${run}/episodes/${encodeURIComponent(episode)}`,
  );
  state.step = 0;
  text(
    "replay-title",
    labels[state.replay.episode.task_family] || "Episode replay",
  );
  text("replay-instruction", state.replay.episode.instruction || episode);
  $("step-list").replaceChildren();
  state.replay.steps.forEach((s, i) => {
    const button = element(
      "button",
      `${i + 1} · ${s.action?.skill_name || "response"}`,
    );
    button.addEventListener("click", () => {
      stopPlayback();
      state.step = i;
      renderStep();
    });
    $("step-list").append(button);
  });
  $("step-slider").max = Math.max(0, state.replay.steps.length - 1);
  renderStep();
  if (!$("replay").open) $("replay").showModal();
}
async function refreshLiveReplay() {
  const e = state.replay.episode.episode_id;
  const result = await api(
    `/api/runs/${state.replayRun}/episodes/${encodeURIComponent(e)}`,
  );
  if (!result.live) {
    await openReplay(e, state.replayRun);
    return;
  }
  state.replay = result;
  renderStep();
}
function renderStep() {
  const replay = state.replay;
  if (!replay) return;
  const s = replay.steps[state.step];
  const frame = s?.frame || (!s ? replay.episode.latest_frame : null);
  $("replay-frame").hidden = !frame;
  $("no-frame").hidden = !!frame;
  if (frame && $("replay-frame").getAttribute("src") !== frame)
    $("replay-frame").src = frame;
  const live = replay.live;
  $("pixel-marker").hidden = true;
  text(
    "replay-kicker",
    live
      ? "LIVE RGB · ACTIONS APPEAR AFTER THE EPISODE"
      : "RECORDED RGB · STEP-BY-STEP REPLAY",
  );
  text("model-action", s ? pretty(s.action) : "Waiting for the episode trace…");
  text("executed-action", s ? pretty(s.executed) : "—");
  text(
    "step-result",
    s
      ? `${s.environment}${s.error ? ` · ${s.error.replaceAll("_", " ")}` : ""}`
      : "The current frame is shown while the model is running.",
  );
  text(
    "step-world",
    s
      ? `World goal at this step: ${s.world_success ? "reached" : "not reached"}`
      : "",
  );
  text("model-response", pretty(s?.response || "No response recorded."));
  text("model-reasoning", s?.reasoning || "");
  text("step-judge", pretty(s?.judge));
  text(
    "step-label",
    live
      ? `Frame ${replay.episode.frame_count}`
      : `${state.step + 1} / ${replay.steps.length}`,
  );
  $("step-slider").value = state.step;
  $("step-slider").disabled = live;
  $("prev-step").disabled = live || state.step === 0;
  $("next-step").disabled = live || state.step >= replay.steps.length - 1;
  $("play-steps").disabled = live || replay.steps.length < 2;
  [...$("step-list").children].forEach((b, i) =>
    b.classList.toggle("active", i === state.step),
  );
  updateMarker();
}
function updateMarker() {
  const s = state.replay?.steps[state.step],
    img = $("replay-frame"),
    marker = $("pixel-marker");
  marker.hidden = true;
  if (
    s?.action?.skill_name === "interact_pixel" &&
    Number.isFinite(s.executed?.x) &&
    Number.isFinite(s.executed?.y) &&
    img.naturalWidth &&
    s.frame
  ) {
    const scale = Math.min(
      img.clientWidth / img.naturalWidth,
      img.clientHeight / img.naturalHeight,
    );
    marker.style.left = `${(img.clientWidth - img.naturalWidth * scale) / 2 + s.executed.x * scale}px`;
    marker.style.top = `${(img.clientHeight - img.naturalHeight * scale) / 2 + s.executed.y * scale}px`;
    marker.hidden = false;
  }
}
function stopPlayback() {
  if (state.timer) clearInterval(state.timer);
  state.timer = null;
  text("play-steps", "▶ Play");
}
function renderRecordedCases(cases) {
  $("recorded-cases").hidden = !cases.length;
  $("recorded-case-list").replaceChildren();
  for (const item of cases) {
    const card = element("article", null, "workflow-card recorded-case");
    card.append(element("span", `${item.family} · ${item.model}`, "eyebrow"));
    card.append(element("h3", item.instruction));
    card.append(element("p", `${item.steps} ${item.steps === 1 ? "action" : "actions"} · W ${Number(item.world_success)} / B ${Number(item.benchmark_success)} · ${item.feedback === "none" ? "No action feedback" : "Action-feedback intervention"}`));
    const button = element("button", "Replay trajectory →", "card-action");
    button.addEventListener("click", async () => {
      try {
        state.run = item.run_id;
        location.hash = "results";
        await refreshRuns();
        await openReplay(item.episode_id, item.run_id);
      } catch (e) { notice(e.message); }
    });
    card.append(button);
    $("recorded-case-list").append(card);
  }
}

async function showDemo(replay = false) {
  state.run = "demo";
  location.hash = "results";
  await refreshRuns();
  if (replay) {
    const success =
      state.currentRun?.episodes.find((e) => e.success) ||
      state.currentRun?.episodes[0];
    if (success) await openReplay(success.episode_id, "demo");
  }
}

$("model-form").addEventListener("input", () => {
  state.dirty = true;
  text("config-state", "Unsaved changes");
});
$("backend").addEventListener("change", () => {
  $("base-url").value = "";
  $("api-key-header").value = "Authorization";
  updateUrlHint();
});
$("model-form").addEventListener("submit", (e) => {
  e.preventDefault();
  perform(e.submitter, async () => {
    const config = await api("/api/config", modelValues());
    loadConfig(config);
    state.readiness.model_configured = true;
    renderReadiness();
    notice(
      "Model configuration saved. Select a task below to run a real evaluation.",
      true,
    );
  });
});
$("check-setup").addEventListener("click", (e) => check(e.target, false));
$("check-model").addEventListener("click", (e) => check(e.target, true));
async function check(button, model) {
  await perform(button, async () => {
    if (state.dirty)
      throw Error("Save your model settings before checking them.");
    button.textContent = model ? "Testing…" : "Checking…";
    const result = await api("/api/checks", { model_request: model });
    $("checks").replaceChildren();
    for (const c of result.checks) {
      const row = element("div", null, "check");
      row.append(
        element(
          "span",
          `${c.status === "ok" ? "✓" : c.status === "error" ? "!" : "·"} ${c.check.replaceAll("_", " ")}`,
          c.status,
        ),
        element("span", c.message),
      );
      $("checks").append(row);
    }
  });
}
for (const id of ["task-search", "family-filter", "difficulty-filter"])
  $(id).addEventListener("input", () => {
    state.page = 0;
    renderTasks();
  });
$("select-filtered").addEventListener("click", () => {
  filteredTasks().forEach((e) => state.selected.add(e.episode_id));
  renderTasks();
});
$("clear-selection").addEventListener("click", () => {
  state.selected.clear();
  renderTasks();
});
$("previous-page").addEventListener("click", () => {
  state.page--;
  renderTasks();
});
$("next-page").addEventListener("click", () => {
  state.page++;
  renderTasks();
});
$("launch-run").addEventListener("click", (e) =>
  perform(e.target, async () => {
    if (state.dirty)
      throw Error("Save your model settings before starting an evaluation.");
    const result = await api("/api/runs", {
      episode_ids: [...state.selected],
      workers: Number($("workers").value),
      boot_concurrency: Number($("boot-concurrency").value),
      render_concurrency: Number($("render-concurrency").value),
    });
    state.run = result.id;
    location.hash = "results";
    notice(
      "Evaluation started. You can follow progress and stop this run here.",
      true,
    );
    await refreshRuns();
  }),
);
$("refresh-runs").addEventListener("click", (e) =>
  perform(e.target, refreshRuns),
);
$("run-select").addEventListener("change", () => {
  state.run = $("run-select").value;
  renderRun().catch((e) => notice(e.message));
});
$("stop-run").addEventListener("click", (e) =>
  perform(e.target, async () => {
    await api(`/api/runs/${state.run}/stop`, {});
    await refreshRuns();
    notice("Run stopped. Completed episode files are preserved.", true);
  }),
);
$("log-details").addEventListener("toggle", () => {
  if ($("log-details").open) loadLogs().catch((e) => notice(e.message));
});
$("explore-demo").addEventListener("click", () =>
  showDemo().catch((e) => notice(e.message)),
);
for (const id of ["demo-image-button", "demo-replay"])
  $(id).addEventListener("click", () =>
    showDemo(true).catch((e) => notice(e.message)),
  );
$("close-replay").addEventListener("click", () => $("replay").close());
$("replay").addEventListener("close", stopPlayback);
$("replay-frame").addEventListener("load", updateMarker);
$("demo-image").addEventListener("load", () => {
  $("demo-image").hidden = false;
  $("demo-placeholder").hidden = true;
});
$("prev-step").addEventListener("click", () => {
  stopPlayback();
  state.step = Math.max(0, state.step - 1);
  renderStep();
});
$("next-step").addEventListener("click", () => {
  stopPlayback();
  state.step = Math.min(state.replay.steps.length - 1, state.step + 1);
  renderStep();
});
$("step-slider").addEventListener("input", () => {
  stopPlayback();
  state.step = Number($("step-slider").value);
  renderStep();
});
$("play-steps").addEventListener("click", () => {
  if (state.timer) {
    stopPlayback();
    return;
  }
  if (state.step === state.replay.steps.length - 1) state.step = 0;
  text("play-steps", "Ⅱ Pause");
  renderStep();
  state.timer = setInterval(() => {
    if (state.step >= state.replay.steps.length - 1) {
      stopPlayback();
      return;
    }
    state.step++;
    renderStep();
  }, 1200);
});
window.addEventListener("hashchange", route);
window.addEventListener("resize", updateMarker);
function renderConcurrency() {
  const workers = Number($("workers").value);
  const render = Number($("render-concurrency").value) || Math.min(4, workers);
  const boot = Number($("boot-concurrency").value) || Math.min(8, workers);
  const active = Math.min(workers, render);
  text("concurrency-summary", `Up to ${active} active episodes and model requests, with up to ${Math.min(active, boot)} simulators starting together. Fewer selected tasks reduce these limits.`);
}
for (const id of ["workers", "boot-concurrency", "render-concurrency"])
  $(id).addEventListener("input", renderConcurrency);
async function initialize() {
  const data = await api("/api/bootstrap");
  state.token = data.token;
  state.episodes = data.episodes;
  state.runs = data.runs;
  state.readiness = data.readiness || {};
  renderRecordedCases(data.recordings || []);
  text("output-location", `New evaluations are saved in ${data.out_dir || "outputs"}.`);
  renderReadiness();
  renderConcurrency();
  loadConfig(data.config);
  text(
    "task-count",
    data.episodes.length ? data.episodes.length.toLocaleString() : "1,000",
  );
  if (data.config_error) notice(data.config_error);
  if (data.data_error) {
    $("data-warning").hidden = false;
    text(
      "data-warning",
      `${data.data_error} You can still explore the recorded example.`,
    );
  }
  for (const key of ["task_family", "difficulty"]) {
    const id = key === "task_family" ? "family-filter" : "difficulty-filter";
    for (const value of [...new Set(data.episodes.map((e) => e[key]))].sort()) {
      const o = element("option", labels[value] || value);
      o.value = value;
      $(id).append(o);
    }
  }
  if (data.episodes.length) state.selected.add(data.episodes[0].episode_id);
  renderTasks();
  const demo = await api("/api/runs/demo");
  text(
    "demo-outcome-label",
    demo.metrics ? "Goal verified" : "Recorded episode",
  );
  const example = demo.episodes.find((e) => e.success) || demo.episodes[0];
  if (example) {
    const replay = await api(`/api/runs/demo/episodes/${example.episode_id}`);
    const frame = replay.steps.find((s) => s.frame)?.frame;
    if (frame) $("demo-image").src = frame;
  }
  route();
  setInterval(async () => {
    if (
      state.polling ||
      $("page-results").hidden ||
      (!state.runs.some((r) => r.can_stop) &&
        state.currentRun?.state !== "running")
    )
      return;
    state.polling = true;
    try {
      await refreshRuns();
    } catch (e) {
      notice(e.message);
    } finally {
      state.polling = false;
    }
  }, 3000);
}
initialize().catch((e) => notice(`Could not load the workbench: ${e.message}`));

function renderReadiness() {
  text(
    "model-readiness",
    state.readiness.model_configured ? "Model configured" : "Connect an API",
  );
  $("model-readiness").className =
    `badge${state.readiness.model_configured ? " good" : ""}`;
  text(
    "runtime-readiness",
    state.readiness.simulator_installed
      ? "Simulator installed"
      : "Simulator needed",
  );
  text(
    "runtime-guidance",
    state.readiness.simulator_installed
      ? "The simulator package is installed. Check rendering, then run one episode before scaling up."
      : "Explore recorded results now. Install the simulator when you're ready to evaluate your model.",
  );
  $("setup-guidance").hidden = !!state.readiness.simulator_installed;
  $("setup-guidance").replaceChildren(
    element("strong", "Ready to replay. One more step to run."),
    element(
      "p",
      "Install the simulator in this Python environment, then restart the workbench. Real episodes also need a compatible rendering host.",
    ),
    element(
      "code",
      state.readiness.install_command || 'python -m pip install -e ".[thor]"',
    ),
  );
}
