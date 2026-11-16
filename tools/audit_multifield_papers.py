"""Frozen finite-frame real-paper execution audit; no scientific accuracy labels."""
from __future__ import annotations

import argparse
import copy
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

FOLDER = Path(__file__).resolve().parents[1] / "benchmarks/pilots/multifield-20261116"
SEED = "85908ff2a73ec626b0b63caa6adf0199bc94be9bd5c89bd79f5fed6872471590"
QUERY = ('journal_key:PLoSONE AND doc_type:full AND article_type:"Research Article" '
         'AND publication_date:[2024-01-01T00:00:00Z TO 2024-01-31T23:59:59Z]')
PREFIXES = (
    ("physics", "/Physical sciences/Physics"),
    ("chemistry", "/Physical sciences/Chemistry"),
    ("computing", "/Computer and information sciences"),
    ("animal", "/Biology and life sciences/Zoology"),
    ("social-science", "/Social sciences"),
    ("clinical", "/Medicine and health sciences"),
)
MAX_BYTES = 16 * 1024 * 1024


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8") + b"\n"


def save(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "SRA-finite-frame-audit/1.0"})
    with urllib.request.urlopen(request, timeout=60) as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Source exceeds the bounded capture size.")
    return raw


def assign(subjects):
    if not isinstance(subjects, list) or not all(isinstance(s, str) for s in subjects):
        raise ValueError("Missing/malformed source subject paths.")
    for field, prefix in PREFIXES:
        if any(s == prefix or s.startswith(prefix + "/") for s in subjects):
            return field
    return None


def select(pages):
    """Reject incomplete/duplicate pages before returning any selection."""
    docs, total = [], None
    for page in pages:
        response = page["response"]
        count = response["numFound"]
        if type(count) is not int or count < 0:
            raise ValueError("Invalid frame size.")
        if total is not None and count != total:
            raise ValueError("Frame size changed while capturing pages.")
        total = count
        if response["start"] != len(docs):
            raise ValueError("Noncontiguous frame pages.")
        docs.extend(response["docs"])
    if total is None or len(docs) != total:
        raise ValueError("Incomplete frame; do not sample.")
    ids = [d["id"] for d in docs]
    if len(set(ids)) != len(ids) or ids != sorted(ids):
        raise ValueError("Duplicate or unsorted DOI frame.")
    ranked = {field: [] for field, _ in PREFIXES}
    rows = []
    for doc in docs:
        doi = doc["id"]
        if not re.fullmatch(r"10\.1371/journal\.pone\.\d+", doi):
            raise ValueError("Unexpected publisher DOI.")
        field = assign(doc.get("subject"))
        rank = sha((SEED + "\n" + str(field) + "\n" + doi).encode()) if field else None
        row = dict(doc, stratum=field, selection_priority_sha256=rank)
        rows.append(row)
        if field:
            ranked[field].append(row)
    selected, strata = [], []
    for field, _ in PREFIXES:
        group = sorted(ranked[field], key=lambda r: (r["selection_priority_sha256"], r["id"]))
        chosen = group[:2]
        selected.extend(chosen)
        strata.append(dict(stratum=field, frame_size=len(group), sample_size=len(chosen),
                           sampling_fraction=len(chosen) / len(group) if group else None))
    return dict(schema_version="multifield-frame/1.0", query=QUERY, seed=SEED,
                frame_size=len(rows), unmatched=sum(r["stratum"] is None for r in rows),
                strata=strata, records=rows, selected=selected)


