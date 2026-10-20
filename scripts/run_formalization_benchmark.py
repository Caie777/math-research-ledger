"""Execute one prepared benchmark using project-owned decision-only executors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from math_research.formalization.benchmark import execute_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lake", type=Path, required=True)
    parser.add_argument(
        "--configuration-only",
        action="store_true",
        help="Seal a blocked checkpoint; never allow model generation",
    )
    args = parser.parse_args()
    metadata = json.loads((args.output / "setup.json").read_text("utf-8"))
    print(
        json.dumps(
            execute_benchmark(
                args.project,
                args.repo,
                args.output,
                metadata,
                args.lake,
                allow_execution=not args.configuration_only,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
