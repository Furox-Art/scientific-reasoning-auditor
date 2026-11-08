import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version

from sra import __version__
from sra.document import ParsedDocument


AUDITOR_VERSION = __version__
RULESET_VERSION = "0.5.2"
RULE_CONFIGURATION = {
    "audit_report_schema_version": "1.5",
    "manifest_schema_version": "1.4",
    "claim_marker_version": 2,
    "causal_design_rule_version": 4,
    "direction_conflict_rule_version": 4,
    "repeated_rate_ratio_ci_rule_version": 1,
    "document_context_grouping_version": 2,
    "section_heading_match_version": 3,
    "welch_test_calculation_version": 2,
    "reported_value_tolerance_policy": "half_displayed_unit_last_place_or_explicit_override-v1",
    "reasoning_graph_schema_version": "1.4",
    "semantic_review_schema_version": "1.4",
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


REPOSITORY_HASH_GROUPS = (
    # py.typed ships inside the package and is part of what a distribution
    # claims to be: without it here the sdist inventory disagreed with the
    # distribution verifier, which saw one member it did not expect.
    ("Python runtime source", ("src/sra/**/*.py", "src/sra/py.typed")),
    ("JSON schemas", ("schemas/**/*.json",)),
    ("Python tests", ("tests/**/*.py",)),
    ("Node adapter sources and tests", ("test/**/*.js", "bin/**/*.js")),
    ("Build verification tools", ("tools/**/*.py",)),
    ("GitHub Actions workflows", (".github/workflows/**/*.yml",)),
    ("examples", ("examples/**/*.md", "examples/**/*.json")),
)
REPOSITORY_HASH_FILES = (
    "pyproject.toml",
    "package.json",
    "index.js",
    "index.d.ts",
    "MANIFEST.in",
    "README.md",
    "LICENSE",
)
INSTALLED_PACKAGE_HASH_SCOPE = "installed Python package source files only"


def _source_tree_sha256(
    repository_root: Path | None = None,
) -> tuple[str | None, str, list[str]]:
    """Hash selected runtime, test, workflow, adapter, schema and build inputs."""
    repository_root = (
        Path(repository_root).resolve()
        if repository_root is not None
        else Path(__file__).resolve().parents[2]
    )
    files_by_category: list[tuple[str, list[Path]]] = []
    for category, patterns in REPOSITORY_HASH_GROUPS:
        category_files = sorted({
            path
            for pattern in patterns
            for path in repository_root.glob(pattern)
            if path.is_file()
        })
        if category_files:
            files_by_category.append((category, category_files))

    metadata_files = [
        repository_root / name
        for name in REPOSITORY_HASH_FILES
        if (repository_root / name).is_file()
    ]
    if metadata_files:
        files_by_category.append(("package/build/documentation metadata", metadata_files))

    files = sorted({
        path for _, category_files in files_by_category for path in category_files
    })
    if files:
        hash_root = repository_root
        scope = "; ".join(category for category, _ in files_by_category)
    else:
        package_root = Path(__file__).resolve().parent
        files = sorted(path for path in package_root.rglob("*.py") if path.is_file())
        if not files:
            return None, INSTALLED_PACKAGE_HASH_SCOPE, []
        hash_root = package_root.parent
        scope = INSTALLED_PACKAGE_HASH_SCOPE

    # Sort by the recorded name, not by Path. ``Path`` comparison is
    # case-insensitive, so a tree containing both ``LICENSE`` and ``bin/sra.js``
    # produced an order that is not plain string order -- and the distribution
    # verifier, which checks the inventory against ``sorted()``, rejected it.
    # The inventory is the record that matters, so the order is the record's.
    files.sort(key=lambda path: path.relative_to(hash_root).as_posix())

    included_files = [path.relative_to(hash_root).as_posix() for path in files]
    digest = hashlib.sha256()
    try:
        for path in files:
            relative = path.relative_to(hash_root).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    except OSError:
        return None, scope, included_files
    return digest.hexdigest(), scope, included_files


def build_manifest(document: ParsedDocument) -> dict:
    package_version = _package_version("scientific-reasoning-auditor") or AUDITOR_VERSION
    dependencies = {
        "scipy": _package_version("scipy"),
        "pypdf": _package_version("pypdf"),
    }
    revision, working_tree_dirty = _source_revision()
    source_code_sha256, source_code_hash_scope, source_code_hash_files = _source_tree_sha256()
    extracted_text_sha256 = hashlib.sha256(document.text.encode("utf-8")).hexdigest()

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
        "extracted_text_sha256": extracted_text_sha256,
        "ruleset_version": RULESET_VERSION,
        "configuration_sha256": configuration_hash,
        "dependencies": dependencies,
        "source_code_revision": revision,
        "source_code_sha256": source_code_sha256,
        "source_code_hash_scope": source_code_hash_scope,
        "source_code_hash_files": source_code_hash_files,
        "working_tree_dirty": working_tree_dirty,
    }
    environment_json = json.dumps(environment, sort_keys=True, separators=(",", ":"))
    environment_fingerprint = hashlib.sha256(environment_json.encode("utf-8")).hexdigest()

    return {
        "manifest_schema_version": "1.4",
        "auditor_version": AUDITOR_VERSION,
        "installed_package_version": package_version,
        "ruleset_version": RULESET_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input": {
            "filename": document.source,
            "format": document.input_format,
            "size_bytes": document.source_size_bytes,
            "sha256": document.sha256,
            "extracted_text_sha256": extracted_text_sha256,
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
        "source_code_hash_scope": source_code_hash_scope,
        "source_code_hash_files": source_code_hash_files,
        "working_tree_dirty": working_tree_dirty,
        "revision_note": (
            "The source_code_sha256 covers exactly the installed Python package source files listed in source_code_hash_files; repository-only tests, workflows, schemas and build metadata are not all available in an installed wheel."
            if source_code_hash_scope == INSTALLED_PACKAGE_HASH_SCOPE and source_code_sha256 else
            "The source_code_sha256 covers exactly the relative paths listed in source_code_hash_files; source_code_hash_scope describes their categories. Other repository files are not included."
            if source_code_sha256 else
            "The source tree hash could not be generated; preserve the exact source files."
        ),
    }
