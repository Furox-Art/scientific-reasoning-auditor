"""Source-frozen evaluation of rule-based language prompts on human-revised science.

Evaluation unit: one arXivEdits annotated source/revision pair.
The binary reference label indicates *annotation of a language-motivated edit*,
not whether the unedited sentence is grammatically right or wrong.
Results are conditional on this edit-enriched corpus. No invented labels.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import io
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from sra.document import ParsedDocument
from sra.writing_style import style_review

REQUIRED_COLUMNS = (
    "id", "sentence-1", "sentence-2", "arxiv-id",
    "edits-combination-0", "edits-combination-1", "edits-combination-2",
)
LANGUAGE_INTENT_PREFIXES = ("Lang-", "Improve-grammar")
MAX_CORPUS_BYTES = 10_000_000
MAX_SUGGESTIONS_PER_SAMPLE = 50
EXCLUDED_ADVISORY_CODES = frozenset({"long_line", "statistical_language"})


def _wilson(success: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.959963984540054
    p = success / total
    d = 1 + z * z / total
    center = (p + z * z / (2 * total)) / d
    spread = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / d
    return [max(0.0, center - spread), min(1.0, center + spread)]


def _ratio(numer: int, denom: int) -> float | None:
    return numer / denom if denom else None


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _parse_annotation(cell: str) -> list[str]:
    if len(cell) > 25_000:
        raise ValueError("Edit annotation cell exceeds the size limit.")
    parsed = ast.literal_eval(cell)
    if not isinstance(parsed, dict):
        raise ValueError("Each edit annotation must be a dictionary.")
    if len(parsed) > 200:
        raise ValueError("Too many edits in a single annotation combination.")
    out = []
    for edit in parsed.values():
        if not isinstance(edit, dict):
            raise ValueError("Malformed human edit annotation.")
        intention = edit.get("intention")
        if intention is None:
            continue
        if not isinstance(intention, str):
            raise ValueError("Annotation intention must be a string or null.")
        out.append(intention)
    return out


def _style_suggestions(sentence: str) -> list[dict[str, Any]]:
    synthetic = ParsedDocument(
        source="<benchmark-input>",
        text=sentence,
        sha256=hashlib.sha256(sentence.encode("utf-8")).hexdigest(),
        sections={"Excerpt": sentence},
        section_start_lines={"Excerpt": 1},
        input_format="benchmark sentence",
        source_size_bytes=len(sentence.encode("utf-8")),
        parser_backend="benchmark",
    )
    suggestions = style_review(
        synthetic, language="en", long_sentence_words=200,
    )
    if len(suggestions) > MAX_SUGGESTIONS_PER_SAMPLE:
        raise ValueError("Excessive suggestions from a single sentence.")
    return suggestions


def evaluate_arxiv_edit_pairs(
    path: str | Path, *,
    expected_sha256: str | None = None,
    max_rows: int = 2000,
) -> dict[str, Any]:
    """Evaluate all rows in a frozen arXivEdits annotated split.

    Labels are intent categories assigned to *revisions*. A negative means no
    language edit is annotated among those particular revision annotations,
    NOT proof that the sentence is grammatically correct. Do not interpret
    conditional rates as general editing accuracy or expertise.
    """
    if type(max_rows) is not int or max_rows < 1 or max_rows > 100_000:
        raise ValueError("max_rows must be an integer from 1 to 100000.")
    raw = Path(path).read_bytes()
    if not raw or len(raw) > MAX_CORPUS_BYTES:
        raise ValueError("Corpus must be nonempty and at most 10 MB.")
    sha = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None:
        if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
            raise ValueError("Expected SHA-256 must be 64 lowercase hex characters.")
        if sha != expected_sha256:
            raise ValueError("Corpus SHA-256 differs from the frozen expected hash.")

    frozen_test_sha = "6541dce4c7f82019e8f24dc0259a1a04e20dd853d87b465adeb1febc2cbf0220"
    is_frozen_test = sha == frozen_test_sha
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    if (reader.fieldnames is None or
            not set(REQUIRED_COLUMNS).issubset(reader.fieldnames) or
            len(reader.fieldnames) != len(set(reader.fieldnames))):
        raise ValueError("Unrecognized arXivEdits annotated CSV schema.")
    seen = set()
    counts = Counter()
    intent_counts: Counter[str] = Counter()
    sample_count = 0
    paper_ids = set()
    rule_hits: Counter[str] = Counter()
    exact_candidates = 0
    target_agreements = 0
    examples_of_nonmatches = []
    positive_with_suggestion = 0
    negative_with_suggestion = 0

    for row in reader:
        if sample_count >= max_rows:
            raise ValueError(
                "Corpus has more rows than max_rows; increase the limit rather "
                "than silently evaluating a biased prefix."
            )
        if any(key is None for key in row):
            raise ValueError("Malformed CSV row.")
        sample_id = row["id"]
        if not isinstance(sample_id, str) or not sample_id or sample_id in seen:
            raise ValueError("Every benchmark row needs a unique, nonempty ID.")
        seen.add(sample_id)
        source, target = row["sentence-1"], row["sentence-2"]
        paper_id = row["arxiv-id"]
        if (not isinstance(source, str) or not source.strip() or
                not isinstance(target, str) or not target.strip() or
                not isinstance(paper_id, str) or not paper_id.strip()):
            raise ValueError("Missing revision/source/article identifier.")
        if source == target:
            raise ValueError("Annotated edit pair contains identical sentences.")
        if len(source) > 10000 or len(target) > 10000:
            raise ValueError("Unreasonably long sentence input.")
        intentions = []
        for col in REQUIRED_COLUMNS[4:]:
            intentions.extend(_parse_annotation(row[col]))
        if not intentions:
            raise ValueError("No original human revision annotation found.")
        intent_counts.update(intentions)
        human_language_edit = any(
            intent.startswith(LANGUAGE_INTENT_PREFIXES)
            for intent in intentions
        )
        suggestions = _style_suggestions(source)
        triggered = len(suggestions) > 0
        if human_language_edit:
            counts["positives"] += 1
            if triggered:
                counts["tp"] += 1
                positive_with_suggestion += 1
            else:
                counts["fn"] += 1
        else:
            counts["nonlanguage_revisions"] += 1
            if triggered:
                counts["fp_proxy"] += 1
                negative_with_suggestion += 1
            else:
                counts["tn_proxy"] += 1

        for suggestion in suggestions:
            rule_hits[suggestion["code"]] += 1
            if suggestion["code"] in EXCLUDED_ADVISORY_CODES:
                continue
            replacement = suggestion["suggestion"]
            excerpt = suggestion["excerpt"]
            if not replacement or not excerpt:
                continue
            exact_candidates += 1
            if (_normalized(replacement) in _normalized(target) and
                    _normalized(excerpt) not in _normalized(target)):
                target_agreements += 1
            elif len(examples_of_nonmatches) < 10:
                examples_of_nonmatches.append({
                    "sample_id": sample_id,
                    "arxiv_id": paper_id,
                    "rule": suggestion["code"],
                    "reason": "Replacement not present as an exact normalized string in target.",
                })
        paper_ids.add(paper_id)
        sample_count += 1

    if not sample_count:
        raise ValueError("No annotated examples.")
    if not counts["positives"] or not counts["nonlanguage_revisions"]:
        raise ValueError("Need both language-tagged and other-revision examples.")

    tp, fp = counts["tp"], counts["fp_proxy"]
    fn, tn = counts["fn"], counts["tn_proxy"]
    return {
        "schema_version": "1.0",
        "kind": "observed_human_revision_intent_detection",
        "corpus": (
            "arXivEdits annotated scientific revision test split"
            if is_frozen_test else "User-provided annotated revision CSV (provenance not verified)"
        ),
        "corpus_url": "https://huggingface.co/datasets/miwytt/arXivEdits_edits",
        "paper": "https://aclanthology.org/2022.emnlp-main.641/",
        "verified_dataset_revision": (
            "3fdba9ce77468272ed4c32bcf3f9f38983ed57be"
            if is_frozen_test else None
        ),
        "split": "test" if is_frozen_test else "unverified",
        "pinned_source_url": (
            "https://huggingface.co/datasets/miwytt/arXivEdits_edits/resolve/"
            "3fdba9ce77468272ed4c32bcf3f9f38983ed57be/edits/test.csv"
            if is_frozen_test else None
        ),
        "source_csv_sha256": sha,
        "rows_evaluated": sample_count,
        "unique_papers": len(paper_ids),
        "source_edits_by_intent": dict(sorted(intent_counts.items())),
        "annotation_label_rule": (
            "Positive if at least one annotated edit intention begins "
            "'Lang-' or 'Improve-grammar'; negative proxy otherwise."
        ),
        "detector": "SRA offline style_review(language=en), default patterns",
        "confusion_matrix_against_revision_intents": {
            "tp": tp, "fp_proxy": fp, "fn": fn, "tn_proxy": tn,
        },
        "conditional_detection": {
            "positive_recall": _ratio(tp, tp + fn),
            "positive_recall_ci95_wilson": _wilson(tp, tp + fn),
            "precision_proxy": _ratio(tp, tp + fp),
            "precision_proxy_ci95_wilson": _wilson(tp, tp + fp),
            "nonlanguage_revision_specificity_proxy": _ratio(tn, tn + fp),
            "nonlanguage_revision_specificity_ci95_wilson": _wilson(tn, tn + fp),
        },
        "suggested_replacements": {
            "machine_string_substitution_candidates": exact_candidates,
            "exact_normalized_matches_in_human_target": target_agreements,
            "exact_target_agreement_fraction": _ratio(target_agreements, exact_candidates),
            "exact_target_agreement_ci95_wilson": _wilson(target_agreements, exact_candidates),
            "note": (
                "Literal phrase agreement only; different but acceptable human "
                "rewrites are marked as nonmatches. This is NOT correction correctness."
            ),
        },
        "rule_trigger_counts": dict(sorted(rule_hits.items())),
        "inspection_cases_without_text": examples_of_nonmatches,
        "limitations": [
            "The dataset includes edited scientific sentences, not a random sample of all manuscript sentences.",
            "Only annotations attached to these human revisions are observed. A no-language-edit tag is NOT a verified grammar-correct negative.",
            "Scientific revisions and language edits may coexist in a single example; original editors can disagree and edits can be subjective.",
            "The figures are conditional revision-intent agreement; they are not full real-manuscript grammar accuracy, error-free precision or peer-reviewed validation.",
            "The selected mirror and its SHA-256 are recorded; no copyrighted source/target sentences or human edits are redistributed in the report.",
            "Confidence intervals use sentence-level Wilson bounds and do not adjust for clustering within papers.",
            "The optional local LanguageTool integration is not evaluated here; only the built-in offline rules are evaluated.",
        ],
    }
