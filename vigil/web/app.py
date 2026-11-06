from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.util import find_spec
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
from urllib.parse import unquote, urlsplit
import webbrowser

from vigil.agent.backends import ModelBackendConfig
from vigil.data.episodes import EpisodeSpec
from vigil.config import MODEL_ARGUMENTS, apply_config_values
from vigil.data.paths import CANONICAL_PACK, data_root
from vigil.paths import PACKAGE_ROOT, source_root
from vigil.eval.state import atomic_json
from vigil.eval.inspection import selected_episode_ids, verify_run

ASSETS = Path(__file__).parent


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def contained(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Path is outside the selected results directory.")
    return resolved


def run_object(root: Path, name: str, default=None) -> dict:
    path = contained(root, root / name)
    if not path.exists() and default is not None:
        return default
    value = read_json(path)
    if not isinstance(value, dict):
        raise ValueError(f"Invalid or missing run JSON object: {name}")
    return value


def run_ids(path: Path) -> list[str]:
    status = run_object(path, "run_status.json", {})
    if "episode_ids" not in status:
        status = run_object(path, "ui_run.json", {})
    return selected_episode_ids(status)


def simulator_install_command() -> str:
    release = source_root()
    packages = ["-e", f"{release}[thor]"] if release is not None else ["ai2thor>=5.0"]
    return shlex.join([sys.executable, "-m", "pip", "install", *packages])


def resolve_model(values: dict) -> ModelBackendConfig:
    args = argparse.Namespace()
    apply_config_values(args, values)
    return ModelBackendConfig.from_env(**{field: getattr(args, name) for name, field in MODEL_ARGUMENTS.items() if hasattr(args, name)})


def private_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False, encoding="utf-8") as handle:
        temporary = Path(handle.name)
        try:
            os.chmod(temporary, 0o600)
            json.dump(value, handle, indent=2)
            handle.write("\n")
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


