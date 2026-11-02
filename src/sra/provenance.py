import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

from sra.document import ParsedDocument


AUDITOR_VERSION = "0.2.2"
RULESET_VERSION = "0.2.2"
RULE_CONFIGURATION = {
    "claim_marker_version": 1,
    "causal_design_rule_version": 1,
    "direction_conflict_rule_version": 1,
    "section_heading_match_version": 1,
    "welch_test_calculation_version": 1,
    "reported_value_tolerance_policy": "half_displayed_unit_last_place_or_explicit_override-v1",
    "lexical_candidate_minimum_jaccard": 0.15,
    "max_evidence_excerpts_per_finding": 5,
}


def _package_version(name: str) -> str | None:
    try:
        return version(name)
    except PackageNotFoundError:
        return None


def _source_revision() -> tuple[str | None, bool | None]:
    repository_root = Path(__file__).resolve().parents[2]
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=2,
        ).stdout.strip())
        return revision, dirty
    except (OSError, subprocess.SubprocessError):
        return None, None


def build_manifest(document: ParsedDocument) -> dict:
    package_version = _package_version("scientific-reasoning-auditor") or AUDITOR_VERSION
    dependencies = {
        "scipy": _package_version("scipy"),
        "pypdf": _package_version("pypdf"),
    }
    revision, working_tree_dirty = _source_revision()

    configuration_json = json.dumps(
        RULE_CONFIGURATION, sort_keys=True, separators=(",", ":")
    )
    configuration_hash = hashlib.sha256(configuration_json.encode("utf-8")).hexdigest()
    environment = {
        "auditor_version": AUDITOR_VERSION,
        "python_version": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "parser_backend": document.parser_backend,
        "ruleset_version": RULESET_VERSION,
        "configuration_sha256": configuration_hash,
        "dependencies": dependencies,
        "source_code_revision": revision,
        "working_tree_dirty": working_tree_dirty,
    }
    environment_json = json.dumps(environment, sort_keys=True, separators=(",", ":"))
    environment_fingerprint = hashlib.sha256(environment_json.encode("utf-8")).hexdigest()

    return {
        "manifest_schema_version": "1.0",
        "auditor_version": AUDITOR_VERSION,
        "installed_package_version": package_version,
        "ruleset_version": RULESET_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": {
            "filename": document.source,
            "format": document.input_format,
            "size_bytes": document.source_size_bytes,
            "sha256": document.sha256,
        },
        "parser": {
            "backend": document.parser_backend,
            "section_parser": "markdown-heading-regex-v1",
            "text_encoding": "utf-8",
        },
        "runtime": {
            "python_version": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "dependencies": dependencies,
        },
        "configuration": RULE_CONFIGURATION,
        "configuration_sha256": configuration_hash,
        "environment_fingerprint": environment_fingerprint,
        "source_code_revision": revision,
        "working_tree_dirty": working_tree_dirty,
        "revision_note": (
            "The working tree was modified during the run; preserve the exact source files or "
            "commit them to reproduce this build."
            if working_tree_dirty else
            "Revision is unavailable because the package was not running from an accessible Git checkout."
            if revision is None else
            "Git commit is recorded; dependency and configuration fingerprints are recorded separately."
        ),
    }