def capture():
    """Explicit online acquisition. Never call the auditor or replace failures."""
    if (FOLDER / "selection.json").exists():
        raise FileExistsError("A selection already exists; preserve its source snapshot.")
    pages, evidence, start = [], [], 0
    while True:
        url = "https://api.plos.org/search?" + urllib.parse.urlencode(dict(
            q=QUERY, rows=1000, start=start, sort="id asc", wt="json",
            fl="id,title_display,publication_date,subject,author_display"))
        raw = fetch(url)
        page = json.loads(raw)
        save(FOLDER / "frame" / f"page-{start:04d}.json", raw)
        evidence.append(dict(url=url, sha256=sha(raw), bytes=len(raw), start=start))
        pages.append(page)
        response = page["response"]
        start += len(response["docs"])
        if start >= response["numFound"]:
            break
        if not response["docs"]:
            raise ValueError("Frame pagination made no progress.")
    result = select(pages)
    result.update(raw_pages=evidence, protocol_sha256=sha((FOLDER / "protocol.md").read_bytes()))
    save(FOLDER / "selection.json", encoded(result))
    print(json.dumps(dict(frame_size=result["frame_size"], unmatched=result["unmatched"],
                          strata=result["strata"], selected=[(r["stratum"], r["id"], r["title_display"])
                          for r in result["selected"]]), ensure_ascii=True, indent=2))


def text(node):
    """Separate block/cell content without breaking ordinary inline words."""
    if node is None:
        return ""
    blocks = {"p", "sec", "title", "td", "th", "tr", "label", "list-item",
              "ref", "table", "table-wrap", "caption", "abstract", "disp-formula",
              "alternatives", "tex-math"}
    def emit(element):
        tag = element.tag.rsplit("}", 1)[-1]
        value = element.text or ""
        for child in element:
            child_tag = child.tag.rsplit("}", 1)[-1]
            inner = emit(child)
            if child_tag == "sup":
                inner = "^(" + inner + ")"
            elif child_tag == "sub":
                inner = "_(" + inner + ")"
            elif child_tag in blocks:
                inner = " " + inner + " "
            value += inner + (child.tail or "")
        return value
    return " ".join(emit(node).split())


def normalize(raw, doi):
    """Retain complete abstract/body/back text, tables, captions and equations."""
    if b"<!ENTITY" in raw.upper():
        raise ValueError("Entity declarations are not supported.")
    root = ET.fromstring(raw)
    if root.tag != "article":
        raise ValueError("Expected publisher JATS article.")
    meta = root.find("./front/article-meta")
    if meta is None or root.find("body") is None or not text(root.find("body")):
        raise ValueError("Incomplete JATS front/body.")
    dois = [text(n).lower() for n in meta.findall("article-id") if n.get("pub-id-type") == "doi"]
    if doi not in dois:
        raise ValueError("Downloaded article DOI differs from selected DOI.")
    license_node = meta.find("./permissions/license")
    license_text = text(license_node)
    urls = [v for n in license_node.iter() for v in n.attrib.values()] if license_node is not None else []
    # PLOS JATS often names the full license without a URI. Record the exact
    # article-specific grant, never confuse Attribution with NonCommercial/ND.
    explicit_url = next((u for u in urls if re.fullmatch(
        r"https?://creativecommons\.org/(?:licenses/by/(?:[234]\.0)|publicdomain/zero/1\.0)/?", u)), None)
    explicit_grant = ("Creative Commons Attribution License" in license_text
                      and "unrestricted use, distribution, and reproduction" in license_text
                      and "NonCommercial" not in license_text and "NoDerivatives" not in license_text)
    if not (explicit_url or explicit_grant):
        raise ValueError("No confirmed article-specific permissive redistribution grant.")
    title = text(meta.find("./title-group/article-title"))
    chunks = ["# " + title, "", "DOI: " + doi, ""]
    for abstract in meta.findall("abstract"):
        chunks.extend(["## Abstract", "", text(abstract), ""])
    def render(node, depth=2):
        if node.tag == "sec":
            heading = text(node.find("title"))
            if heading:
                chunks.extend(["#" * min(depth, 6) + " " + heading, ""])
            for child in node:
                if child.tag != "title":
                    render(child, depth + 1)
        elif node.tag in ("body", "back"):
            for child in node:
                render(child, depth)
        else:
            value = text(node)
            if value:
                if node.tag in ("ref-list", "ack", "fn-group", "app-group"):
                    chunks.extend(["## " + {"ref-list": "References", "ack": "Acknowledgments",
                        "fn-group": "Notes", "app-group": "Appendices"}[node.tag], ""])
                chunks.extend([value, ""])
    render(root.find("body"))
    if root.find("back") is not None:
        render(root.find("back"))
    authors = [text(n) for n in meta.findall("./contrib-group/contrib") if n.get("contrib-type") == "author"]
    return "\n".join(chunks).encode("utf-8"), dict(title=title, authors=authors,
        license_text=license_text, explicit_license_url=explicit_url,
        permission_basis="article-specific JATS permission, preserved verbatim",
        body_elements=sum(1 for _ in root.find("body").iter()),
        text_scope="Complete title/abstract/body/back text; inline notation and tables flattened; "
                   "linked figure images and supplements not reviewed; not a human whole-paper reading.")