class Workbench:
    def __init__(self, *, config: Path, results: Path, demo: Path | None = None,
                 out_dir: Path = Path("outputs"), recordings: Path | None = None):
        self.config_path = config.expanduser().resolve()
        self.results = results.expanduser().resolve()
        self.out_dir = out_dir.expanduser().resolve()
        self.recordings = recordings.resolve() if recordings else None
        self.read_roots = {self.results, self.out_dir}
        if self.recordings:
            self.read_roots.add(self.recordings)
        self.demo = (demo or ASSETS / "demo").resolve()
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.process = None
        self.active_id = None
        self.cancelled_ids = set()
        self.runs = {}
        self.verifications = {}
        self.data_error = None
        self.catalog = []
        self.pack = {}
        self.data = None
        try:
            self.data = data_root()
            self.pack = json.loads((self.data / "benchmark" / "packs" / CANONICAL_PACK).read_text())
            for row in self.pack["episodes"]:
                episode = EpisodeSpec.from_path(self.data / "episodes" / row["episode_id"] / "episode.json")
                self.catalog.append({"episode_id": episode.episode_id, "task_family": episode.task_family,
                                     "instruction": episode.instruction, "scene": row.get("scene_id") or episode.scene_id,
                                     "platform": episode.scene.get("platform", ""), "max_steps": episode.max_steps,
                                     "difficulty": row.get("difficulty") or row.get("aux_difficulty") or "unspecified"})
        except (OSError, ValueError, KeyError) as exc:
            self.data_error = str(exc)
            self.catalog = []
        self.episodes = {row["episode_id"]: row for row in self.catalog}
        self.demo_episodes = read_json(self.demo / "episodes.json", {})

    def config_values(self):
        if not self.config_path.exists():
            return {"backend": "openai-compatible", "model": "", "base_url": "", "api_key": ""}
        values = read_json(self.config_path)
        if not isinstance(values, dict):
            raise ValueError(f"Invalid configuration file: {self.config_path.name}. Fix its JSON before saving.")
        return values

    def redact(self, value):
        from vigil.security import credential_values, redact
        values = read_json(self.config_path, {})
        keys = list(credential_values(values))
        keys += [os.getenv(name, "") for name in ("VIGIL_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY")]
        return redact(value, keys)

    def public_config(self):
        values = self.config_values()
        public = {k: v for k, v in values.items() if k != "api_key"}
        try:
            config = resolve_model(values)
            public["key_configured"] = bool(config.api_key)
        except ValueError:
            public["key_configured"] = bool(values.get("api_key"))
        return self.redact(public)

    def readiness(self):
        try:
            resolve_model(self.config_values())
            configured = True
        except ValueError:
            configured = False
        return {"simulator_installed": find_spec("ai2thor") is not None,
                "data_available": not self.data_error, "model_configured": configured,
                "install_command": simulator_install_command()}

    def save_config(self, updates):
        with self.lock:
            if self.process and self.process.poll() is None:
                raise ValueError("Wait for the current run to finish or stop it before changing the model.")
            updates = dict(updates)
            clear = updates.pop("clear_api_key", False)
            current = self.config_values()
            if not updates.get("api_key") and not clear:
                updates.pop("api_key", None)
            if clear:
                updates["api_key"] = ""
            candidate = {**current, **updates}
            if "extra_body" in updates:
                candidate.pop("request_extra_body_json", None)
            resolve_model(candidate)
            private_json(self.config_path, candidate)
            return self.public_config()

    def discover_runs(self):
        candidates = [self.demo]
        for root in self.read_roots:
            if root.exists():
                candidates += [p.parent for pattern in ("run_status.json", "ui_run.json")
                               for p in root.rglob(pattern) if p.resolve().is_relative_to(root)]
        with self.lock:
            discovered = {}
            for path in candidates:
                if path == self.demo or any(path.resolve().is_relative_to(root) for root in self.read_roots):
                    run_id = "demo" if path == self.demo else hashlib.sha256(str(path.resolve()).encode()).hexdigest()[:16]
                    discovered[run_id] = path.resolve()
            self.runs = discovered
            summaries = []
            for run_id, path in self.runs.items():
                try:
                    summaries.append(self.run_summary(run_id))
                except (ValueError, OSError, TypeError, KeyError) as exc:
                    summaries.append({"id": run_id, "name": path.name, "demo": run_id == "demo",
                                      "state": "invalid", "model": "", "total": 0, "completed": 0,
                                      "can_stop": False, "error": str(exc)})
            return self.redact(summaries)

    def run_path(self, run_id):
        if run_id not in self.runs:
            self.discover_runs()
        if run_id not in self.runs:
            raise ValueError("Run not found. Use --results-dir to open another results folder.")
        path = self.runs[run_id].resolve()
        if run_id != "demo" and not any(path.is_relative_to(root) for root in self.read_roots):
            raise ValueError("Run is outside the selected results directory.")
        return path

    def recorded_cases(self):
        if not self.recordings:
            return []
        catalog = read_json(self.recordings / "catalog.json", {})
        return [{**case, "run_id": run_id} for case in catalog.get("cases", [])
                for run_id, path in self.runs.items()
                if path == self.recordings / case.get("id", "")]

    def run_summary(self, run_id):
        path = self.run_path(run_id)
        status = run_object(path, "run_status.json", {})
        ui = run_object(path, "ui_run.json", {})
        ids = run_ids(path)
        live = run_id == self.active_id and self.process is not None and self.process.poll() is None
        state = "running" if live else status.get("state", ui.get("state", "incomplete"))
        if state not in {"running", "complete", "infrastructure_error", "cancelled", "failed", "interrupted", "incomplete"}:
            raise ValueError("Invalid run completion state.")
        if not live and ui.get("state") in {"cancelled", "failed"}:
            state = ui["state"]
        elif not live and ui and state == "running":
            state = "interrupted"
        model = run_object(path, "model_config.json", {}).get("model", ui.get("model", ""))
        complete = sum(contained(path, path / "scores" / f"{episode}.score.json").is_file() for episode in ids)
        return {"id": run_id, "name": "Recorded example" if run_id == "demo" else path.name,
                "demo": run_id == "demo", "state": state, "model": model,
                "total": len(ids), "completed": complete, "can_stop": live,
                "started_at": ui.get("started_at", ""), "path": str(path) if run_id != "demo" else "Bundled example"}

    def verified_metrics(self, path, ids):
        """Cache successful audits only while all evidence files remain unchanged."""
        files = [path / name for name in ("run_status.json", "aggregate_score.json")]
        files += [path / folder / f"{episode}{suffix}" for episode in ids
                  for folder, suffix in (("traces", ".json"), ("scores", ".score.json"))]
        signature = []
        for file in files:
            safe = contained(path, file)
            stat = safe.stat()
            signature.append((str(safe), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))
        signature = tuple(signature)
        if self.verifications.get(path) != signature:
            verify_run(path)
            self.verifications[path] = signature
        return run_object(path, "aggregate_score.json")

    def episode_row(self, path, run_id, episode):
        score = run_object(path, f"scores/{episode}.score.json", {})
        settlement = score.get("settlement", {})
        if not isinstance(settlement, dict):
            raise ValueError(f"Invalid settlement in score for {episode}.")
        frame_dir = contained(path, path / "frames" / episode)
        frames = sorted(frame_dir.glob("step_*.png"))
        trace = contained(path, path / "traces" / f"{episode}.json")
        info = self.episodes.get(episode) or self.demo_episodes.get(episode, {})
        return {**info, "episode_id": episode,
                "task_family": score.get("task_family", info.get("task_family", "")),
                "state": score.get("terminal_status", "running" if frames else "pending"),
                "world_success": settlement.get("world_success"), "success": score.get("success"),
                "steps": score.get("steps_used", len(frames)), "reason": score.get("terminal_reason", ""),
                "has_trace": trace.is_file(), "frame_count": len(frames),
                "latest_frame": f"/api/runs/{run_id}/frames/{episode}/{frames[-1].name}" if frames else None}

    def run_detail(self, run_id):
        path = self.run_path(run_id)
        result = self.run_summary(run_id)
        provenance = run_object(path, "provenance.json", {})
        result["recording"] = None
        if provenance.get("source_result_sha256"):
            profile = provenance.get("profile") or {}
            result["recording"] = {"scope": provenance.get("selection", "Selected historical recording."),
                                   "profile": profile.get("name", "unknown"),
                                   "feedback": profile.get("feedback_policy", "unknown")}
        ids = run_ids(path)
        result["episodes"] = [self.episode_row(path, run_id, episode) for episode in ids]
        # An old aggregate from an unfinished/resumed run must never appear as final.
        result["metrics"] = None
        result["verification_error"] = None
        if result["state"] == "complete":
            try:
                aggregate = self.verified_metrics(path, ids)
                result["metrics"] = {k: aggregate.get(k) for k in ("episode_count", "world_success_rate", "success_rate", "mean_steps_used", "diagnostic_rates", "by_task_family")}
            except (OSError, ValueError, TypeError, KeyError) as exc:
                result["verification_error"] = str(exc)
        return self.redact(result)

    def episode_trace(self, run_id, episode_id):
        path = self.run_path(run_id)
        if episode_id not in run_ids(path):
            raise ValueError("Episode is not part of this run.")
        row = self.episode_row(path, run_id, episode_id)
        trace = read_json(contained(path, path / "traces" / f"{episode_id}.json"))
        if not isinstance(trace, dict):
            return {"episode": row, "steps": [], "live": True}
        steps = []
        for step in trace.get("steps", []):
            meta = step.get("metadata", {})
            env = meta.get("env_result", {})
            agent = meta.get("agent_turn", {})
            index = step["step_index"]
            frame = contained(path, path / "frames" / episode_id / f"step_{index:03d}.png")
            steps.append({"index": index, "frame": f"/api/runs/{run_id}/frames/{episode_id}/{frame.name}" if frame.is_file() else None,
                          "action": step.get("action"), "executed": env.get("executed_arguments"),
                          "environment": step.get("env_status"), "error": step.get("error_type"),
                          "world_success": step.get("judge_success"), "progress": step.get("progress"),
                          "response": meta.get("raw_response", agent.get("raw_response", (meta.get("model_output") or {}).get("raw_text", ""))),
                          "reasoning": agent.get("reasoning") or agent.get("thought"),
                          "usage": agent.get("usage"), "judge": meta.get("judge_result", {})})
        return self.redact({"episode": row, "steps": steps, "live": False, "settlement": trace.get("metadata", {}).get("settlement")})

    def start_run(self, payload):
        with self.lock:
            if self.process and self.process.poll() is None:
                raise ValueError("A run is already active. Wait for it or stop it first.")
            if self.data_error or not self.catalog:
                raise ValueError(self.data_error or "Benchmark data is missing.")
            ids = payload.get("episode_ids")
            if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in self.episodes for i in ids):
                raise ValueError("Select at least one task from the canonical benchmark.")
            if len(set(ids)) != len(ids):
                raise ValueError("Task selection contains duplicates.")
            if find_spec("ai2thor") is None:
                raise ValueError(f"Install the simulator with {simulator_install_command()}, then restart the workbench.")
            workers = payload.get("workers", 1)
            if type(workers) is not int or not 1 <= workers <= 16:
                raise ValueError("Workers must be between 1 and 16. Start with 1.")
            limits = {}
            for name in ("boot_concurrency", "render_concurrency"):
                value = payload.get(name, 0)
                if type(value) is not int or not 0 <= value <= 16:
                    raise ValueError(f"{name} must be between 0 (auto) and 16.")
                limits[name] = value
            values = self.config_values()
            model = resolve_model(values)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
            path = self.out_dir / f"run-{stamp}-{secrets.token_hex(3)}"
            path.mkdir(parents=True)
            selected = set(ids)
            rows = [r for r in self.pack["episodes"] if r["episode_id"] in selected]
            ids = [r["episode_id"] for r in rows]
            selection = {k: v for k, v in self.pack.items() if k not in {"summary", "episodes"}}
            selection["episodes"] = rows
            atomic_json(path / "selection.json", selection)
            # Keep credentials outside both result artifacts and source exports.
            snapshot_dir = Path(tempfile.mkdtemp(prefix="vigil-ui-"))
            snapshot = snapshot_dir / "config.json"
            private_json(snapshot, values)
            run_id = hashlib.sha256(str(path).encode()).hexdigest()[:16]
            command = [sys.executable, "-u", "-m", "vigil.cli", "run", "--config", str(snapshot),
                       "--pack-file", str(path / "selection.json"), "--episode-root", str(self.data / "episodes"),
                       "--scene-root", str(self.data / "scenes"), "--out-dir", str(path), "--workers", str(workers)]
            for name, value in limits.items():
                command.extend(["--" + name.replace("_", "-"), str(value)])
            info = {"state": "running", "episode_ids": ids, "model": model.model,
                    "workers": workers, **limits,
                    "started_at": datetime.now(timezone.utc).isoformat()}
            atomic_json(path / "ui_run.json", info)
            log = (path / "run.log").open("w", encoding="utf-8")
            try:
                env = dict(os.environ)
                env["PYTHONPATH"] = str(PACKAGE_ROOT.parent) + os.pathsep + env.get("PYTHONPATH", "")
                self.process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True, env=env)
            except BaseException:
                log.close()
                snapshot.unlink(missing_ok=True)
                snapshot_dir.rmdir()
                atomic_json(path / "ui_run.json", {**info, "state": "failed"})
                raise
            self.runs[run_id] = path
            self.active_id = run_id
            process = self.process
            def monitor():
                code = process.wait()
                log.close()
                with self.lock:
                    final = "cancelled" if run_id in self.cancelled_ids else "complete" if code == 0 else "failed"
                    atomic_json(path / "ui_run.json", {**info, "state": final, "exit_code": code})
                    snapshot.unlink(missing_ok=True)
                    snapshot_dir.rmdir()
            threading.Thread(target=monitor, daemon=True).start()
            return {"id": run_id}

    def stop_run(self, run_id):
        with self.lock:
            if run_id != self.active_id or self.process is None or self.process.poll() is not None:
                raise ValueError("Only a run started by this workbench can be stopped here.")
            self.cancelled_ids.add(run_id)
            process = self.process
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        return {"stopped": True}

    def check(self, model_request=False):
        from vigil.diagnostics import check_environment
        args = argparse.Namespace(pack_file=(self.data / "benchmark" / "packs" / CANONICAL_PACK) if self.data else Path("missing"),
                                  episode_root=self.data / "episodes" if self.data else Path("missing"),
                                  scene_root=self.data / "scenes" if self.data else Path("missing"), out_dir=self.out_dir,
                                  check_model=model_request, check_simulator=False)
        return self.redact({"checks": check_environment(args, lambda _: resolve_model(self.config_values()))})

    def close(self):
        if self.active_id and self.process is not None and self.process.poll() is None:
            self.stop_run(self.active_id)


