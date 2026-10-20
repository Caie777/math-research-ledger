"""Reproducible experiment manifests for a dossier (Milestone M1, Phase 7).

Every experiment is a directory ``experiments/EXP-XXXX/`` with a manifest that
records exactly how to reproduce it: the command, working directory, Python
version, a dependencies hash, the git commit, and the random seed. An experiment
may *support* or *contradict* a claim; it may never *verify* one.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from math_research.ledger.records import store
from math_research.ledger.records.models import ExperimentRecord


def experiments_dir(ot_dir: Path, problem_id: str) -> Path:
    return store.dossier_dir(ot_dir, problem_id) / "experiments"


def experiment_dir(ot_dir: Path, problem_id: str, exp_id: str) -> Path:
    return experiments_dir(ot_dir, problem_id) / exp_id


def _manifest_path(ot_dir: Path, problem_id: str, exp_id: str) -> Path:
    return experiment_dir(ot_dir, problem_id, exp_id) / "manifest.yaml"


def list_experiments(ot_dir: Path, problem_id: str) -> list[ExperimentRecord]:
    root = experiments_dir(ot_dir, problem_id)
    if not root.is_dir():
        return []
    out: list[ExperimentRecord] = []
    for child in sorted(root.iterdir()):
        manifest = child / "manifest.yaml"
        if manifest.is_file():
            out.append(ExperimentRecord.model_validate(yaml.safe_load(manifest.read_text("utf-8"))))
    return out


def get_experiment(ot_dir: Path, problem_id: str, exp_id: str) -> ExperimentRecord | None:
    manifest = _manifest_path(ot_dir, problem_id, exp_id)
    if not manifest.is_file():
        return None
    return ExperimentRecord.model_validate(yaml.safe_load(manifest.read_text("utf-8")))


def list_problem_experiments(ot_dir: Path, problem_id: str) -> list[ExperimentRecord]:
    return list_experiments(ot_dir, problem_id)


def get_problem_experiment(ot_dir: Path, problem_id: str, exp_id: str) -> ExperimentRecord | None:
    return get_experiment(ot_dir, problem_id, exp_id)
