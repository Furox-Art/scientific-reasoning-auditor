"""Offline-first composition of independent checks on one manuscript snapshot."""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from contextlib import ExitStack
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from sra.audit import audit_parsed_document
from sra.capabilities import capabilities, STUDY_TYPES, REPORT_SCHEMA, EMPIRICAL_STRUCTURE
from sra.document import ParsedDocument, SourceIdentityError, load_document
from sra.doi import verify_document_dois
from sra.domain_evidence import PROFILES, review_domain
from sra.json_utils import reject_duplicate_keys
from sra.paper_review import review_parsed_paper, read_visual_source, _chunks, MAX_INPUT_BYTES
from sra.scientific_validation import verify_scientific_spec
from sra.stats import verify_welch_t_test
from sra.stats_extended import verify_extended_stats
from sra.writing import audit_academic_writing_document
from sra.logic_spec import prepare_logic_spec
from sra.logic import verify_prepared_logic
from sra.toolkit_spec import prepare_toolkit_spec
from sra.toolkit import verify_prepared_toolkit
from sra.criteria import build_criteria_matrix

MAX_SPEC_BYTES = 1024 * 1024


def _reject_constant(token: str) -> None:
    raise ValueError("Non-finite JSON constants are not permitted.")


def load_spec_file(path: str | Path) -> str:
    """Bound reads before allocation; preserve decimal precision in the JSON text."""
    with Path(path).expanduser().open("rb") as stream:
        raw = stream.read(MAX_SPEC_BYTES + 1)
    if len(raw) > MAX_SPEC_BYTES:
        raise ValueError("Structured specification exceeds the 1 MiB limit.")
    return raw.decode("utf-8-sig")


def _decode_spec(value: dict | str) -> tuple[dict, str]:
    try:
        raw = value if isinstance(value, str) else json.dumps(value, allow_nan=False, ensure_ascii=False)
        if len(raw) > MAX_SPEC_BYTES or len(raw.encode("utf-8")) > MAX_SPEC_BYTES:
            raise ValueError("Structured specification exceeds the 1 MiB limit.")
        spec = json.loads(raw, parse_float=Decimal, parse_constant=_reject_constant,
                          object_pairs_hook=reject_duplicate_keys)
    except (TypeError, RecursionError, UnicodeError) as exc:
        raise ValueError("Structured specification must be bounded JSON.") from exc
    if not isinstance(spec, dict):
        raise ValueError("Structured specification must be a JSON object.")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return spec, digest


def _prepare_spec(value: dict | str, science: bool) -> dict:
    spec, digest = _decode_spec(value)
    # Complete local validation/calculation BEFORE either external service is called.
    if science:
        return verify_scientific_spec(spec, digest)
    if spec.get("test") == "welch_t":
        return verify_welch_t_test(spec, digest)
    return verify_extended_stats(spec, digest)


def _configuration(study_type, disciplines, style_language, online, send_to_model,
                   model, timeout, chunk_chars, visual_pages) -> dict:
    if not isinstance(study_type, str) or study_type not in STUDY_TYPES:
        raise ValueError("Unsupported study_type. Consult capabilities.")
    if not isinstance(disciplines, (list, tuple)) or any(
        not isinstance(item, str) or item not in PROFILES for item in disciplines
    ):
        raise ValueError("disciplines must be a list of supported profile identifiers.")
    if style_language not in ("en", "tr", "none"):
        raise ValueError("style_language must be en, tr or none.")
    if any(type(item) is not bool for item in (online, send_to_model, visual_pages)):
        raise ValueError("online, send_to_model and visual_pages must be booleans.")
    if send_to_model and (not isinstance(model, str) or not model.strip() or len(model) > 128):
        raise ValueError("Explicit model consent requires a valid model identifier.")
    if not send_to_model and (model is not None or visual_pages):
        raise ValueError("Model and page-image review require send_to_model=true.")
    if type(timeout) is not int or not 1 <= timeout <= 600:
        raise ValueError("timeout must be an integer between 1 and 600 seconds.")
    if type(chunk_chars) is not int or not 2000 <= chunk_chars <= 20000:
        raise ValueError("chunk_chars must be an integer from 2000 to 20000.")
    return {"study_type": study_type, "disciplines": list(dict.fromkeys(disciplines)),
            "style_language": style_language, "online": online,
            "send_to_model": send_to_model, "model": model,
            "timeout": timeout, "chunk_chars": chunk_chars, "visual_pages": visual_pages}


