"""Build blinded reviewer packs and merge independent expert decisions.

The pack deliberately contains no automated predictions or source excerpts.
Software verifies source hashes, coverage and declared roles, but cannot
verify reviewer identity, qualification, independence or actual blinding.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from sra.benchmark import _get_article, _PMCPATTERN

_WORKSHEET_KIND = "blinded_validation_worksheet"
_PACK_KIND = "blinded_validation_pack"
_HEX = frozenset("0123456789abcdef")


def _load_benchmark(path: str | Path) -> tuple[bytes, list[dict[str, Any]]]:
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("kind") != "unlabeled_real_paper_smoke_test":
        raise ValueError("Expected an SRA PMC smoke-test report.")
    entries = data.get("paper_results")
    if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
        raise ValueError("Benchmark paper_results must be a list of objects.")
    papers = [item for item in entries if item.get("status") == "PROCESSED"]
    if not papers:
        raise ValueError("No processed papers in benchmark.")
    if len({item.get("pmcid") for item in papers}) != len(papers):
        raise ValueError("Benchmark has duplicate processed PMCIDs.")
    for paper in papers:
        pmcid = paper.get("pmcid")
        if not isinstance(pmcid, str) or _PMCPATTERN.fullmatch(pmcid) is None:
            raise ValueError("Every processed paper needs a PMCID.")
        source_hash = paper.get("response_sha256")
        if (not isinstance(source_hash, str) or len(source_hash) != 64
                or any(char not in _HEX for char in source_hash)):
            raise ValueError(f"Processed paper {pmcid} lacks a valid response_sha256.")
        if not isinstance(paper.get("writing_finding_codes"), list):
            raise ValueError("Benchmark lacks frozen writing_finding_codes; rerun a current benchmark.")
    return raw, papers


def _validate_codes(codes: Any) -> list[str]:
    if (not isinstance(codes, list) or not codes
            or any(not isinstance(code, str) or not code.strip() for code in codes)):
        raise ValueError("At least one non-empty finding code is required.")
    if len(set(codes)) != len(codes):
        raise ValueError("Finding codes must be unique.")
    return list(codes)


def _validate_reviewers(reviewer_ids: Any) -> list[str]:
    if not isinstance(reviewer_ids, list) or len(reviewer_ids) != 2:
        raise ValueError("Exactly two declared reviewer IDs are required.")
    if (any(not isinstance(item, str) or not item.strip() for item in reviewer_ids)
            or reviewer_ids[0].strip() == reviewer_ids[1].strip()):
        raise ValueError("Reviewer IDs must be two distinct non-empty strings.")
    return [item.strip() for item in reviewer_ids]


def _prepare_output_dir(out_dir: str | Path) -> Path:
    out = Path(out_dir)
    if out.exists():
        if not out.is_dir():
            raise ValueError("Output path exists and is not a directory.")
        if any(out.iterdir()):
            raise ValueError("Output directory must be new or empty.")
    else:
        out.mkdir(parents=True)
    return out


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


_PACK_INSTRUCTIONS = [
    "Read only the supplied paper text and coding manual.",
    "Set verdict to JSON true or false for every case; blank, null and string values are invalid.",
    "Do not run the auditor, inspect automated findings or view the other reviewer's worksheet.",
    "Do not discuss cases with the other reviewer before both worksheets are submitted.",
    "Return this file unchanged except for verdict values and optional notes.",
    "A reviewer ID is a declaration; software cannot verify identity, qualification or independence.",
]


def build_validation_pack(
    benchmark_path: str | Path,
    out_dir: str | Path,
    reviewer_ids: list[str],
    codes: list[str],
    *,
    online: bool = False,
    manual_path: str | Path | None = None,
) -> dict[str, Any]:
    if not online:
        raise ValueError("PMC network retrieval requires explicit --online.")
    raw, papers = _load_benchmark(benchmark_path)
    codes = _validate_codes(codes)
    reviewer_ids = _validate_reviewers(reviewer_ids)
    out = _prepare_output_dir(out_dir)
    benchmark_sha = hashlib.sha256(raw).hexdigest()

    manual_sha = None
    if manual_path is not None:
        manual_text = Path(manual_path).read_text(encoding="utf-8")
        if not manual_text.strip():
            raise ValueError("Coding manual is empty.")
        manual_sha = hashlib.sha256(manual_text.encode("utf-8")).hexdigest()
        (out / "coding_manual.md").write_text(manual_text, encoding="utf-8", newline="\n")

    papers_dir = out / "papers"
    papers_dir.mkdir()
    paper_entries = []
    for index, paper in enumerate(papers):
        if index:
            time.sleep(0.38)  # Stay below the PMC 3-requests/second service guidance.
        pmcid = paper["pmcid"]
        text, metadata = _get_article(pmcid)
        if metadata.get("response_sha256") != paper["response_sha256"]:
            raise ValueError(
                f"Frozen source hash changed for {pmcid}; rebuild the benchmark before labelling."
            )
        text_path = papers_dir / f"{pmcid}.md"
        if not text_path.resolve().is_relative_to(papers_dir.resolve()):
            raise ValueError("PMCID must stay within the blinded papers directory.")
        text_path.write_text(text, encoding="utf-8", newline="\n")
        paper_entries.append({
            "pmcid": pmcid,
            "source_sha256": paper["response_sha256"],
            "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text_file": f"papers/{pmcid}.md",
        })

    cases = [
        {
            "pmcid": paper["pmcid"],
            "code": code,
            "source_sha256": paper["response_sha256"],
            "text_file": f"papers/{paper['pmcid']}.md",
            "verdict": None,
        }
        for paper in papers
        for code in codes
    ]
    for index, reviewer_id in enumerate(reviewer_ids, start=1):
        _write_json(out / f"reviewer_{index}.json", {
            "schema_version": "1.0",
            "kind": _WORKSHEET_KIND,
            "benchmark_sha256": benchmark_sha,
            "reviewer_id": reviewer_id,
            "finding_codes": list(codes),
            "instructions": _PACK_INSTRUCTIONS,
            "cases": [dict(case) for case in cases],
        })

    (out / "README.md").write_text(
        "# Blinded validation pack\n\n"
        "Each reviewer must fill a separate worksheet without consulting the other "
        "or any automated report. Every case needs a boolean verdict. Return the "
        "completed worksheet and a signed qualification/conflict declaration to "
        "the study organizer. The paper texts are for this review only and must "
        "not be redistributed.\n",
        encoding="utf-8",
    )

    pack = {
        "schema_version": "1.0",
        "kind": _PACK_KIND,
        "benchmark_sha256": benchmark_sha,
        "finding_codes": list(codes),
        "reviewer_ids": list(reviewer_ids),
        "paper_count": len(papers),
        "unit_count": len(cases),
        "papers": paper_entries,
        "manual_sha256": manual_sha,
        "instructions": _PACK_INSTRUCTIONS,
        "limitations": [
            "Worksheets contain no automated predictions or source excerpts.",
            "Reviewer identity, qualifications, independence and actual blinding are not verified by software.",
            "Full texts are stored outside the repository and must not be redistributed.",
        ],
    }
    _write_json(out / "pack_manifest.json", pack)
    return pack


def _load_sheet(path: str | Path, benchmark_sha: str) -> tuple[str, list[str], list[dict[str, Any]]]:
    raw = Path(path).read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("kind") != _WORKSHEET_KIND:
        raise ValueError("Expected a blinded validation worksheet.")
    if data.get("benchmark_sha256") != benchmark_sha:
        raise ValueError("Reviewer worksheet does not match the frozen benchmark.")
    reviewer_id = data.get("reviewer_id")
    if not isinstance(reviewer_id, str) or not reviewer_id.strip():
        raise ValueError("Reviewer worksheet lacks a reviewer ID.")
    codes = _validate_codes(data.get("finding_codes"))
    cases = data.get("cases")
    if not isinstance(cases, list) or any(not isinstance(case, dict) for case in cases):
        raise ValueError("Reviewer worksheet cases must be a list of objects.")
    return reviewer_id.strip(), codes, cases


def _case_verdicts(
    cases: list[dict[str, Any]],
    expected: list[tuple[str, str]],
    papers_by_pmcid: dict[str, dict[str, Any]],
    reviewer_id: str,
) -> dict[tuple[str, str], bool]:
    expected_set = set(expected)
    verdicts: dict[tuple[str, str], bool] = {}
    for case in cases:
        key = (case.get("pmcid"), case.get("code"))
        if key not in expected_set or key in verdicts:
            raise ValueError("Unknown or repeated (PMCID, code) annotation unit.")
        if case.get("source_sha256") != papers_by_pmcid[key[0]]["response_sha256"]:
            raise ValueError("Reviewer source hash differs from the frozen paper source.")
        if type(case.get("verdict")) is not bool:
            raise ValueError(f"Reviewer {reviewer_id} must set a boolean verdict for every case.")
        verdicts[key] = case["verdict"]
    if set(verdicts) != expected_set:
        raise ValueError(
            f"Reviewer {reviewer_id} annotation coverage incomplete: "
            f"{len(verdicts)}/{len(expected)} units."
        )
    return verdicts


def _load_adjudications(
    path: str | Path,
    reviewer_ids: list[str],
    expected: list[tuple[str, str]],
) -> tuple[str, dict[tuple[str, str], bool]]:
    data = json.loads(Path(path).read_bytes())
    if not isinstance(data, dict):
        raise ValueError("Adjudication file must be a JSON object.")
    adjudicator_id = data.get("adjudicator_id")
    if not isinstance(adjudicator_id, str) or not adjudicator_id.strip():
        raise ValueError("An adjudicator_id is required.")
    adjudicator_id = adjudicator_id.strip()
    if adjudicator_id in reviewer_ids:
        raise ValueError("The adjudicator must be distinct from both reviewers.")
    decisions = data.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError("Adjudication decisions must be a list.")
    expected_set = set(expected)
    labels: dict[tuple[str, str], bool] = {}
    for decision in decisions:
        if not isinstance(decision, dict):
            raise ValueError("Every adjudication decision must be an object.")
        key = (decision.get("pmcid"), decision.get("code"))
        if key not in expected_set or key in labels:
            raise ValueError("Unknown or repeated adjudication unit.")
        if type(decision.get("expert_label")) is not bool:
            raise ValueError("Every adjudication decision needs a boolean expert_label.")
        rationale = decision.get("rationale")
        if not isinstance(rationale, str) or len(rationale.strip()) < 20:
            raise ValueError("Every adjudication decision needs a 20+ character rationale.")
        labels[key] = decision["expert_label"]
    return adjudicator_id, labels


def merge_adjudicated_labels(
    benchmark_path: str | Path,
    reviewer_a_path: str | Path,
    reviewer_b_path: str | Path,
    adjudications_path: str | Path,
) -> dict[str, Any]:
    raw, papers = _load_benchmark(benchmark_path)
    benchmark_sha = hashlib.sha256(raw).hexdigest()
    reviewer_a, codes_a, cases_a = _load_sheet(reviewer_a_path, benchmark_sha)
    reviewer_b, codes_b, cases_b = _load_sheet(reviewer_b_path, benchmark_sha)
    if reviewer_a == reviewer_b:
        raise ValueError("Reviewer IDs must be distinct.")
    if codes_a != codes_b:
        raise ValueError("Reviewer worksheets use different finding codes.")
    codes = codes_a
    expected = [(paper["pmcid"], code) for paper in papers for code in codes]
    papers_by_pmcid = {paper["pmcid"]: paper for paper in papers}
    verdicts_a = _case_verdicts(cases_a, expected, papers_by_pmcid, reviewer_a)
    verdicts_b = _case_verdicts(cases_b, expected, papers_by_pmcid, reviewer_b)
    adjudicator_id, decisions = _load_adjudications(
        adjudications_path, [reviewer_a, reviewer_b], expected
    )

    disagreements = {
        key for key in expected
        if verdicts_a[key] != verdicts_b[key]
    }
    if set(decisions) != disagreements:
        if set(decisions) - disagreements:
            raise ValueError("Adjudication decisions are only allowed for reviewer disagreements.")
        raise ValueError("Every reviewer disagreement requires an adjudication decision.")

    final_cases = []
    for key in expected:
        pmcid, code = key
        if verdicts_a[key] == verdicts_b[key]:
            expert_label = verdicts_a[key]
        else:
            expert_label = decisions[key]
        final_cases.append({
            "pmcid": pmcid,
            "code": code,
            "source_sha256": papers_by_pmcid[pmcid]["response_sha256"],
            "expert_label": expert_label,
            "reviewer_ids": [reviewer_a, reviewer_b],
            "reviewer_labels": [verdicts_a[key], verdicts_b[key]],
            "adjudicated": True,
        })

    unit_count = len(expected)
    agreements = unit_count - len(disagreements)
    raw_agreement = agreements / unit_count
    a_positive = sum(verdicts_a.values()) / unit_count
    b_positive = sum(verdicts_b.values()) / unit_count
    chance = a_positive * b_positive + (1 - a_positive) * (1 - b_positive)
    kappa = (raw_agreement - chance) / (1 - chance) if chance < 1 else None
    return {
        "schema_version": "1.0",
        "kind": "adjudicated_validation_labels",
        "benchmark_sha256": benchmark_sha,
        "finding_codes": list(codes),
        "adjudicator_id": adjudicator_id,
        "cases": final_cases,
        "inter_reviewer_agreement": {
            "units": unit_count,
            "agreements": agreements,
            "disagreements": len(disagreements),
            "raw_exact_agreement": raw_agreement,
            "cohen_kappa": kappa,
            "interpretation": "Agreement is not proof that either reviewer or the adjudicator is correct.",
        },
        "limitations": [
            "Reviewer and adjudicator IDs are declarations, not verified identities or qualifications.",
            "Software verifies hashes, coverage and boolean structure only, not scientific judgement.",
            "Labels apply only to the supplied BioC-derived texts and the preregistered codes.",
        ],
    }