def sources():
    selection = json.loads((FOLDER / "selection.json").read_bytes())
    records = []
    for row in selection["selected"]:
        doi = row["id"]
        name = doi.rsplit(".", 1)[1]
        url = "https://journals.plos.org/plosone/article/file?" + urllib.parse.urlencode(
            dict(id=doi, type="manuscript"))
        record = dict(doi=doi, stratum=row["stratum"], source_url=url,
                      publisher_url="https://journals.plos.org/plosone/article?id=" + doi,
                      status="unavailable", human_full_reading=False, human_labels=None)
        try:
            raw = fetch(url)
            record.update(captured_sha256=sha(raw), captured_bytes=len(raw))
            # Publish originals only after checking their article-specific grant.
            markdown, info = normalize(raw, doi)
            original = f"sources/{name}.xml"
            derived = f"texts/{name}.md"
            save(FOLDER / original, raw)
            save(FOLDER / derived, markdown)
            record.update(info, status="available", original=original,
                          original_sha256=sha(raw), original_bytes=len(raw),
                          text=derived, text_sha256=sha(markdown), text_bytes=len(markdown))
        except (OSError, ValueError, ET.ParseError) as exc:
            record.update(failure_type=type(exc).__name__, failure=str(exc)[:500])
        records.append(record)
        print(json.dumps(dict(doi=doi, stratum=row["stratum"], status=record["status"],
                              text_bytes=record.get("text_bytes"), failure=record.get("failure"))), flush=True)
    save(FOLDER / "sources.json", encoded(dict(
        selection_sha256=sha((FOLDER / "selection.json").read_bytes()), papers=records)))


def stable(report):
    """Semantic projection only; raw reports are always preserved unmodified.

    Exclude timestamps and display paths at enumerated schema pointers.
    Never drop graph edge 'source' endpoints or source identity hashes.
    """
    result = copy.deepcopy(report)
    result["source"] = "<MANUSCRIPT_PATH>"
    for name in ("reasoning", "writing"):
        module = result.get("modules", {}).get(name, {}).get("result")
        if isinstance(module, dict) and "source" in module:
            module["source"] = "<MANUSCRIPT_PATH>"
    manifests = [result.get("reproducibility_manifest")]
    reasoning = result.get("modules", {}).get("reasoning", {}).get("result")
    if isinstance(reasoning, dict):
        manifests.append(reasoning.get("reproducibility_manifest"))
    for manifest in manifests:
        if isinstance(manifest, dict):
            manifest.pop("generated_at_utc", None)
            if isinstance(manifest.get("input"), dict):
                manifest["input"]["filename"] = "<MANUSCRIPT_PATH>"
    return result


