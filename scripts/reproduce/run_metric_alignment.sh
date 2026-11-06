#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: scripts/reproduce/run_metric_alignment.sh --reference-path PATH --expected-aggregate FILE [options]

Options:
  --reference-path PATH       Directory, trace/result JSON, or aggregate JSON with results. Repeatable.
  --expected-aggregate FILE   Reference aggregate_score.json to compare against.
  --actual-out FILE           New output file (must not exist). Default: outputs/metric-alignment/release_rescore.json
  --pack-file FILE           Require exact episode coverage. Default: frozen paper selection.
  --tolerance FLOAT           Absolute tolerance for numeric comparison. Default: 1e-9
  -h, --help                  Show this help.
USAGE
}

reference_paths=()
expected_aggregate=""
actual_out="outputs/metric-alignment/release_rescore.json"
tolerance="1e-9"
pack_file=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --reference-path)
      [[ $# -ge 2 ]] || { echo "missing value for --reference-path" >&2; exit 2; }
      reference_paths+=("$2")
      shift 2
      ;;
    --expected-aggregate)
      [[ $# -ge 2 ]] || { echo "missing value for --expected-aggregate" >&2; exit 2; }
      expected_aggregate="$2"
      shift 2
      ;;
    --actual-out)
      [[ $# -ge 2 ]] || { echo "missing value for --actual-out" >&2; exit 2; }
      actual_out="$2"
      shift 2
      ;;
    --pack-file)
      [[ $# -ge 2 ]] || { echo "missing value for --pack-file" >&2; exit 2; }
      pack_file="$2"
      shift 2
      ;;
    --tolerance)
      [[ $# -ge 2 ]] || { echo "missing value for --tolerance" >&2; exit 2; }
      tolerance="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ${#reference_paths[@]} -eq 0 ]]; then
  echo "at least one --reference-path is required" >&2
  usage >&2
  exit 2
fi
if [[ -z "$expected_aggregate" ]]; then
  echo "--expected-aggregate is required" >&2
  usage >&2
  exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"

pack_file="${pack_file:-$repo_root/data/reproduction/paper_v4_pack.json}"

python - "$actual_out" "$expected_aggregate" "${reference_paths[@]}" <<'PY_CHECK'
from pathlib import Path
import sys
output = Path(sys.argv[1]).resolve()
if any(output == Path(item).resolve() for item in sys.argv[2:]):
    raise SystemExit("actual-out must not overwrite a reference input")
PY_CHECK

mkdir -p "$(dirname "$actual_out")"
export PYTHONPATH="$repo_root${PYTHONPATH:+:$PYTHONPATH}"

python -m vigil.cli score-traces "${reference_paths[@]}" --out "$actual_out"
python "$repo_root/scripts/reproduce/compare_aggregates.py" \
  --expected "$expected_aggregate" \
  --actual "$actual_out" \
  --tolerance "$tolerance" \
  --pack-file "$pack_file"
