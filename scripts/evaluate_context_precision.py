"""Run isolated synthetic precision replay against current or explicitly supplied runtime."""

import argparse
import json
import sys
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--runtime-source", type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(args.runtime_source or root / "src"))

from benchmarks.precision.corpus import build  # noqa: E402
from benchmarks.precision.evaluate import evaluate  # noqa: E402

args.output.mkdir(parents=True, exist_ok=False)
corpus = build(args.output / "synthetic-workspace")
results = [evaluate(corpus, budget) for budget in (2000, 8000, 16000)]
(args.output / "results.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2), "utf-8"
)
print(
    json.dumps([{k: v for k, v in row.items() if k not in {"packet", "calls"}} for row in results])
)