def execute_paper(row, out):
    """Retain both raw runs and any failure; never drop later selected papers."""
    from sra.document import load_document
    from sra.review import review_document
    from sra.review_report import review_markdown
    from sra.domain_adjudication import make_domain_template

    item = dict(doi=row["doi"], stratum=row["stratum"], source_status=row["status"],
                scientific_accuracy=None, human_labels=None, human_full_reading=False)
    if row["status"] != "available":
        item["failure"] = row.get("failure")
        return item
    name = row["doi"].rsplit(".", 1)[1]
    try:
        document = load_document(FOLDER / row["text"])
        options = dict(disciplines=[row["stratum"]], study_type="unknown",
                       style_language="none", prepare_inputs=True, online=False)
        report = review_document(document, **options)
        save(out / "papers" / (name + ".json"), encoded(report))
        save(out / "papers" / (name + ".md"), review_markdown(report).encode("utf-8"))
        item.update(source_sha256=document.sha256, first_report_sha256=sha(encoded(report)))
        repeated = review_document(document, **options)
        save(out / "repeated" / (name + ".json"), encoded(repeated))
        equal = stable(report) == stable(repeated)
        item.update(repeat_equal=equal, repeat_report_sha256=sha(encoded(repeated)))
        matrix = report["criteria_matrix"]
        if any(c["scientific_verdict"] != "NOT_ASSESSED" for c in matrix["criteria"]):
            raise ValueError("Unexpected scientific verdict in execution-only audit.")
        profile = report["modules"]["discipline:" + row["stratum"]]
        preparation = report["modules"].get("preparation", {}).get("result") or {}
        item.update(requested_module_execution_status=report["execution_status"],
            execution_status=report["execution_status"] if equal else "repeat_mismatch",
            criteria_summary=matrix["summary"],
            profile_states=dict(Counter(c["status"] for c in (profile["result"] or {}).get("items", []))),
            preparation_candidates=dict(Counter(c["kind"] for c in preparation.get("candidates", []))),
            suggested_checks=sum(c.get("suggested_check") is not None for c in preparation.get("candidates", [])),
            module_states={k: v["status"] for k, v in report["modules"].items()},
            semantic_report_sha256=sha(encoded(stable(report))))
        template = make_domain_template(document, row["stratum"])
        save(out / "blank-review-forms" / (name + ".json"), encoded(template))
        if not equal:
            item["failure"] = "First and repeated semantic reports differ; both raw reports retained."
    except (ImportError, OSError, ValueError, RuntimeError, TypeError) as exc:
        item.update(execution_status="failed", failure_type=type(exc).__name__, failure=str(exc)[:500])
    return item


