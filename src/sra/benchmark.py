"""Reproducible external-paper smoke testing with the authorized NCBI PMC BioC API.

The test corpus contains real papers, but without independently adjudicated
scientific labels these results are NOT estimates of sensitivity or specificity.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sra.audit import audit_file
from sra.writing import audit_academic_writing

_PMCPATTERN = re.compile(r"PMC[1-9][0-9]{4,9}$")
_SECTION_NAMES = {
    "ABSTRACT": "Abstract",
    "INTRO": "Introduction",
    "METHODS": "Methods",
    "METHOD": "Methods",
    "RESULTS": "Results",
    "DISCUSS": "Discussion",
    "CONCL": "Conclusion",
}
_BIOC_BASE = "https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_json/"


def _get_article(pmcid: str, timeout: float = 12.0) -> tuple[str, dict]:
    url = _BIOC_BASE + pmcid + "/unicode"
    request = Request(url, headers={"User-Agent": "ScientificReasoningAuditor research QA (https://github.com/Furox-Art/scientific-reasoning-auditor)"})
    with urlopen(request, timeout=timeout) as response:
        data = response.read(6_000_001)
    if len(data) > 6_000_000:
        raise ValueError("BioC response exceeds the 6 MB safety limit.")
    payload = json.loads(data)
    if not isinstance(payload, list) or not payload:
        raise ValueError("Expected a non-empty BioC collections list.")
    docs = payload[0].get("documents", [])
    if not docs or not isinstance(docs[0], dict):
        raise ValueError("BioC document is unavailable.")
    passages = docs[0].get("passages", [])
    if not isinstance(passages, list) or not passages:
        raise ValueError("BioC has no passages.")
    first = passages[0].get("infons", {})
    returned_id = str(
        first.get("article-id_pmc")
        or first.get("article-id_pmcid")
        or first.get("article-id_pmcaid")
        or docs[0].get("id", "")
    )
    if returned_id.removeprefix("PMC") != pmcid.removeprefix("PMC"):
        raise ValueError("BioC article ID does not match the requested PMCID.")
    if not first.get("article-id_doi"):
        raise ValueError("BioC article has no registered source DOI metadata.")
    metadata = {
        "pmcid": pmcid, "doi": first.get("article-id_doi"),
        "title": passages[0].get("text", ""),
        "license_present": bool(first.get("license")),
        "license_text_sha256": (
            hashlib.sha256(str(first["license"]).encode("utf-8")).hexdigest()
            if first.get("license") else None
        ),
        "source_url": url,
        "response_sha256": hashlib.sha256(data).hexdigest(),
    }
    parts = []
    last_heading = None
    body_segments = 0
    for passage in passages:
        if not isinstance(passage, dict):
            continue
        infons = passage.get("infons", {})
        section = _SECTION_NAMES.get(str(infons.get("section_type", "")).upper())
        kind = str(infons.get("type", "")).lower()
        passage_text = passage.get("text", "")
        if not section or not isinstance(passage_text, str) or not passage_text.strip():
            continue
        if "title" in kind:
            continue
        if section != last_heading:
            parts.append(f"# {section}")
            last_heading = section
        parts.append(passage_text.strip())
        body_segments += 1
    if body_segments < 4:
        raise ValueError("Too few body passages for manuscript smoke test.")
    return "\n\n".join(parts) + "\n", metadata


def run_pmc_benchmark(manifest_path: str | Path, *, online: bool = False,
                      limit: int = 20) -> dict:
    if not online:
        raise ValueError("PMC network retrieval requires explicit --online.")
    if type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("limit must be an integer between 1 and 200.")
    raw = Path(manifest_path).read_bytes()
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("pmcids"), list):
        raise ValueError("Manifest must be a JSON object with a pmcids list.")
    ids = manifest["pmcids"][:limit]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Manifest PMCID list must be non-empty with unique IDs.")
    if any(not isinstance(item, str) or not _PMCPATTERN.fullmatch(item) for item in ids):
        raise ValueError("PMCID must have format PMC followed by 5–10 digits.")
    records = []
    for index, pmcid in enumerate(ids):
        if index:
            time.sleep(0.38)  # Stay below the PMC 3-requests/second service guidance.
        record = {"pmcid": pmcid}
        try:
            text, metadata = _get_article(pmcid)
            with tempfile.TemporaryDirectory(prefix="sra-pmc-") as tmp:
                document_path = Path(tmp) / "pmc_article.md"
                document_path.write_text(text, encoding="utf-8")
                report = audit_file(str(document_path))
                writing = audit_academic_writing(document_path)
            record.update({
                "status": "PROCESSED",
                **metadata,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "word_count": writing["metrics"]["document_word_count"],
                "writing_review_prompts": len(writing["findings"]),
                "writing_finding_codes": sorted({item["code"] for item in writing["findings"]}),
                "reasoning_review_prompts": len(report.findings),
                "reasoning_graph_nodes": len(report.reasoning_graph.get("nodes", [])),
            })
        except (OSError, ValueError, RuntimeError, TypeError, HTTPError, URLError, json.JSONDecodeError) as exc:
            record.update({"status": "FETCH_OR_PROCESS_FAILED", "error_type": type(exc).__name__})
        records.append(record)
    successes = sum(record["status"] == "PROCESSED" for record in records)
    return {
        "schema_version": "1.0",
        "kind": "unlabeled_real_paper_smoke_test",
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "source": "NIH NCBI PMC BioC API; user-provided PMCID allowlist",
        "total_requested": len(ids),
        "processed": successes,
        "failed": len(ids)-successes,
        "paper_results": records,
        "independent_expert_labels": 0,
        "sensitivity": None,
        "specificity": None,
        "precision": None,
        "limitations": [
            "This is a real-paper integration and robustness test, not independent scientific performance validation.",
            "No expert-adjudicated truth labels were available; sensitivity, specificity and false-positive rates are NOT estimated.",
            "BioC text extraction may omit tables, figures, and other evidence; results must not imply manuscript deficiencies.",
            "Response SHA-256 and source links enable audit of external data; full texts are not stored or redistributed.",
            "Review publisher licenses and PMC terms for any separate storage or redistribution of source texts.",
        ],
    }