def make_server(app: Workbench, port: int = 8765):
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("UI port must be between 0 and 65535; use 0 for an available port.")
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_data(self, data, mime="application/json", status=200, filename=None):
            body = json.dumps(data, ensure_ascii=False).encode() if mime == "application/json" else data
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def handle_request(self, mutation=False):
            try:
                host = self.headers.get("Host", "")
                allowed = {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
                if host not in allowed:
                    self.send_data({"error": "Local access only."}, status=403)
                    return
                body = None
                if mutation:
                    origin = self.headers.get("Origin")
                    if (origin and origin not in {"http://" + h for h in allowed}) or not secrets.compare_digest(self.headers.get("X-Vigil-Token", ""), app.token):
                        self.send_data({"error": "Reload the workbench before making changes."}, status=403)
                        return
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 262144 or self.headers.get_content_type() != "application/json":
                        raise ValueError("Send a JSON object smaller than 256 KB.")
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict):
                        raise ValueError("Expected a JSON object.")
                route = [unquote(s) for s in urlsplit(self.path).path.strip("/").split("/")]
                if mutation:
                    if route == ["api", "config"]:
                        self.send_data(app.save_config(body))
                    elif route == ["api", "checks"]:
                        self.send_data(app.check(body.get("model_request") is True))
                    elif route == ["api", "runs"]:
                        self.send_data(app.start_run(body))
                    elif len(route) == 4 and route[:2] == ["api", "runs"] and route[3] == "stop":
                        self.send_data(app.stop_run(route[2]))
                    else:
                        self.send_data({"error": "Unknown action."}, status=404)
                    return
                if route == [""]:
                    self.send_data((ASSETS / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")
                elif len(route) == 2 and route[0] == "static" and route[1] in {"app.js", "style.css"}:
                    self.send_data((ASSETS / "static" / route[1]).read_bytes(), mimetypes.guess_type(route[1])[0])
                elif route == ["api", "bootstrap"]:
                    try:
                        config = app.public_config()
                        config_error = None
                    except ValueError as exc:
                        config, config_error = {}, str(exc)
                    self.send_data({"token": app.token, "config": config, "config_error": config_error,
                                    "data_error": app.data_error, "episodes": app.catalog, "runs": app.discover_runs(),
                                    "recordings": app.recorded_cases(), "out_dir": str(app.out_dir),
                                    "readiness": app.readiness()})
                elif route == ["api", "runs"]:
                    self.send_data(app.discover_runs())
                elif len(route) >= 3 and route[:2] == ["api", "runs"]:
                    run_id = route[2]
                    path = app.run_path(run_id)
                    if len(route) == 3:
                        self.send_data(app.run_detail(run_id))
                    elif len(route) == 5 and route[3] == "episodes":
                        self.send_data(app.episode_trace(run_id, route[4]))
                    elif len(route) == 6 and route[3] == "frames":
                        ids = run_ids(path)
                        if route[4] not in ids or not re.fullmatch(r"step_\d+\.png", route[5]):
                            raise ValueError("Frame not found.")
                        frame = contained(path, path / "frames" / route[4] / route[5])
                        self.send_data(frame.read_bytes(), "image/png")
                    elif len(route) == 4 and route[3] == "download":
                        if app.run_detail(run_id)["metrics"] is None:
                            raise ValueError("Final metrics are available only for a completed run.")
                        self.send_data(app.redact(read_json(contained(path, path / "aggregate_score.json"))), filename="aggregate_score.json")
                    elif len(route) == 4 and route[3] == "logs":
                        log = contained(path, path / "run.log")
                        text = ""
                        if log.is_file():
                            with log.open("rb") as handle:
                                handle.seek(max(0, log.stat().st_size - 16000))
                                text = handle.read().decode("utf-8", errors="replace")
                        self.send_data({"text": app.redact(text)})
                    else:
                        self.send_data({"error": "Not found."}, status=404)
                else:
                    self.send_data({"error": "Not found."}, status=404)
            except (ValueError, OSError, KeyError, TypeError) as exc:
                try:
                    message = app.redact(str(exc))
                except ValueError:
                    message = "Configuration could not be read. Check vigil.json."
                self.send_data({"error": message}, status=400)

        def do_GET(self):
            self.handle_request()

        def do_POST(self):
            self.handle_request(mutation=True)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(*, port=8765, config=Path("vigil.json"), results=Path("outputs"), out_dir=Path("outputs"), open_browser=True):
    release = source_root()
    recordings = release / "examples" / "recorded-runs" if release else None
    app = Workbench(config=config, results=results, out_dir=out_dir,
                    recordings=recordings if recordings and (recordings / "catalog.json").is_file() else None)
    try:
        server = make_server(app, port)
    except OSError as exc:
        raise ValueError(f"Cannot open UI port {port}. Use vigil ui --port 0 to choose an available port. ({exc.strerror})") from exc
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"VIGIL workbench: {url}\nBrowse the recorded example, or configure a model and start a run.\nNo model calls or simulations start until you request them. Ctrl+C closes the workbench.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        app.close()
        server.server_close()
    return 0