def run(out):
    import sra
    out = Path(out)
    repository = Path(__file__).resolve().parents[1]
    if out.resolve().is_relative_to(repository):
        raise ValueError("Write audit outputs outside the repository; output files alter repository provenance.")
    if out.exists():
        raise FileExistsError("Choose a fresh output directory; first runs are immutable.")
    selection_raw = (FOLDER / "selection.json").read_bytes()
    selection = json.loads(selection_raw)
    pages = [json.loads((FOLDER / "frame" / f"page-{p['start']:04d}.json").read_bytes())
             for p in selection["raw_pages"]]
    for p in selection["raw_pages"]:
        if sha((FOLDER / "frame" / f"page-{p['start']:04d}.json").read_bytes()) != p["sha256"]:
            raise ValueError("Frozen frame bytes changed.")
    rebuilt = select(pages)
    if rebuilt["selected"] != selection["selected"] or rebuilt["records"] != selection["records"]:
        raise ValueError("Frozen selection differs from reproducible sampling.")
    if sha((FOLDER / "protocol.md").read_bytes()) != selection["protocol_sha256"]:
        raise ValueError("Frozen protocol changed.")
    inventory = json.loads((FOLDER / "sources.json").read_bytes())
    if inventory["selection_sha256"] != sha(selection_raw):
        raise ValueError("Source inventory refers to another selection.")
    expected = [(r["id"], r["stratum"]) for r in selection["selected"]]
    if [(r["doi"], r["stratum"]) for r in inventory["papers"]] != expected:
        raise ValueError("Dropped, reordered or substituted selected paper.")
    # Validate every available source BEFORE emitting any output.
    for row in inventory["papers"]:
        if row["status"] != "available":
            continue
        raw = (FOLDER / row["original"]).read_bytes()
        md = (FOLDER / row["text"]).read_bytes()
        if sha(raw) != row["original_sha256"] or sha(md) != row["text_sha256"]:
            raise ValueError("Frozen source/text bytes changed.")
        if normalize(raw, row["doi"])[0] != md:
            raise ValueError("Normalized source is not a complete reproducible JATS derivation.")
    results = [execute_paper(row, out) for row in inventory["papers"]]
    package = Path(sra.__file__).resolve().parent
    runtime = {p.relative_to(package).as_posix(): sha(p.read_bytes()) for p in sorted(package.rglob("*"))
               if p.is_file() and (p.suffix == ".py" or p.name == "py.typed")}
    summary = dict(schema_version="multifield-execution/1.0", engine_version=sra.__version__,
        python=platform.python_version(), platform=platform.platform(),
        protocol_sha256=selection["protocol_sha256"], selection_sha256=sha(selection_raw),
        inventory_sha256=sha((FOLDER / "sources.json").read_bytes()),
        producer_sha256=sha(Path(__file__).read_bytes()), runtime_source_files=runtime,
        clarification_sha256=sha((FOLDER / "normalization-and-replay-clarification.md").read_bytes()),
        semantic_comparison="Exact findings/results/hashes; only enumerated timestamps/display paths excluded. Raw reports retained.",
        frame_size=selection["frame_size"], unmatched=selection["unmatched"], strata=selection["strata"],
        selected=len(results), available=sum(r["source_status"] == "available" for r in results),
        completed=sum(r.get("execution_status") == "complete" for r in results),
        requested_modules_complete=sum(r.get("requested_module_execution_status") == "complete" for r in results),
        repeat_equal=sum(r.get("repeat_equal") is True for r in results),
        new_human_labels=0, scientific_accuracy=None, papers=results,
        scope="Prospective six-stratum finite-frame full-text execution audit; not scientific-error accuracy.",
        limitations=["One publisher and one month; not representative of all science.",
                     "Equal stratum allocation is not a self-weighted population sample.",
                     "Taxonomy and profile applicability require human confirmation.",
                     "Machine-ingested full text is not an expert or human whole-paper review.",
                     "Flattened equations/tables; linked figures and supplements not verified.",
                     "No independent human gold labels; precision, recall and scientific accuracy not estimated."])
    save(out / "summary.json", encoded(summary))
    lines = ["# Multi-field real-paper execution audit", "", summary["scope"], "",
             f"Selected: {summary['selected']}; full texts available: {summary['available']}; "
             f"requested execution complete: {summary['completed']}; repeat agreement: {summary['repeat_equal']}.",
             "Scientific-error accuracy: not estimated. New human labels: 0.", "",
             "| Stratum | Frame | Selected | Fraction |", "| --- | ---: | ---: | ---: |"]
    for row in summary["strata"]:
        lines.append(f"| {row['stratum']} | {row['frame_size']} | {row['sample_size']} | {row['sampling_fraction']} |")
    lines += ["", "| DOI | Stratum | Source | Execution |", "| --- | --- | --- | --- |"]
    for row in results:
        lines.append(f"| {row['doi']} | {row['stratum']} | {row['source_status']} | {row.get('execution_status', 'not_run')} |")
    lines += ["", "## Limits", "", *("- " + value for value in summary["limitations"]), ""]
    save(out / "summary.md", "\n".join(lines).encode())
    print(json.dumps({k: summary[k] for k in ("selected", "available", "completed", "repeat_equal", "scientific_accuracy")}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "sources", "run"))
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.action == "run":
        if args.out is None:
            parser.error("run requires a fresh --out directory")
        run(args.out)
    else:
        if args.out is not None:
            parser.error("--out is only for offline run")
        {"capture": capture, "sources": sources}[args.action]()


if __name__ == "__main__":
    main()