def review_manuscript(path: str | Path, *, pdf_ocr_mode: str = "off",
                      ocr_languages: str = "eng", **options) -> dict[str, Any]:
    """Compose a review without modifying the manuscript or using network by default."""
    document = load_document(path, pdf_ocr_mode=pdf_ocr_mode, ocr_languages=ocr_languages)
    return review_document(document, visual_path=path, **options)


def review_document(
    document: ParsedDocument, *, study_type: str = "unknown",
    disciplines: list[str] | tuple[str, ...] = (), style_language: str = "en",
    online: bool = False, statistics_spec: dict | str | None = None,
    scientific_spec: dict | str | None = None, send_to_model: bool = False,
    logic_spec: dict | str | None = None,
    toolkit_spec: dict | str | None = None,
    prepare_inputs: bool = False,
    model: str | None = None, base_url: str = "https://api.openai.com/v1",
    api_key_env: str = "OPENAI_API_KEY", timeout: int = 120, chunk_chars: int = 12000,
    visual_pages: bool = False, visual_path: str | Path | None = None,
) -> dict[str, Any]:
    """Bind all module executions to one detached parsed snapshot and one contract."""
    config = _configuration(study_type, disciplines, style_language, online,
                            send_to_model, model, timeout, chunk_chars, visual_pages)
    if visual_pages and document.input_format != "pdf":
        raise ValueError("Page images require PDF input.")
    if send_to_model:
        if document.source_size_bytes > MAX_INPUT_BYTES:
            raise ValueError("Model review input exceeds the 20 MiB limit.")
        _chunks(document.text, chunk_chars)
    visual_bytes = read_visual_source(document, visual_path) if visual_pages else None
    document = copy.deepcopy(document)
    if type(prepare_inputs) is not bool:
        raise ValueError('prepare_inputs must be boolean.')
    prepared_logic = prepare_logic_spec(logic_spec, document) if logic_spec is not None else None
    prepared_toolkit = prepare_toolkit_spec(toolkit_spec, document) if toolkit_spec is not None else None
    text_digest = hashlib.sha256(document.text.encode("utf-8")).hexdigest()
    catalog = capabilities()
    modules: dict[str, dict] = {}
    requested_scientific_kinds = ()

    def entry(status: str, result=None, reason: str | None = None) -> dict:
        return {"status": status, "reason": reason, "source_sha256": document.sha256,
                "extracted_text_sha256": text_digest, "result": result}

    def run(name: str, operation: Callable[[], dict], *, required=False) -> None:
        try:
            result = operation()
        except SourceIdentityError:
            raise
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            if required:
                raise
            status = "unavailable" if isinstance(exc, ImportError) or isinstance(exc.__cause__, ImportError) else "failed"
            modules[name] = entry(status, reason=f"{type(exc).__name__}: module did not complete; details withheld.")
            return
        bound = result.get("source_sha256", result.get("sha256", document.sha256))
        if bound != document.sha256 or result.get("extracted_text_sha256", text_digest) != text_digest:
            raise SourceIdentityError(f"Module {name} returned a mismatched source identity.")
        modules[name] = entry("completed", result)

    # Validate structured inputs before any network; missing optional dependencies
    # remain explicit, but malformed JSON or calculation specifications fail closed.
    for name, value, science in (("statistics", statistics_spec, False),
                                  ("scientific", scientific_spec, True)):
        if value is None:
            modules[name] = entry("not_requested", reason="No explicit structured values supplied.")
        else:
            if science:
                requested, _ = _decode_spec(value)
                checks = requested.get('checks', [])
                requested_scientific_kinds = tuple(item.get('kind') for item in checks
                    if isinstance(item, dict) and isinstance(item.get('kind'), str)) if isinstance(checks, list) else ()
            try:
                prepared = _prepare_spec(value, science)
            except (ImportError, RuntimeError) as exc:
                unavailable = isinstance(exc, ImportError) or isinstance(exc.__cause__, ImportError)
                modules[name] = entry("unavailable" if unavailable else "failed",
                                      reason="Structured calculation did not complete; check optional dependencies and inputs.")
            else:
                modules[name] = entry("completed", prepared)

    if prepared_logic is not None:
        run("logic", lambda: verify_prepared_logic(prepared_logic))
        if modules["logic"]["result"] is not None and modules["logic"]["result"]["execution_status"] == "partial":
            modules["logic"]["status"] = "failed"
            modules["logic"]["reason"] = "Formal verification reached a solver budget; no unknown result is a proof."
    if prepared_toolkit is not None:
        run("toolkit", lambda: verify_prepared_toolkit(prepared_toolkit))
        if modules["toolkit"]["result"] is not None and modules["toolkit"]["result"]["execution_status"] == "partial":
            modules["toolkit"]["status"] = "failed"
            modules["toolkit"]["reason"] = "Some requested toolkit checks were unavailable, failed or undetermined; inspect per-check results."
    if prepare_inputs:
        from sra.inspection import prepare_inspection
        run('preparation',lambda:prepare_inspection(document))
    modules["extraction"] = entry("completed", {
        "backend": document.parser_backend, "input_format": document.input_format,
        "input_bytes": document.source_size_bytes, "extracted_characters": len(document.text),
        "page_details": document.extraction_details,
    })
    run("reasoning", lambda: audit_parsed_document(document).to_dict(), required=True)
    excluded = []
    reasoning = modules["reasoning"]["result"]
    included = []
    for finding in reasoning["findings"]:
        if study_type in ("theoretical", "narrative-review") and finding["check_id"] in EMPIRICAL_STRUCTURE:
            excluded.append({"module": "reasoning", "finding": finding,
                             "reason": "Empirical section-heading expectation does not apply to the declared study type."})
        else:
            included.append(finding)
    reasoning["findings"] = included
    run("writing", lambda: audit_academic_writing_document(document, style_language=style_language))
    for discipline in config["disciplines"]:
        run("discipline:" + discipline, lambda key=discipline: review_domain(document, key))
    if not config["disciplines"]:
        modules["specialist"] = entry("not_requested", reason="No specialist profile selected; common checks remain available.")
    run("citations", lambda: verify_document_dois(document, online=online, timeout=6, limit=20))
    citations = modules["citations"]
    if online and citations["result"] is not None and any(
        item["status"] == "UNVERIFIED" for item in citations["result"]["results"]
    ):
        citations["status"] = "failed"
        citations["reason"] = "One or more requested DOI lookups did not complete verification; inspect the preserved DOI results."
    if send_to_model:
        with ExitStack() as stack:
            model_path = visual_path
            if visual_bytes is not None:
                folder = stack.enter_context(tempfile.TemporaryDirectory(prefix="sra-unified-vision-"))
                model_path = Path(folder) / "source.pdf"
                model_path.write_bytes(visual_bytes)
            run("model", lambda: review_parsed_paper(
                document, model=model, base_url=base_url, api_key_env=api_key_env,
                timeout=timeout, chunk_chars=chunk_chars, visual_pages=visual_pages,
                visual_path=model_path))
        if modules["model"]["status"] == "completed" and study_type in ("theoretical", "narrative-review"):
            findings = modules["model"]["result"].get("rule_based_findings", [])
            modules["model"]["result"]["rule_based_findings"] = [
                item for item in findings if item["check_id"] not in EMPIRICAL_STRUCTURE
            ]
            excluded.extend({"module": "model", "finding": item,
                             "reason": "Empirical section-heading expectation does not apply to the declared study type."}
                            for item in findings if item["check_id"] in EMPIRICAL_STRUCTURE)
    else:
        modules["model"] = entry("not_requested", reason="External manuscript transmission was not requested.")
    gaps = ["raw_data_not_validated", "analysis_code_not_reexecuted", "mathematical_proofs_not_verified",
            "exact_citation_claim_support_not_verified", "figures_and_supplements_not_verified",
            "independent_expert_validation_not_established"]
    if not config["disciplines"]:
        gaps.append("specialist_profile_not_selected")
    if statistics_spec is not None or scientific_spec is not None:
        gaps.append("supplied_quantitative_values_not_independently_linked_to_manuscript")
    gaps.append("formalization_semantics_not_verified" if prepared_logic is not None else "formal_logic_not_requested")
    if document.extraction_details.get("pages_without_extractable_text"):
        gaps.append("pdf_pages_without_extracted_text")
    return {
        "schema_version": REPORT_SCHEMA, "source": document.source,
        "source_sha256": document.sha256, "extracted_text_sha256": text_digest,
        "execution_status": "partial" if any(item["status"] in ("failed", "unavailable") for item in modules.values()) else "complete",
        "execution_scope": "Requested module execution only; not scientific quality or validity.",
        "configuration": config, "capability_contract_sha256": catalog["contract_sha256"],
        "applicability": {"version": catalog["applicability_version"], "declared_study_type": study_type,
                          "review_required": study_type in ("unknown", "mixed"),
                          "note": "Study type and profile selection are caller declarations requiring human confirmation."},
        "modules": modules, "excluded_findings": excluded, "coverage_gaps": gaps,
        'criteria_matrix': build_criteria_matrix(study_type, modules, document.sha256, text_digest,
                                                prepared_toolkit['checks'] if prepared_toolkit is not None else (),
                                                requested_scientific_kinds),
        "reproducibility_manifest": reasoning["reproducibility_manifest"],
        "limitations": catalog["limitations"],
    }
