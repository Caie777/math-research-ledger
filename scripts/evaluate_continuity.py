"""Reproduce the frozen synthetic benchmark in a NEW directory; no real workspace input."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.continuity.evaluate import evaluate_budget  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New synthetic output directory")
    parser.add_argument("--budgets", type=int, nargs="+", default=[2000, 8000, 16000])
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    for budget in args.budgets:
        result = evaluate_budget(args.output / str(budget), budget)
        (args.output / f"benchmark-{budget}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), "utf-8"
        )
        print(
            json.dumps([row["metrics"] for row in result["results"]], ensure_ascii=False),
            flush=True,
        )


if __name__ == "__main__":
    main()
