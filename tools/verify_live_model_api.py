"""Opt-in real model-provider smoke test on a PUBLICLY SHAREABLE synthetic paper.

No credentials are printed or saved, and no user manuscript is transmitted.
Runs two model requests (one text chunk and one whole-paper synthesis).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from sra.paper_review import paper_review_markdown, review_paper

SYNTHETIC_MANUSCRIPT = """# Abstract
A synthetic observational experiment compared two imagined groups. No human
subjects or private research data were used. The fictitious study reports a
descriptive change, not evidence of cause and effect.

# Methods
The demonstration sample contains 20 illustrative values in Group A and
20 illustrative values in Group B. There is no randomization statement.
The values and findings are invented solely to exercise a software pipeline.

# Results
The hypothetical summary was 2.1 in Group A and 2.4 in Group B.
These descriptive values are not a scientific discovery.

# Discussion
The evidence cannot establish causation, real-world generalizability,
statistical significance, or independent replication.
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="https://api.openai.com/v1")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument(
        "--confirm-send-synthetic", action="store_true",
        help="Explicitly authorize upload of synthetic non-confidential paper text.",
    )
    options = parser.parse_args(argv)
    if not options.confirm_send_synthetic:
        parser.error("Explicit --confirm-send-synthetic consent is required before network requests.")
    if not os.environ.get(options.api_key_env):
        print(
            f"LIVE_API_NOT_TESTED: {options.api_key_env} is not configured; no request was sent.",
            file=sys.stderr,
        )
        return 3
    with tempfile.TemporaryDirectory(prefix="sra-live-model-") as directory:
        path = Path(directory) / "synthetic_public_test.md"
        path.write_text(SYNTHETIC_MANUSCRIPT, encoding="utf-8")
        report = review_paper(
            path, model=options.model, base_url=options.base_url,
            api_key_env=options.api_key_env, timeout=options.timeout,
        )
        if report["chunk_count"] != report["chunks_reviewed"]:
            raise AssertionError("Not all synthetic manuscript chunks were reviewed.")
        if report["covered_characters"] != len(SYNTHETIC_MANUSCRIPT):
            raise AssertionError("Synthetic manuscript was not fully submitted.")
        if report["source_sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
            raise AssertionError("Source file identity verification failed.")
        for chunk in report["chunk_analyses"]:
            for critique in chunk["critiques"]:
                if critique["quote"] not in SYNTHETIC_MANUSCRIPT:
                    raise AssertionError("Model reported an unsupported quotation.")
        markdown = paper_review_markdown(report)
        if "Whole-paper explanation and scientific assessment" not in markdown:
            raise AssertionError("Model synthesis report did not render.")
        interaction_count = len(report["model_request_provenance"])
        if interaction_count != report["chunk_count"] + 1:
            raise AssertionError("Unexpected request count or partial model output.")
        # Only non-secret, non-manuscript metadata is displayed.
        print(json.dumps({
            "status": "LIVE_PROVIDER_SMOKE_PASSED",
            "source_sha256": report["source_sha256"],
            "requested_model": options.model,
            "response_models": [
                item.get("response_model") for item in report["model_request_provenance"]
            ],
            "chunks": report["chunk_count"],
            "request_count": interaction_count,
            "evidence_quotes_verified_in_source": True,
            "semantic_scientific_validity_verified": False,
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
