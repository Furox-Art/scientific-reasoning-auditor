import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

from sra.document import ParsedDocument


AUDITOR_VERSION = "0.4.0"
RULESET_VERSION = "0.4.0"
RULE_CONFIGURATION = {
    "audit_report_schema_version": "1.4",
    "manifest_schema_version": "1.1",
    "claim_marker_version": 1,
    "causal_design_rule_version": 2,
    "direction_conflict_rule_version": 2,
    "document_context_grouping_version": 2,
    "section_heading_match_version": 2,
    "welch_test_calculation_version": 1,
    "reported_value_tolerance_policy": "half_displayed_unit_last_place_or_explicit_override-v1",
    "reasoning_graph_schema_version": "1.1",
    "semantic_review_schema_version": "1.3",
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


def _source_tree_sha256() -> str | None:
    """Hash the exact auditor source/config files, including uncommitted changes."""
    repository_root = Path(__file__).resolve().parents[2]
    included = [
        *repository_root.glob("src/sra/**/*.py"),
        *repository_root.glob("schemas/**/*.json"),
        repository_root / "pyproject.toml",
    ]
    files = sorted(path for path in included if path.is_file())
    if not files:
        return None
    digest = hashlib.sha256()
    try:
        for path in files:
            relative = path.relative_to(repository_root).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    except OSError:
        return None
    return digest.hexdigest()


def build_manifest(document: ParsedDocument) -> dict:
    package_version = _package_version("scientific-reasoning-auditor") or AUDITOR_VERSION
    dependencies = {
        "scipy": _package_version("scipy"),
        "pypdf": _package_version("pypdf"),
    }
    revision, working_tree_dirty = _source_revision()
    source_code_sha256 = _source_tree_sha256()

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
        "source_code_sha256": source_code_sha256,
        "working_tree_dirty": working_tree_dirty,
    }
    environment_json = json.dumps(environment, sort_keys=True, separators=(",", ":"))
    environment_fingerprint = hashlib.sha256(environment_json.encode("utf-8")).hexdigest()

    return {
        "manifest_schema_version": "1.1",
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
            "section_parser": "markdown-fence-aware-and-plain-heading-v2",
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
        "source_code_sha256": source_code_sha256,
        "working_tree_dirty": working_tree_dirty,
        "revision_note": (
            "The source_code_sha256 identifies the exact included source/config snapshot, including uncommitted changes."
            if working_tree_dirty and source_code_sha256 else
            "The working tree was modified during the run, but the source snapshot hash could not be generated; preserve the exact source files."
            if working_tree_dirty else
            "The source_code_sha256 identifies the exact included source/config snapshot."
            if source_code_sha256 else
            "The source tree hash could not be generated; preserve the exact source files."
        ),
    }
