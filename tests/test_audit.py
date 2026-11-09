import io
import json
import math
import tempfile
import unittest
from pathlib import Path

from sra.audit import audit_file
from sra.document import load_document
from sra.checks import _direction
from sra.graph import validate_reasoning_graph
from sra.semantic_review import build_semantic_review_template, validate_semantic_review
from sra.report import to_markdown
from sra.stats import verify_stats_file, verify_welch_t_test


class AuditTests(unittest.TestCase):
    def audit_text(self, text: str):
        self._last_source_text = text
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "paper.md"
        path.write_text(text, encoding="utf-8")
        return audit_file(path)

    def build_template(self, report, review_mode: str = "single", source_text: str | None = None):
        manuscript = source_text or getattr(self, "_last_source_text", None)
        if manuscript is None:
            raise AssertionError("Test must provide manuscript source text.")
        return build_semantic_review_template(
            report,
            review_mode=review_mode,
            source_text=manuscript,
        )

    def test_flags_absolute_claim_and_missing_sections(self):
        report = self.audit_text(
            "# Results\nThe treatment is associated with response.\n"
            "# Conclusion\nThis study proves conclusively that treatment causes response."
        )
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("language.absolute_claim", ids)
        self.assertIn("reasoning.correlation_causation_review", ids)
        self.assertIn("structure.methods_missing", ids)
        self.assertIn("structure.limitations_missing", ids)
        self.assertTrue(report.sha256)

    def test_claim_evidence_candidate_is_explicitly_heuristic(self):
        report = self.audit_text(
            "# Methods\nWe used a randomized design.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nOur findings demonstrate that the intervention increased the score."
        )
        self.assertEqual(len(report.claim_evidence_candidates), 1)
        candidate = report.claim_evidence_candidates[0]
        self.assertIn("not verified", candidate.interpretation)
        self.assertEqual(candidate.match_status, "heuristic_candidate")
        self.assertEqual(candidate.claim_line, 6)
        self.assertEqual(candidate.support_line, 4)
        self.assertEqual(candidate.claim_section, "Conclusion")
        self.assertEqual(candidate.support_section, "Results")

    def test_flags_possible_direction_conflict_between_results_and_conclusion(self):
        report = self.audit_text(
            "# Methods\nA randomized experiment was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention decreased the measured score."
        )
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.directional_contradiction", ids)
        relation = next(
            item for item in report.reasoning_map
            if item["relation"] == "possible_directional_contradiction"
        )
        self.assertEqual(relation["status"], "heuristic_review_required")

    def test_weak_lexical_overlap_is_not_presented_as_support(self):
        report = self.audit_text(
            "# Methods\nA protocol was followed.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Discussion\nThe outcome was correlated with a biomarker."
        )
        candidate = report.claim_evidence_candidates[0]
        self.assertLess(candidate.lexical_overlap, 0.15)
        self.assertEqual(candidate.match_status, "unmatched_review_required")

    def test_flags_causal_claim_in_observational_design(self):
        report = self.audit_text(
            "# Methods\nThis was a cross-sectional observational study.\n"
            "# Results\nExposure was associated with the measured outcome.\n"
            "# Conclusion\nThe exposure caused the measured outcome."
        )
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.causal_claim_observational_design", ids)
        finding = next(f for f in report.findings if f.check_id == "reasoning.causal_claim_observational_design")
        self.assertEqual(finding.evidence_locations[1]["section"], "Methods")

    def test_unmatched_conclusion_claim_gets_review_signal(self):
        report = self.audit_text(
            "# Methods\nA standard protocol was followed.\n"
            "# Results\nThe temperature remained stable throughout the experiment.\n"
            "# Conclusion\nOur findings demonstrate that the treatment improves long-term memory."
        )
        candidate = report.claim_evidence_candidates[0]
        self.assertEqual(candidate.match_status, "unmatched_review_required")
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.conclusion_without_lexical_candidate", ids)

    def test_document_parser_keeps_duplicate_headings_and_ignores_fenced_code_headings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.md"
            path.write_text(
                "# Methods\nA protocol was defined.\n"
                "# Results\nFirst endpoint increased.\n"
                "~~~markdown\n~~~python\n# Conclusion\nThis is only a code example.\n~~~\n"
                "# Results\nSecond endpoint decreased.\n"
                "# Conclusion\nThe second endpoint decreased."
            )
            document = load_document(path)
        self.assertIn("Results", document.sections)
        self.assertIn("Results (2)", document.sections)
        self.assertEqual(document.sections["Results"], "First endpoint increased.")
        self.assertEqual(document.sections["Results (2)"], "Second endpoint decreased.")
        self.assertEqual(document.sections["Conclusion"], "The second endpoint decreased.")
        self.assertNotIn("code example", document.sections["Results"])
        self.assertEqual(document.section_start_lines["Results (2)"], 11)
        self.assertEqual(document.section_start_lines["Conclusion"], 13)

    def test_plain_text_conventional_headings_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.txt"
            path.write_text(
                "Methods\nThis was a cross-sectional observational study.\n"
                "Results\nExposure was associated with the outcome.\n"
                "Conclusion\nThe exposure caused the outcome."
            )
            report = audit_file(path)
        self.assertIn("Methods", report.section_names)
        self.assertIn("Results", report.section_names)
        self.assertIn("Conclusion", report.section_names)
        self.assertIn(
            "reasoning.causal_claim_observational_design",
            {finding.check_id for finding in report.findings},
        )

    def test_negated_causal_and_directional_phrases_are_not_treated_as_positive(self):
        causal_negated = self.audit_text(
            "# Methods\nThis was a cross-sectional observational study.\n"
            "# Results\nExposure was associated with the measured outcome.\n"
            "# Conclusion\nThe exposure did not cause the measured outcome."
        )
        ids = {finding.check_id for finding in causal_negated.findings}
        self.assertNotIn("reasoning.causal_claim_observational_design", ids)
        self.assertNotIn("reasoning.correlation_causation_review", ids)
        self.assertFalse(any(
            node["node_type"] == "assumption_gap"
            for node in causal_negated.reasoning_graph["nodes"]
        ))

        directional_negated = self.audit_text(
            "# Methods\nA randomized experiment was conducted.\n"
            "# Results\nThe intervention decreased the measured memory score.\n"
            "# Conclusion\nThe intervention did not increase the measured memory score."
        )
        self.assertNotIn(
            "reasoning.directional_contradiction",
            {finding.check_id for finding in directional_negated.findings},
        )
        self.assertEqual(_direction("The article described the protocol."), 0)
        self.assertEqual(_direction("The intervention did not increase the score."), 0)
        self.assertEqual(
            _direction("The intervention did not increase memory but reduced inflammation."),
            -1,
        )

    def test_non_randomized_wording_is_not_cancelled_by_a_cited_prior_trial(self):
        report = self.audit_text(
            "# Methods\nThis was a non-randomized observational cohort study.\n"
            "A previous randomized controlled trial was also discussed.\n"
            "# Results\nExposure was associated with the outcome.\n"
            "# Conclusion\nThe exposure caused the outcome."
        )
        self.assertIn(
            "reasoning.causal_claim_observational_design",
            {finding.check_id for finding in report.findings},
        )

    def test_manifest_records_source_and_environment_fingerprints(self):
        report = self.audit_text(
            "# Methods\nA test was performed.\n# Results\nThe result was stable."
        )
        manifest = report.reproducibility_manifest
        self.assertEqual(manifest["input"]["sha256"], report.sha256)
        self.assertEqual(
            manifest["input"]["extracted_text_sha256"],
            __import__("hashlib").sha256(
                "# Methods\nA test was performed.\n# Results\nThe result was stable.".encode("utf-8")
            ).hexdigest(),
        )
        self.assertEqual(manifest["input"]["format"], "md")
        self.assertEqual(manifest["manifest_schema_version"], "1.4")
        self.assertEqual(report.schema_version, "1.5")
        self.assertEqual(len(manifest["configuration_sha256"]), 64)
        self.assertEqual(len(manifest["environment_fingerprint"]), 64)
        self.assertEqual(manifest["ruleset_version"], "0.7.0")
        self.assertEqual(manifest["auditor_version"], "0.7.0")
        self.assertEqual(manifest["installed_package_version"], "0.7.0")
        self.assertIn("source_code_revision", manifest)
        self.assertEqual(len(manifest["source_code_sha256"]), 64)
        self.assertIn("Python tests", manifest["source_code_hash_scope"])
        self.assertIn("GitHub Actions workflows", manifest["source_code_hash_scope"])
        self.assertIn("tests/test_audit.py", manifest["source_code_hash_files"])
        self.assertIn(".github/workflows/tests.yml", manifest["source_code_hash_files"])
        self.assertIn("tools/verify_distributions.py", manifest["source_code_hash_files"])
        self.assertEqual(
            manifest["source_code_hash_files"],
            sorted(manifest["source_code_hash_files"]),
        )
        self.assertIn("working_tree_dirty", manifest)
        self.assertIn("scipy", manifest["runtime"]["dependencies"])
        json.dumps(report.to_dict(), ensure_ascii=False)

    def test_distribution_verifier_rejects_duplicate_and_unexpected_archive_entries(self):
        import importlib.util
        import stat
        import tarfile
        import warnings
        import zipfile

        project_root = Path(__file__).resolve().parents[1]
        verifier_path = project_root / "tools" / "verify_distributions.py"
        spec = importlib.util.spec_from_file_location("sra_distribution_verifier", verifier_path)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)

        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)

            for drive_path in (
                "C:/scientific_reasoning_auditor-0.7.0/PKG-INFO",
                "C:relative/scientific_reasoning_auditor-0.7.0/PKG-INFO",
            ):
                with self.subTest(drive_path=drive_path):
                    with self.assertRaisesRegex(SystemExit, "drive-prefixed"):
                        verifier._safe_archive_path(drive_path, "windows-path.tar.gz")

            renamed_root_sdist = temporary / "renamed-root.tar.gz"
            with tarfile.open(renamed_root_sdist, "w:gz") as archive:
                root_entry = tarfile.TarInfo("unexpected-project-root/")
                root_entry.type = tarfile.DIRTYPE
                archive.addfile(root_entry)
                payload = b"Name: scientific-reasoning-auditor\nVersion: 0.7.0\n"
                info = tarfile.TarInfo("unexpected-project-root/PKG-INFO")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            with self.assertRaisesRegex(SystemExit, "does not match canonical project root"):
                verifier._verify_sdist(
                    renamed_root_sdist, project_root, [],
                    "scientific-reasoning-auditor", "0.7.0",
                )

            duplicate_sdist = temporary / "duplicate.tar.gz"
            with tarfile.open(duplicate_sdist, "w:gz") as archive:
                payload = b"Name: scientific-reasoning-auditor\nVersion: 0.7.0\n"
                for _ in range(2):
                    info = tarfile.TarInfo("source/PKG-INFO")
                    info.size = len(payload)
                    archive.addfile(info, io.BytesIO(payload))
            with self.assertRaisesRegex(SystemExit, "duplicate archive member path"):
                verifier._verify_sdist(
                    duplicate_sdist, project_root, [],
                    "scientific-reasoning-auditor", "0.7.0",
                )

            canonical_root = "scientific_reasoning_auditor-0.7.0"
            unexpected_sdist = temporary / "unexpected.tar.gz"
            with tarfile.open(unexpected_sdist, "w:gz") as archive:
                payload = b"Name: scientific-reasoning-auditor\nVersion: 0.7.0\n"
                info = tarfile.TarInfo(f"{canonical_root}/PKG-INFO")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
                extra = b"UNEXPECTED = True\n"
                info = tarfile.TarInfo(f"{canonical_root}/src/sra/unlisted.py")
                info.size = len(extra)
                archive.addfile(info, io.BytesIO(extra))
            with self.assertRaisesRegex(SystemExit, "complete source archive file inventory differs"):
                verifier._verify_sdist(
                    unexpected_sdist, project_root, [],
                    "scientific-reasoning-auditor", "0.7.0",
                )

            setup_payload_sdist = temporary / "setup-payload.tar.gz"
            with tarfile.open(setup_payload_sdist, "w:gz") as archive:
                root_entry = tarfile.TarInfo(f"{canonical_root}/")
                root_entry.type = tarfile.DIRTYPE
                archive.addfile(root_entry)
                payload = b"Name: scientific-reasoning-auditor\nVersion: 0.7.0\n"
                info = tarfile.TarInfo(f"{canonical_root}/PKG-INFO")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
                payload = b"from setuptools import setup\nsetup()\n"
                info = tarfile.TarInfo(f"{canonical_root}/setup.py")
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            with self.assertRaisesRegex(SystemExit, "complete source archive file inventory differs"):
                verifier._verify_sdist(
                    setup_payload_sdist, project_root, [],
                    "scientific-reasoning-auditor", "0.7.0",
                )

            for member_type, label in (
                (tarfile.SYMTYPE, "symlink"),
                (tarfile.LNKTYPE, "hardlink"),
            ):
                with self.subTest(archive_member=label):
                    non_regular_sdist = temporary / f"{label}.tar.gz"
                    with tarfile.open(non_regular_sdist, "w:gz") as archive:
                        root_entry = tarfile.TarInfo("source/")
                        root_entry.type = tarfile.DIRTYPE
                        archive.addfile(root_entry)
                        entry = tarfile.TarInfo("source/src/sra/unlisted.py")
                        entry.type = member_type
                        entry.linkname = "source/PKG-INFO"
                        archive.addfile(entry)
                    with self.assertRaisesRegex(SystemExit, "non-regular archive member is forbidden"):
                        verifier._verify_sdist(
                            non_regular_sdist, project_root, [],
                            "scientific-reasoning-auditor", "0.7.0",
                        )

            payload_directory_sdist = temporary / "directory-payload.tar.gz"
            with tarfile.open(payload_directory_sdist, "w:gz") as archive:
                root_entry = tarfile.TarInfo(f"{canonical_root}/")
                root_entry.type = tarfile.DIRTYPE
                archive.addfile(root_entry)
                directory_entry = tarfile.TarInfo(f"{canonical_root}/src/")
                directory_entry.type = tarfile.DIRTYPE
                directory_entry.size = len(b"hidden-directory-payload")
                archive.addfile(directory_entry, io.BytesIO(b"hidden-directory-payload"))
            with self.assertRaisesRegex(SystemExit, "directory member must be a zero-size directory"):
                verifier._verify_sdist(
                    payload_directory_sdist, project_root, [],
                    "scientific-reasoning-auditor", "0.7.0",
                )

            duplicate_wheel = temporary / "duplicate.whl"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(duplicate_wheel, "w") as archive:
                    archive.writestr("sra/__init__.py", b"")
                    archive.writestr("sra/__init__.py", b"")
            with self.assertRaisesRegex(SystemExit, "duplicate wheel member path"):
                verifier._verify_wheel(
                    duplicate_wheel, project_root,
                    "scientific-reasoning-auditor", "0.7.0",
                )

            disguised_directory_symlink = temporary / "directory-symlink.whl"
            with zipfile.ZipFile(disguised_directory_symlink, "w") as archive:
                symlink_info = zipfile.ZipInfo("sra/")
                symlink_info.create_system = 3
                symlink_info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(symlink_info, "outside-package")
            with self.assertRaisesRegex(SystemExit, "non-directory ZIP type has a directory path"):
                verifier._verify_wheel(
                    disguised_directory_symlink, project_root,
                    "scientific-reasoning-auditor", "0.7.0",
                )

            pth_wheel = temporary / "unexpected-root-pth.whl"
            with zipfile.ZipFile(pth_wheel, "w") as archive:
                archive.writestr("sra/__init__.py", b"VALUE = 1\n")
                archive.writestr("audit_probe.pth", b"import pathlib; pathlib.Path('/tmp/sra-pth-ran').touch()\n")
            symlink_wheel = temporary / "symlink.whl"
            with zipfile.ZipFile(symlink_wheel, "w") as archive:
                archive.writestr("sra/__init__.py", b"VALUE = 1\n")
                symlink_info = zipfile.ZipInfo("sra/injected.py")
                symlink_info.create_system = 3
                symlink_info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(symlink_info, "injected-target.py")
            symlink_root = temporary / "symlink-root"
            (symlink_root / "src" / "sra").mkdir(parents=True)
            (symlink_root / "src" / "sra" / "__init__.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(SystemExit, "non-regular wheel member is forbidden"):
                verifier._verify_wheel(
                    symlink_wheel, symlink_root,
                    "scientific-reasoning-auditor", "0.7.0",
                )

            pth_root = temporary / "pth-root"
            (pth_root / "src" / "sra").mkdir(parents=True)
            (pth_root / "src" / "sra" / "__init__.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(SystemExit, "complete wheel file inventory differs"):
                verifier._verify_wheel(
                    pth_wheel, pth_root,
                    "scientific-reasoning-auditor", "0.7.0",
                )

            wheel_root = temporary / "wheel-root"
            (wheel_root / "src" / "sra").mkdir(parents=True)
            (wheel_root / "src" / "sra" / "__init__.py").write_text(
                "VALUE = 1\n", encoding="utf-8"
            )
            unexpected_wheel = temporary / "unexpected.whl"
            with zipfile.ZipFile(unexpected_wheel, "w") as archive:
                archive.writestr("sra/__init__.py", b"VALUE = 1\n")
                archive.writestr("sra/unlisted.txt", b"unexpected")
            with self.assertRaisesRegex(SystemExit, "complete wheel file inventory differs"):
                verifier._verify_wheel(
                    unexpected_wheel, wheel_root,
                    "scientific-reasoning-auditor", "0.7.0",
                )

    def test_distribution_verifier_rejects_tampered_wheel_entrypoint_and_record(self):
        import base64
        import csv
        import hashlib
        import importlib.util
        import io
        import zipfile

        project_root = Path(__file__).resolve().parents[1]
        verifier_path = project_root / "tools" / "verify_distributions.py"
        spec = importlib.util.spec_from_file_location("sra_distribution_verifier_metadata", verifier_path)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)

        dist_info = "scientific_reasoning_auditor-0.7.0.dist-info"
        sources = {
            path.relative_to(project_root / "src").as_posix(): path.read_bytes()
            for path in sorted((project_root / "src" / "sra").rglob("*.py"))
            if path.is_file()
        }
        # The published wheel carries the PEP 561 marker, so the fixture must
        # carry it too; otherwise the inventory check fires before the metadata
        # check this test is about.
        py_typed = project_root / "src" / "sra" / "py.typed"
        if py_typed.is_file():
            sources["sra/py.typed"] = py_typed.read_bytes()

        def make_wheel(
            path: Path,
            *,
            bad_entrypoint: bool = False,
            bad_record: bool = False,
            extra_wheel_tag: bool = False,
        ) -> None:
            files = dict(sources)
            files[f"{dist_info}/METADATA"] = (
                b"Metadata-Version: 2.1\n"
                b"Name: scientific-reasoning-auditor\n"
                b"Version: 0.7.0\n"
            )
            files[f"{dist_info}/WHEEL"] = (
                b"Wheel-Version: 1.0\n"
                b"Generator: setuptools (78.1.0)\n"
                b"Root-Is-Purelib: true\n"
                b"Tag: py3-none-any\n"
                + (
                    b"Tag: cp312-cp312-win_amd64\n"
                    if extra_wheel_tag
                    else b""
                )
            )
            files[f"{dist_info}/entry_points.txt"] = (
                b"[console_scripts]\nsra = os:system\n"
                if bad_entrypoint
                else b"[console_scripts]\nsra = sra.cli:main\n"
            )
            files[f"{dist_info}/top_level.txt"] = b"sra\n"
            files[f"{dist_info}/licenses/LICENSE"] = (project_root / "LICENSE").read_bytes()

            record = io.StringIO(newline="")
            writer = csv.writer(record, lineterminator="\n")
            for filename, content in sorted(files.items()):
                digest = base64.urlsafe_b64encode(
                    hashlib.sha256(content).digest()
                ).decode("ascii").rstrip("=")
                if bad_record and filename == "sra/__init__.py":
                    digest = "sha256=" + ("A" * 43)
                else:
                    digest = "sha256=" + digest
                writer.writerow((filename, digest, str(len(content))))
            writer.writerow((f"{dist_info}/RECORD", "", ""))
            files[f"{dist_info}/RECORD"] = record.getvalue().encode("utf-8")

            with zipfile.ZipFile(path, "w") as archive:
                for filename, content in files.items():
                    archive.writestr(filename, content)

        bad_entrypoint_wheel = project_root / "tests" / "_bad-entrypoint-test.whl"
        bad_record_wheel = project_root / "tests" / "_bad-record-test.whl"
        bad_tag_wheel = project_root / "tests" / "_bad-tag-test.whl"
        self.addCleanup(lambda: bad_entrypoint_wheel.unlink(missing_ok=True))
        self.addCleanup(lambda: bad_record_wheel.unlink(missing_ok=True))
        self.addCleanup(lambda: bad_tag_wheel.unlink(missing_ok=True))
        make_wheel(bad_entrypoint_wheel, bad_entrypoint=True)
        with self.assertRaisesRegex(SystemExit, "unexpected console entry-point metadata"):
            verifier._verify_wheel(
                bad_entrypoint_wheel, project_root,
                "scientific-reasoning-auditor", "0.7.0",
            )

        make_wheel(bad_record_wheel, bad_record=True)
        with self.assertRaisesRegex(SystemExit, "wheel RECORD hash/size mismatch"):
            verifier._verify_wheel(
                bad_record_wheel, project_root,
                "scientific-reasoning-auditor", "0.7.0",
            )

        make_wheel(bad_tag_wheel, extra_wheel_tag=True)
        with self.assertRaisesRegex(SystemExit, "duplicate WHEEL metadata headers"):
            verifier._verify_wheel(
                bad_tag_wheel, project_root,
                "scientific-reasoning-auditor", "0.7.0",
            )

    def test_distribution_verifier_rejects_wheel_dependency_metadata_mismatch(self):
        import base64
        import csv
        import hashlib
        import importlib.util
        import io
        import tomllib
        import zipfile

        project_root = Path(__file__).resolve().parents[1]
        verifier_path = project_root / "tools" / "verify_distributions.py"
        spec = importlib.util.spec_from_file_location("sra_distribution_verifier_dep_metadata", verifier_path)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        project = tomllib.loads(
            (project_root / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        dist_info = "scientific_reasoning_auditor-0.7.0.dist-info"
        files = {
            path.relative_to(project_root / "src").as_posix(): path.read_bytes()
            for path in sorted((project_root / "src" / "sra").rglob("*.py"))
            if path.is_file()
        }
        # Same reason as the entry-point fixture: mirror the published wheel.
        py_typed = project_root / "src" / "sra" / "py.typed"
        if py_typed.is_file():
            files["sra/py.typed"] = py_typed.read_bytes()
        expected_fields = verifier._expected_metadata_fields(project)
        expected_fields["Requires-Dist"] = [
            *expected_fields["Requires-Dist"],
            "malicious-package>=99",
        ]
        metadata_lines = []
        for field, values in expected_fields.items():
            if values is None:
                continue
            if isinstance(values, list):
                metadata_lines.extend(f"{field}: {value}" for value in values)
            else:
                metadata_lines.append(f"{field}: {values}")
        metadata = (
            "\n".join(metadata_lines)
            + "\n\n"
            + (project_root / "README.md").read_text(encoding="utf-8")
        ).encode("utf-8")
        files[f"{dist_info}/METADATA"] = metadata
        files[f"{dist_info}/WHEEL"] = (
            b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
        )
        files[f"{dist_info}/entry_points.txt"] = b"[console_scripts]\nsra = sra.cli:main\n"
        files[f"{dist_info}/top_level.txt"] = b"sra\n"
        files[f"{dist_info}/licenses/LICENSE"] = (project_root / "LICENSE").read_bytes()

        record = io.StringIO(newline="")
        writer = csv.writer(record, lineterminator="\n")
        for filename, content in sorted(files.items()):
            digest = base64.urlsafe_b64encode(
                hashlib.sha256(content).digest()
            ).decode("ascii").rstrip("=")
            writer.writerow((filename, "sha256=" + digest, str(len(content))))
        writer.writerow((f"{dist_info}/RECORD", "", ""))
        files[f"{dist_info}/RECORD"] = record.getvalue().encode("utf-8")

        malicious_wheel = project_root / "tests" / "_malicious-dependency-test.whl"
        self.addCleanup(lambda: malicious_wheel.unlink(missing_ok=True))
        with zipfile.ZipFile(malicious_wheel, "w") as archive:
            for filename, content in files.items():
                archive.writestr(filename, content)

        with self.assertRaisesRegex(SystemExit, "Requires-Dist metadata differs"):
            verifier._verify_wheel(
                malicious_wheel,
                project_root,
                "scientific-reasoning-auditor",
                "0.7.0",
                expected_project=project,
            )

    def test_distribution_verifier_checks_nested_sdist_pkg_info_metadata(self):
        import importlib.util
        import io
        import tarfile
        import tomllib

        project_root = Path(__file__).resolve().parents[1]
        verifier_path = project_root / "tools" / "verify_distributions.py"
        spec = importlib.util.spec_from_file_location("sra_nested_pkg_info_verifier", verifier_path)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        project = tomllib.loads(
            (project_root / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        name = project["name"]
        version = project["version"]
        source_root = f"{name.replace('-', '_')}-{version}"
        expected_files = verifier._expected_sdist_metadata_files(name, version)
        archive_files = {f"{source_root}/{relative}" for relative in expected_files}
        directories = verifier._expected_directories(archive_files, root=source_root)

        fields = verifier._expected_metadata_fields(project)
        lines = []
        for field, values in fields.items():
            if values is None:
                continue
            if isinstance(values, list):
                lines.extend(f"{field}: {value}" for value in values)
            else:
                lines.append(f"{field}: {values}")
        valid_metadata = (
            "\n".join(lines)
            + "\n\n"
            + (project_root / "README.md").read_text(encoding="utf-8")
        ).encode("utf-8")
        invalid_nested_metadata = (
            valid_metadata.split(b"\n\n", 1)[0]
            + b"\nRequires-Dist: malicious-package>=99\n\n"
            + valid_metadata.split(b"\n\n", 1)[1]
        )

        sdist = project_root / "tests" / "_nested-pkg-info-test.tar.gz"
        self.addCleanup(lambda: sdist.unlink(missing_ok=True))
        nested_pkg_info = f"src/{name.replace('-', '_')}.egg-info/PKG-INFO"
        with tarfile.open(sdist, "w:gz") as archive:
            for directory in sorted(directories):
                info = tarfile.TarInfo(directory + "/")
                info.type = tarfile.DIRTYPE
                archive.addfile(info)
            for relative in sorted(expected_files):
                info = tarfile.TarInfo(f"{source_root}/{relative}")
                payload = (
                    valid_metadata if relative == "PKG-INFO"
                    else invalid_nested_metadata if relative == nested_pkg_info
                    else b""
                )
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))

        with self.assertRaisesRegex(SystemExit, "Requires-Dist metadata differs"):
            verifier._verify_sdist(
                sdist,
                project_root,
                [],
                name,
                version,
                expected_project=project,
            )

    def test_distribution_verifier_preflights_zip_central_directory_limits(self):
        import importlib.util
        import zipfile

        project_root = Path(__file__).resolve().parents[1]
        verifier_path = project_root / "tools" / "verify_distributions.py"
        spec = importlib.util.spec_from_file_location("sra_zip_preflight_verifier", verifier_path)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)

        zip_path = project_root / "tests" / "_too-many-zip-members-test.whl"
        self.addCleanup(lambda: zip_path.unlink(missing_ok=True))
        with zipfile.ZipFile(zip_path, "w") as archive:
            for index in range(12):
                archive.writestr(f"unexpected-{index}.txt", "x")
        with self.assertRaisesRegex(SystemExit, "wheel contains too many archive members"):
            verifier._preflight_zip_archive(zip_path, maximum_member_count=8)

        import struct
        forged_count_zip = project_root / "tests" / "_forged-eocd-count-test.whl"
        self.addCleanup(lambda: forged_count_zip.unlink(missing_ok=True))
        with zipfile.ZipFile(forged_count_zip, "w") as archive:
            for index in range(12):
                archive.writestr(f"member-{index}.txt", b"x")
        forged = bytearray(forged_count_zip.read_bytes())
        eocd = forged.rfind(b"PK\x05\x06")
        struct.pack_into("<HH", forged, eocd + 8, 1, 1)
        forged_count_zip.write_bytes(forged)
        with self.assertRaisesRegex(SystemExit, "central-directory entry count mismatch"):
            verifier._preflight_zip_archive(forged_count_zip, maximum_member_count=20)

        oversized_directory = project_root / "tests" / "_oversized-central-directory-test.whl"
        self.addCleanup(lambda: oversized_directory.unlink(missing_ok=True))
        with zipfile.ZipFile(oversized_directory, "w") as archive:
            for index in range(36):
                info = zipfile.ZipInfo(f"entry-{index}.txt")
                info.extra = struct.pack("<HH", 0xCAFE, 60000) + b"x" * 60000
                archive.writestr(info, b"x")
        with self.assertRaisesRegex(SystemExit, "central directory exceeds 2 MiB"):
            verifier._preflight_zip_archive(oversized_directory, maximum_member_count=100)

        malformed_zip = project_root / "tests" / "_malformed-eocd-test.whl"
        self.addCleanup(lambda: malformed_zip.unlink(missing_ok=True))
        malformed_zip.write_bytes(b"PK\x05\x06" + b"\x00" * 30)
        with self.assertRaisesRegex(SystemExit, "invalid ZIP end-of-central-directory"):
            verifier._preflight_zip_archive(malformed_zip, maximum_member_count=8)

    def test_distribution_verifier_rejects_oversized_archive_containers(self):
        import importlib.util

        project_root = Path(__file__).resolve().parents[1]
        verifier_path = project_root / "tools" / "verify_distributions.py"
        spec = importlib.util.spec_from_file_location("sra_archive_size_verifier", verifier_path)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)

        oversized_sdist = project_root / "tests" / "_oversized-container-test.tar.gz"
        oversized_wheel = project_root / "tests" / "_oversized-container-test.whl"
        self.addCleanup(lambda: oversized_sdist.unlink(missing_ok=True))
        self.addCleanup(lambda: oversized_wheel.unlink(missing_ok=True))
        for path in (oversized_sdist, oversized_wheel):
            with path.open("wb") as stream:
                stream.truncate(verifier.MAX_ARCHIVE_BYTES + 1)

        with self.assertRaisesRegex(SystemExit, "compressed source archive exceeds"):
            verifier._verify_sdist(
                oversized_sdist,
                project_root,
                [],
                "scientific-reasoning-auditor",
                "0.7.0",
            )
        with self.assertRaisesRegex(SystemExit, "wheel archive exceeds"):
            verifier._preflight_zip_archive(oversized_wheel, maximum_member_count=8)

    def test_distribution_verifier_limits_gzip_expansion_before_tar_parsing(self):
        import gzip
        import importlib.util

        project_root = Path(__file__).resolve().parents[1]
        verifier_path = project_root / "tools" / "verify_distributions.py"
        spec = importlib.util.spec_from_file_location("sra_gzip_expansion_verifier", verifier_path)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)

        archive_path = project_root / "tests" / "_gzip-expansion-limit-test.tar.gz"
        self.addCleanup(lambda: archive_path.unlink(missing_ok=True))
        with gzip.open(archive_path, "wb") as stream:
            remaining = verifier.MAX_ARCHIVE_UNCOMPRESSED_BYTES + 1
            chunk = b"0" * verifier.ARCHIVE_READ_CHUNK_BYTES
            while remaining:
                current = min(remaining, len(chunk))
                stream.write(chunk[:current])
                remaining -= current
        self.assertLess(archive_path.stat().st_size, verifier.MAX_ARCHIVE_BYTES)
        with self.assertRaisesRegex(SystemExit, "expanded source archive exceeds"):
            verifier._verify_sdist(
                archive_path,
                project_root,
                [],
                "scientific-reasoning-auditor",
                "0.7.0",
            )

        invalid_gzip = project_root / "tests" / "_invalid-gzip-container-test.tar.gz"
        self.addCleanup(lambda: invalid_gzip.unlink(missing_ok=True))
        invalid_gzip.write_bytes(b"this is not a gzip archive")
        with self.assertRaisesRegex(SystemExit, "invalid gzip source archive"):
            verifier._check_gzip_archive_expansion(invalid_gzip)

    def test_distribution_verifier_rejects_unrecognized_metadata_headers(self):
        import importlib.util
        import tomllib

        project_root = Path(__file__).resolve().parents[1]
        verifier_path = project_root / "tools" / "verify_distributions.py"
        spec = importlib.util.spec_from_file_location("sra_metadata_header_verifier", verifier_path)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        project = tomllib.loads(
            (project_root / "pyproject.toml").read_text(encoding="utf-8")
        )["project"]
        fields = verifier._expected_metadata_fields(project)
        lines = []
        for field, values in fields.items():
            if values is None:
                continue
            if isinstance(values, list):
                lines.extend(f"{field}: {value}" for value in values)
            else:
                lines.append(f"{field}: {values}")
        lines.append("License: Proprietary")
        payload = (
            "\n".join(lines)
            + "\n\n"
            + (project_root / "README.md").read_text(encoding="utf-8")
        ).encode("utf-8")
        with self.assertRaisesRegex(SystemExit, "unrecognized metadata headers"):
            verifier._verify_metadata(
                payload,
                project["name"],
                project["version"],
                "malicious.whl",
                expected_project=project,
                repository_root=project_root,
            )

    def test_distribution_archive_member_reads_are_size_bounded(self):
        import importlib.util
        import io
        import tarfile
        import zipfile

        project_root = Path(__file__).resolve().parents[1]
        verifier_path = project_root / "tools" / "verify_distributions.py"
        spec = importlib.util.spec_from_file_location("sra_bounded_archive_verifier", verifier_path)
        verifier = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verifier)
        oversized = verifier.MAX_ARCHIVE_METADATA_BYTES + 1

        tar_path = project_root / "tests" / "_oversized-metadata-test.tar"
        self.addCleanup(lambda: tar_path.unlink(missing_ok=True))
        with tarfile.open(tar_path, "w") as archive:
            info = tarfile.TarInfo("oversized-metadata")
            info.size = oversized
            archive.addfile(info, io.BytesIO(b"x" * oversized))
        with tarfile.open(tar_path, "r:") as archive:
            member = archive.getmembers()[0]
            with self.assertRaisesRegex(SystemExit, "archive metadata member exceeds"):
                verifier._read_tar_member_bounded(archive, member, tar_path.name)

        zip_path = project_root / "tests" / "_oversized-metadata-test.zip"
        self.addCleanup(lambda: zip_path.unlink(missing_ok=True))
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("oversized-metadata", b"0" * oversized)
        with zipfile.ZipFile(zip_path, "r") as archive:
            info = archive.infolist()[0]
            with self.assertRaisesRegex(SystemExit, "wheel metadata member exceeds"):
                verifier._read_zip_member_bounded(archive, info, zip_path.name)

    def test_source_tree_hash_covers_tests_and_workflow_inputs(self):
        from sra.provenance import _source_tree_sha256

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src/sra").mkdir(parents=True)
            (root / "tests").mkdir()
            (root / ".github/workflows").mkdir(parents=True)
            (root / "src/sra/module.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "tests/test_module.py").write_text("assert True\n", encoding="utf-8")
            (root / ".github/workflows/tests.yml").write_text("name: tests\n", encoding="utf-8")
            first_hash, scope, files = _source_tree_sha256(root)
            self.assertIn("Python tests", scope)
            self.assertIn("GitHub Actions workflows", scope)
            self.assertEqual(
                files,
                [".github/workflows/tests.yml", "src/sra/module.py", "tests/test_module.py"],
            )
            (root / "tests/test_module.py").write_text("assert False\n", encoding="utf-8")
            second_hash, _, second_files = _source_tree_sha256(root)
            self.assertNotEqual(first_hash, second_hash)
            self.assertEqual(files, second_files)

    def test_synthetic_logic_demo_emits_the_expected_review_signals(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "logic_review_demo.md"
        report = audit_file(example)
        ids = {finding.check_id for finding in report.findings}
        self.assertIn("reasoning.causal_claim_observational_design", ids)
        self.assertIn("reasoning.directional_contradiction", ids)
        self.assertIn("reasoning.correlation_causation_review", ids)

    def test_reasoning_graph_has_typed_nodes_and_linked_relations(self):
        report = self.audit_text(
            "# Methods\nWe used a randomized experiment.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        graph = report.reasoning_graph
        node_types = {node["node_type"] for node in graph["nodes"]}
        relations = {edge["relation"] for edge in graph["edges"]}
        self.assertTrue({"method", "evidence", "claim", "inference"}.issubset(node_types))
        self.assertIn("lexical_candidate_basis", relations)
        self.assertIn("yields_claim", relations)
        self.assertIn("method_document_context", relations)
        self.assertIn("heuristic_only", graph["edge_statuses"])
        self.assertIn("not_semantically_verified", graph["node_statuses"])
        self.assertEqual(
            graph["edge_endpoint_types"]["lexical_candidate_basis"],
            {"source": ["evidence"], "target": ["inference"]},
        )
        self.assertEqual(graph["validation"]["status"], "PASS")
        self.assertTrue(any(edge["status"] == "document_context_only" for edge in graph["edges"]))
        self.assertEqual(len(graph["graph_fingerprint"]), 64)

    def test_document_context_graph_edges_scale_linearly(self):
        method_lines = "\n".join(
            f"Protocol step {index} was completed under the prespecified procedure."
            for index in range(12)
        )
        limitation_lines = "\n".join(
            f"Study limitation {index} affected interpretation of the subgroup estimate."
            for index in range(8)
        )
        result_lines = "\n".join(
            f"The intervention increased outcome marker {index} in the measured group."
            for index in range(10)
        )
        conclusion_lines = "\n".join(
            f"The intervention increased outcome marker {index} in the measured group."
            for index in range(10)
        )
        report = self.audit_text(
            f"# Methods\n{method_lines}\n"
            f"# Results\n{result_lines}\n"
            f"# Limitations\n{limitation_lines}\n"
            f"# Conclusion\n{conclusion_lines}"
        )
        graph = report.reasoning_graph
        method_count = sum(node["node_type"] == "method" for node in graph["nodes"])
        limitation_count = sum(node["node_type"] == "limitation" for node in graph["nodes"])
        inference_count = sum(node["node_type"] == "inference" for node in graph["nodes"])
        membership_edges = [
            edge for edge in graph["edges"]
            if edge["relation"] == "document_context_membership"
        ]
        method_context_edges = [
            edge for edge in graph["edges"]
            if edge["relation"] == "method_document_context"
        ]
        limitation_context_edges = [
            edge for edge in graph["edges"]
            if edge["relation"] == "limitation_document_context"
        ]
        self.assertEqual(len(membership_edges), method_count + limitation_count)
        self.assertEqual(len(method_context_edges), inference_count)
        self.assertEqual(len(limitation_context_edges), inference_count)
        self.assertLess(
            len(membership_edges) + len(method_context_edges) + len(limitation_context_edges),
            (method_count + limitation_count) * inference_count,
        )

    def test_explicit_assumptions_and_missing_assumption_gaps_are_distinguished(self):
        report = self.audit_text(
            "# Methods\nWe assume that there is no unmeasured confounding.\n"
            "# Results\nExposure was associated with outcome.\n"
            "# Conclusion\nExposure caused the outcome."
        )
        nodes = report.reasoning_graph["nodes"]
        self.assertTrue(any(n["node_type"] == "assumption" for n in nodes))
        self.assertTrue(any(n["node_type"] == "assumption_gap" for n in nodes))
        gap = next(n for n in nodes if n["node_type"] == "assumption_gap")
        self.assertEqual(gap["status"], "not_linked_to_claim_review_required")
        self.assertIn("not proof", gap["text"])
        no_assumption = self.audit_text(
            "# Methods\nA cross-sectional study was conducted.\n"
            "# Results\nExposure was associated with outcome.\n"
            "# Conclusion\nExposure caused the outcome."
        )
        missing_gap = next(
            n for n in no_assumption.reasoning_graph["nodes"] if n["node_type"] == "assumption_gap"
        )
        self.assertEqual(missing_gap["status"], "not_extracted_review_required")

        lexically_linked_but_inadequate = self.audit_text(
            "# Methods\nWe assume that exposure was measured accurately in adults.\n"
            "# Results\nExposure was associated with outcome in adults.\n"
            "# Conclusion\nExposure caused outcome in adults."
        )
        linked_nodes = lexically_linked_but_inadequate.reasoning_graph["nodes"]
        linked_gap = next(n for n in linked_nodes if n["node_type"] == "assumption_gap")
        self.assertEqual(linked_gap["status"], "candidate_assumptions_found_review_required")
        self.assertIn("does not establish", linked_gap["text"])

        repeated_section_assumptions = self.audit_text(
            "# Methods\nA protocol was specified.\n"
            "# Results\nWe assume that the baseline score was measured accurately.\n"
            "# Results\nThe outcome was stable."
        )
        assumption_nodes = [
            node for node in repeated_section_assumptions.reasoning_graph["nodes"]
            if node["node_type"] == "assumption"
        ]
        self.assertEqual(len(assumption_nodes), 1)

    def test_graph_integrity_validator_detects_dangling_edges_and_cycles(self):
        from sra.graph import _edge_id

        nodes = [
            {"node_id": "a", "node_type": "evidence", "status": "extracted_heuristically"},
            {"node_id": "b", "node_type": "inference", "status": "not_semantically_verified"},
        ]
        edges = [
            {"edge_id": _edge_id("a", "b", "lexical_candidate_basis"),
             "source": "a", "target": "b", "relation": "lexical_candidate_basis",
             "status": "heuristic_only"},
            {"edge_id": _edge_id("b", "a", "yields_claim"),
             "source": "b", "target": "a", "relation": "yields_claim",
             "status": "structural_extraction_only"},
            {"edge_id": _edge_id("missing", "b", "lexical_candidate_basis"),
             "source": "missing", "target": "b", "relation": "lexical_candidate_basis",
             "status": "heuristic_only"},
        ]
        result = validate_reasoning_graph(nodes, edges)
        self.assertEqual(result["status"], "FAIL")
        self.assertTrue(result["dependency_cycle_detected"])
        dangling_id = _edge_id("missing", "b", "lexical_candidate_basis")
        self.assertIn(dangling_id, result["dangling_edges"])
        duplicates = validate_reasoning_graph(
            [
                {"node_id": "same", "node_type": "claim", "status": "extracted_heuristically"},
                {"node_id": "same", "node_type": "evidence", "status": "extracted_heuristically"},
            ],
            [],
        )
        self.assertEqual(duplicates["status"], "FAIL")
        self.assertIn("same", duplicates["duplicate_node_ids"])
        duplicate_edges = validate_reasoning_graph(
            [
                {"node_id": "x", "node_type": "claim", "status": "extracted_heuristically"},
                {"node_id": "y", "node_type": "evidence", "status": "extracted_heuristically"},
            ],
            [
                {"edge_id": _edge_id("x", "y", "qualifies_claim_candidate"),
                 "source": "x", "target": "y", "relation": "qualifies_claim_candidate",
                 "status": "heuristic_only"},
                {"edge_id": _edge_id("x", "y", "qualifies_claim_candidate"),
                 "source": "x", "target": "y", "relation": "qualifies_claim_candidate",
                 "status": "heuristic_only"},
            ],
        )
        self.assertEqual(duplicate_edges["status"], "FAIL")
        duplicate_edge_id = _edge_id("x", "y", "qualifies_claim_candidate")
        self.assertIn(duplicate_edge_id, duplicate_edges["duplicate_edge_ids"])

        malformed_node = validate_reasoning_graph(
            [{"node_id": [], "node_type": "claim", "status": "extracted_heuristically"}], []
        )
        self.assertEqual(malformed_node["status"], "FAIL")
        self.assertIn(0, malformed_node["invalid_node_entries"])
        malformed_edge = validate_reasoning_graph(
            [{"node_id": "claim-1", "node_type": "claim", "status": "extracted_heuristically"}],
            [{"edge_id": "edge-1", "source": [], "target": "claim-1",
              "relation": "yields_claim", "status": "structural_extraction_only"}],
        )
        self.assertEqual(malformed_edge["status"], "FAIL")
        self.assertIn(0, malformed_edge["invalid_edge_entries"])
        malformed_shapes = validate_reasoning_graph([None], [None])
        self.assertEqual(malformed_shapes["status"], "FAIL")

    def test_graph_fingerprint_covers_and_validator_checks_schema_contract_metadata(self):
        from copy import deepcopy
        from sra.graph import graph_fingerprint, validate_reasoning_graph

        report = self.audit_text(
            "# Methods\nThe protocol was prespecified.\n"
            "# Results\nThe signal increased.\n"
            "# Conclusion\nThe signal increased."
        )
        graph = report.reasoning_graph
        original_fingerprint = graph_fingerprint(graph)
        mutated = deepcopy(graph)
        mutated["edge_endpoint_types"]["lexical_candidate_basis"]["source"] = ["claim"]
        self.assertNotEqual(original_fingerprint, graph_fingerprint(mutated))

        metadata = {
            key: mutated[key]
            for key in (
                "node_types", "node_statuses", "edge_relations",
                "edge_statuses", "edge_endpoint_types",
            )
        }
        validation = validate_reasoning_graph(
            mutated["nodes"], mutated["edges"], metadata=metadata
        )
        self.assertEqual(validation["status"], "FAIL")
        self.assertIn("edge_endpoint_types", validation["invalid_schema_metadata"])

    def test_graph_object_validator_requires_supported_schema_and_canonical_metadata(self):
        from copy import deepcopy
        from sra.graph import graph_fingerprint, validate_reasoning_graph_object

        graph = self.audit_text(
            "# Methods\nProtocol prespecified.\n"
            "# Results\nSignal increased.\n"
            "# Conclusion\nSignal increased."
        ).reasoning_graph
        valid = validate_reasoning_graph_object(graph)
        self.assertEqual(valid["status"], "PASS")
        self.assertEqual(valid["invalid_schema_version"], [])
        self.assertEqual(valid["invalid_graph_fingerprint"], [])
        self.assertEqual(valid["invalid_graph_validation"], [])

        tampered_validation = deepcopy(graph)
        tampered_validation["validation"]["dependency_cycle_detected"] = True
        invalid_validation = validate_reasoning_graph_object(tampered_validation)
        self.assertEqual(invalid_validation["status"], "FAIL")
        self.assertEqual(invalid_validation["invalid_graph_validation"], ["validation"])

        corrupted_fingerprint = deepcopy(graph)
        corrupted_fingerprint["graph_fingerprint"] = "0" * 64
        invalid_fingerprint = validate_reasoning_graph_object(corrupted_fingerprint)
        self.assertEqual(invalid_fingerprint["status"], "FAIL")
        self.assertEqual(invalid_fingerprint["invalid_graph_fingerprint"], ["0" * 64])

        unsupported_algorithm = deepcopy(graph)
        unsupported_algorithm["fingerprint_algorithm"] = "unknown"
        invalid_algorithm = validate_reasoning_graph_object(unsupported_algorithm)
        self.assertEqual(invalid_algorithm["status"], "FAIL")
        self.assertIn("fingerprint_algorithm", invalid_algorithm["invalid_schema_metadata"])

        unsupported_version = deepcopy(graph)
        unsupported_version["schema_version"] = "999"
        invalid_version = validate_reasoning_graph_object(unsupported_version)
        self.assertEqual(invalid_version["status"], "FAIL")
        self.assertEqual(invalid_version["invalid_schema_version"], ["999"])

        malformed_source_hash = deepcopy(graph)
        malformed_source_hash["source_sha256"] = "not-a-sha256"
        malformed_source_hash["graph_fingerprint"] = graph_fingerprint(malformed_source_hash)
        invalid_source_hash = validate_reasoning_graph_object(malformed_source_hash)
        self.assertEqual(invalid_source_hash["status"], "FAIL")
        self.assertEqual(invalid_source_hash["invalid_source_sha256"], ["not-a-sha256"])

        incomplete_metadata = deepcopy(graph)
        incomplete_metadata.pop("edge_endpoint_types")
        invalid_metadata = validate_reasoning_graph_object(incomplete_metadata)
        self.assertEqual(invalid_metadata["status"], "FAIL")
        self.assertIn("edge_endpoint_types", invalid_metadata["invalid_schema_metadata"])

    def test_graph_object_validator_checks_complete_node_and_edge_schemas(self):
        from copy import deepcopy
        from sra.graph import graph_fingerprint, validate_reasoning_graph_object

        graph = self.audit_text(
            "# Methods\nProtocol prespecified.\n"
            "# Results\nSignal increased.\n"
            "# Conclusion\nSignal increased."
        ).reasoning_graph

        missing_node_text = deepcopy(graph)
        del missing_node_text["nodes"][0]["text"]
        missing_node_text["graph_fingerprint"] = graph_fingerprint(missing_node_text)
        result_node = validate_reasoning_graph_object(missing_node_text)
        self.assertEqual(result_node["status"], "FAIL")
        self.assertIn(0, result_node["invalid_node_schema"])

        extra_node_field = deepcopy(graph)
        extra_node_field["nodes"][0]["unrecognized"] = True
        extra_node_field["graph_fingerprint"] = graph_fingerprint(extra_node_field)
        result_extra_node = validate_reasoning_graph_object(extra_node_field)
        self.assertEqual(result_extra_node["status"], "FAIL")
        self.assertIn(0, result_extra_node["invalid_node_schema"])

        missing_edge_metadata = deepcopy(graph)
        del missing_edge_metadata["edges"][0]["metadata"]
        missing_edge_metadata["graph_fingerprint"] = graph_fingerprint(missing_edge_metadata)
        result_edge = validate_reasoning_graph_object(missing_edge_metadata)
        self.assertEqual(result_edge["status"], "FAIL")
        self.assertIn(0, result_edge["invalid_edge_schema"])

    def test_graph_object_validator_rejects_unknown_top_level_fields(self):
        from copy import deepcopy
        from sra.graph import validate_reasoning_graph_object

        graph = self.audit_text(
            "# Methods\nProtocol prespecified.\n"
            "# Results\nSignal increased.\n"
            "# Conclusion\nSignal increased."
        ).reasoning_graph
        extended = deepcopy(graph)
        extended["unrecognized_extension"] = {"meaning": "not covered by fingerprint"}
        self.assertEqual(extended["graph_fingerprint"], graph["graph_fingerprint"])

        result = validate_reasoning_graph_object(extended)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["invalid_graph_fields"], ["unrecognized_extension"])

    def test_graph_validator_rejects_unknown_schema_values_and_wrong_endpoint_types(self):
        from sra.graph import _edge_id

        nodes = [
            {"node_id": "claim-1", "node_type": "claim", "status": "extracted_heuristically"},
            {"node_id": "evidence-1", "node_type": "evidence", "status": "extracted_heuristically"},
        ]
        unknown_relation = {
            "edge_id": _edge_id("evidence-1", "claim-1", "not_a_relation"),
            "source": "evidence-1", "target": "claim-1",
            "relation": "not_a_relation", "status": "heuristic_only",
        }
        wrong_endpoint = {
            "edge_id": _edge_id("claim-1", "evidence-1", "lexical_candidate_basis"),
            "source": "claim-1", "target": "evidence-1",
            "relation": "lexical_candidate_basis", "status": "heuristic_only",
        }
        invalid_status = {
            "edge_id": _edge_id("evidence-1", "claim-1", "possible_contradiction_candidate"),
            "source": "evidence-1", "target": "claim-1",
            "relation": "possible_contradiction_candidate", "status": "invented_status",
        }
        mismatched_edge_id = {
            "edge_id": "edge:wrong",
            "source": "evidence-1", "target": "claim-1",
            "relation": "possible_contradiction_candidate", "status": "heuristic_review_required",
        }
        result = validate_reasoning_graph(
            nodes, [unknown_relation, wrong_endpoint, invalid_status, mismatched_edge_id]
        )
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["invalid_edge_relations"], [0])
        self.assertEqual(result["invalid_edge_endpoint_types"], [1])
        self.assertEqual(result["invalid_edge_statuses"], [2])
        self.assertEqual(result["invalid_edge_ids"], [3])

        bad_node = validate_reasoning_graph(
            [{"node_id": "x", "node_type": "invented_type", "status": "invented_status"}], []
        )
        self.assertEqual(bad_node["status"], "FAIL")
        self.assertEqual(bad_node["invalid_node_types"], [0])
        self.assertEqual(bad_node["invalid_node_statuses"], [0])

    def test_semantic_review_loader_rejects_nonstandard_json_constants(self):
        from sra.semantic_review import load_semantic_review

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "review.json"
            for constant in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(constant=constant):
                    path.write_text('{"confidence": ' + constant + '}', encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Non-standard JSON numeric constant"):
                        load_semantic_review(path)

    def test_semantic_review_json_schema_documents_the_review_contract(self):
        schema_path = Path(__file__).resolve().parents[1] / "schemas" / "semantic-review.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.4")
        self.assertIn("review_mode", schema["required"])
        self.assertIn("graph_schema_version", schema["required"])
        self.assertIn("graph_fingerprint_algorithm", schema["required"])
        self.assertIn("evidence_catalog", schema["required"])
        self.assertIn("reviewer_selected_evidence_node_ids",
                        schema["properties"]["assessments"]["items"]["required"])
        self.assertIn("source_sha256", schema["properties"])
        self.assertEqual(schema["properties"]["graph_schema_version"]["const"], "1.4")
        self.assertEqual(
            schema["properties"]["graph_fingerprint_algorithm"]["const"],
            "sha256-canonical-json-graph-contract-v2",
        )
        self.assertIn("graph_fingerprint", schema["properties"])
        self.assertIn("assessments", schema["required"])
        self.assertIn("partially_supported", schema["properties"]["assessments"]["items"]["properties"]["relation"]["enum"])

    def test_semantic_review_mode_is_user_selectable(self):
        report = self.audit_text(
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        ).to_dict()
        single = self.build_template(report)
        parallel = self.build_template(report, review_mode="parallel")
        self.assertEqual(single["review_mode"], "single")
        self.assertEqual(parallel["review_mode"], "parallel")
        self.assertIn("one model", single["instructions"][0])
        self.assertIn("parallel agents", parallel["instructions"][0])
        with self.assertRaises(ValueError):
            self.build_template(report, review_mode="automatic")

    def test_semantic_review_rejects_unlinked_evidence_and_one_word_quotes(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "The unrelated biomarker concentration decreased after storage.\n"
            "Participants showed higher values on the assessment scale following treatment.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = self.build_template(report)
        assessment = template["assessments"][0]
        evidence_nodes = [
            node for node in report["reasoning_graph"]["nodes"]
            if node["node_type"] == "evidence"
        ]
        selected = assessment["evidence_node_ids"][0]
        unrelated = next(node for node in evidence_nodes if node["node_id"] != selected)
        assessment.update({
            "relation": "entailed",
            "confidence": 0.99,
            "rationale": "The selected sentence is claimed to entail the conclusion.",
            "source_quotes": [unrelated["text"]],
        })
        template["reviewer"] = {
            "name": "Test reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        assessment["evidence_node_ids"] = [unrelated["node_id"]]
        rejected_unlinked = validate_semantic_review(template, report, text)
        self.assertEqual(rejected_unlinked["status"], "REJECTED")
        self.assertTrue(any("not linked to its inference" in error for error in rejected_unlinked["errors"]))

        assessment["evidence_node_ids"] = [selected]
        assessment["source_quotes"] = ["The"]
        rejected_short = validate_semantic_review(template, report, text)
        self.assertEqual(rejected_short["status"], "REJECTED")
        self.assertTrue(any("too short" in error for error in rejected_short["errors"]))

        paraphrased = next(
            node for node in evidence_nodes
            if node["node_id"] not in {selected, unrelated["node_id"]}
        )
        assessment["source_quotes"] = [paraphrased["text"]]
        assessment["reviewer_selected_evidence_node_ids"] = [paraphrased["node_id"]]
        accepted_additional = validate_semantic_review(template, report, text)
        self.assertEqual(accepted_additional["status"], "ACCEPTED_FOR_REVIEW")
        self.assertEqual(
            accepted_additional["validated_assessments"][0]["reviewer_selected_evidence_node_ids"],
            [paraphrased["node_id"]],
        )

    def test_semantic_review_runtime_matches_schema_required_and_extra_fields(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = self.build_template(report)
        evidence_id = template["assessments"][0]["evidence_node_ids"][0]
        evidence = next(
            node for node in report["reasoning_graph"]["nodes"]
            if node["node_id"] == evidence_id
        )
        template["reviewer"] = {
            "name": "Test reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        template["assessments"][0].update({
            "relation": "entailed",
            "confidence": 0.9,
            "rationale": "The linked result matches the claim.",
            "source_quotes": [evidence["text"]],
        })
        missing = json.loads(json.dumps(template))
        missing.pop("instructions")
        missing.pop("relation_labels")
        rejected_missing = validate_semantic_review(missing, report, text)
        self.assertEqual(rejected_missing["status"], "REJECTED")
        self.assertTrue(any("instructions" in error for error in rejected_missing["errors"]))
        self.assertTrue(any("relation_labels" in error for error in rejected_missing["errors"]))

        extra = json.loads(json.dumps(template))
        extra["unrecognized"] = True
        rejected_extra = validate_semantic_review(extra, report, text)
        self.assertEqual(rejected_extra["status"], "REJECTED")
        self.assertTrue(any("Unexpected top-level" in error for error in rejected_extra["errors"]))

        tampered_catalog = json.loads(json.dumps(template))
        tampered_catalog["evidence_catalog"][0]["text"] = "Modified source passage."
        rejected_catalog = validate_semantic_review(tampered_catalog, report, text)
        self.assertEqual(rejected_catalog["status"], "REJECTED")
        self.assertTrue(any("catalog text does not match" in error for error in rejected_catalog["errors"]))

        offset = json.loads(json.dumps(template))
        offset["reviewer"]["reviewed_at_utc"] = "2026-11-02T03:00:00+03:00"
        rejected_offset = validate_semantic_review(offset, report, text)
        self.assertEqual(rejected_offset["status"], "REJECTED")
        self.assertTrue(any("must use UTC" in error for error in rejected_offset["errors"]))

    def test_legacy_semantic_review_v10_imports_as_single_mode(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        legacy = self.build_template(report)
        evidence_id = legacy["assessments"][0]["evidence_node_ids"][0]
        evidence = next(
            node for node in report["reasoning_graph"]["nodes"]
            if node["node_id"] == evidence_id
        )
        legacy["assessments"][0].update({
            "relation": "entailed",
            "confidence": 0.9,
            "rationale": "The result passage matches the conclusion claim.",
            "source_quotes": [evidence["text"]],
        })
        legacy["reviewer"] = {
            "name": "Legacy reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        legacy["schema_version"] = "1.0"
        legacy.pop("graph_schema_version")
        legacy.pop("graph_fingerprint_algorithm")
        legacy.pop("review_mode")
        legacy.pop("evidence_catalog")
        legacy["assessments"][0].pop("reviewer_selected_evidence_node_ids")
        result = validate_semantic_review(legacy, report, text)
        self.assertEqual(result["status"], "ACCEPTED_FOR_REVIEW")
        self.assertEqual(result["review_mode"], "single")

    def test_legacy_v11_graph_fingerprint_matches_public_v051_output(self):
        from sra.graph import legacy_graph_fingerprint_v1_1

        example = Path(__file__).resolve().parents[1] / "examples" / "logic_review_demo.md"
        graph = audit_file(example).to_dict()["reasoning_graph"]
        self.assertEqual(
            legacy_graph_fingerprint_v1_1(graph),
            "15ff8d43448068ca588ba6fb03d705ac5937427c1a4c483e46a48261216fdcd9",
        )

    def test_legacy_semantic_review_v13_accepts_published_v051_graph_fingerprint(self):
        from sra.graph import legacy_graph_fingerprint_v1_1

        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        graph = report["reasoning_graph"]
        legacy = self.build_template(report)
        evidence_id = legacy["assessments"][0]["evidence_node_ids"][0]
        evidence = next(node for node in graph["nodes"] if node["node_id"] == evidence_id)
        legacy["assessments"][0].update({
            "relation": "entailed",
            "confidence": 0.9,
            "rationale": "The results passage reports the same measured direction as the conclusion.",
            "source_quotes": [evidence["text"]],
        })
        legacy["reviewer"] = {
            "name": "Legacy reviewer",
            "model_or_agent": "v0.5.1",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        legacy["schema_version"] = "1.3"
        legacy.pop("graph_schema_version")
        legacy.pop("graph_fingerprint_algorithm")
        legacy["graph_fingerprint"] = legacy_graph_fingerprint_v1_1(graph)

        accepted = validate_semantic_review(legacy, report, text)
        self.assertEqual(accepted["status"], "ACCEPTED_FOR_REVIEW")
        self.assertFalse(accepted["errors"])

        changed_report = json.loads(json.dumps(report))
        evidence_node = next(
            node for node in changed_report["reasoning_graph"]["nodes"]
            if node["node_type"] == "evidence"
        )
        evidence_node["text"] += " changed"
        rejected = validate_semantic_review(legacy, changed_report, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any("Graph fingerprint" in error for error in rejected["errors"]))

    def test_semantic_review_template_is_bound_to_source_and_graph(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = self.build_template(report)
        self.assertEqual(template["source_sha256"], report["sha256"])
        self.assertEqual(template["graph_fingerprint"], report["reasoning_graph"]["graph_fingerprint"])
        self.assertEqual(
            {node["node_id"] for node in template["evidence_catalog"]},
            {
                node["node_id"] for node in report["reasoning_graph"]["nodes"]
                if node["node_type"] == "evidence"
            },
        )
        self.assertEqual(len(template["assessments"]), 1)
        assessment = template["assessments"][0]
        evidence_id = assessment["evidence_node_ids"][0]
        evidence = next(n for n in report["reasoning_graph"]["nodes"] if n["node_id"] == evidence_id)
        assessment.update({
            "relation": "entailed",
            "confidence": 0.93,
            "rationale": "The result sentence directly reports the same direction and measured outcome as the claim.",
            "source_quotes": [evidence["text"]],
            "missing_assumptions": [],
            "counter_evidence_node_ids": [],
        })
        template["reviewer"] = {
            "name": "Test reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        accepted = validate_semantic_review(template, report, text)
        self.assertEqual(accepted["status"], "ACCEPTED_FOR_REVIEW")
        self.assertEqual(accepted["validated_assessments"][0]["validation_status"],
                         "structurally_validated_not_truth_verified")

    def test_build_review_template_preserves_bom_source_hash_and_reconstructs_graph(self):
        from sra.audit import build_review_template

        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.md"
            source.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
            raw_hash = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
            template = build_review_template(str(source))
            self.assertEqual(template["source_sha256"], raw_hash)
            report = audit_file(source).to_dict()
            self.assertEqual(template["graph_fingerprint"], report["reasoning_graph"]["graph_fingerprint"])

    def test_semantic_review_template_requires_source_text_for_provenance(self):
        report = self.audit_text(
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        ).to_dict()
        with self.assertRaises(TypeError):
            build_semantic_review_template(report)
        with self.assertRaises(TypeError):
            build_semantic_review_template(
                report,
                source_text=self._last_source_text,
                source_sha256=report["sha256"],
            )

    def test_pdf_manifest_separates_raw_file_and_extracted_text_hashes(self):
        import hashlib
        import sys
        from types import SimpleNamespace
        from unittest.mock import patch
        from sra.audit import build_review_template

        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        raw_pdf_bytes = b"%PDF-FAKE-RAW-SOURCE-FOR-HASH-SEPARATION"
        fake_reader = lambda _path: SimpleNamespace(
            pages=[SimpleNamespace(extract_text=lambda: text)]
        )
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "paper.pdf"
            source.write_bytes(raw_pdf_bytes)
            fake_pypdf = SimpleNamespace(PdfReader=fake_reader)
            with patch.dict(sys.modules, {"pypdf": fake_pypdf}):
                document = load_document(source)
                report = audit_file(source).to_dict()
                template = build_review_template(str(source))

            raw_hash = hashlib.sha256(raw_pdf_bytes).hexdigest()
            extracted_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            self.assertEqual(document.sha256, raw_hash)
            self.assertEqual(report["reproducibility_manifest"]["input"]["sha256"], raw_hash)
            self.assertEqual(
                report["reproducibility_manifest"]["input"]["extracted_text_sha256"],
                extracted_hash,
            )
            self.assertNotEqual(raw_hash, extracted_hash)
            self.assertEqual(template["source_sha256"], raw_hash)
            self.assertEqual(
                report["reasoning_graph"]["graph_fingerprint"],
                template["graph_fingerprint"],
            )

    def test_graph_validator_rejects_empty_graph_and_missing_claim_links(self):
        from copy import deepcopy
        from sra.graph import graph_fingerprint, validate_reasoning_graph_object

        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        graph = report["reasoning_graph"]

        empty = deepcopy(graph)
        empty["nodes"] = []
        empty["edges"] = []
        empty["graph_fingerprint"] = graph_fingerprint(empty)
        empty["validation"] = validate_reasoning_graph_object(
            empty, allow_unset_validation=True
        )
        invalid_empty = validate_reasoning_graph_object(empty)
        self.assertEqual(invalid_empty["status"], "FAIL")
        self.assertEqual(invalid_empty["invalid_graph_content"], ["empty_nodes", "empty_edges"])
        with self.assertRaisesRegex(ValueError, "invalid reasoning graph"):
            self.build_template({
                "sha256": report["sha256"],
                "reasoning_graph": empty,
            })

        method_only_text = "# Methods\nA protocol was prespecified."
        method_only_report = self.audit_text(method_only_text).to_dict()
        method_only_graph = method_only_report["reasoning_graph"]
        self.assertTrue(method_only_graph["nodes"])
        method_only_graph["edges"] = []
        method_only_graph["graph_fingerprint"] = graph_fingerprint(method_only_graph)
        method_only_graph["validation"] = validate_reasoning_graph_object(
            method_only_graph, allow_unset_validation=True
        )
        method_only_validation = validate_reasoning_graph_object(method_only_graph)
        self.assertEqual(method_only_validation["status"], "FAIL")
        self.assertIn("empty_edges", method_only_validation["invalid_graph_content"])

        missing_claim_link = deepcopy(graph)
        missing_claim_link["edges"] = [
            edge for edge in missing_claim_link["edges"]
            if edge["relation"] != "yields_claim"
        ]
        missing_claim_link["graph_fingerprint"] = graph_fingerprint(missing_claim_link)
        missing_claim_link["validation"] = validate_reasoning_graph_object(
            missing_claim_link, allow_unset_validation=True
        )
        invalid_links = validate_reasoning_graph_object(missing_claim_link)
        self.assertEqual(invalid_links["status"], "FAIL")
        self.assertTrue(invalid_links["invalid_claim_inference_links"])
        with self.assertRaisesRegex(ValueError, "invalid reasoning graph"):
            self.build_template({
                "sha256": report["sha256"],
                "reasoning_graph": missing_claim_link,
            })

    def test_semantic_review_rejects_missing_or_malformed_manifest_text_digest(self):
        from copy import deepcopy

        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        review = self.build_template(report)
        mutations = ("missing", "malformed")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                malformed_report = deepcopy(report)
                input_record = malformed_report["reproducibility_manifest"]["input"]
                if mutation == "missing":
                    input_record.pop("extracted_text_sha256")
                else:
                    input_record["extracted_text_sha256"] = "not-a-sha256"
                result = validate_semantic_review(review, malformed_report, text)
                self.assertEqual(result["status"], "REJECTED")
                self.assertTrue(any(
                    "extracted-text digest" in error for error in result["errors"]
                ))

    def test_semantic_review_rejects_source_text_change_outside_graph_extraction(self):
        original = (
            "# Introduction\nOriginal background context.\n"
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(original).to_dict()
        review = self.build_template(report)
        changed = original.replace("Original background context", "Different background context")
        self.assertNotEqual(changed, original)
        with self.assertRaisesRegex(ValueError, "extracted-text digest"):
            self.build_template(report, source_text=changed)

        rejected = validate_semantic_review(review, report, changed)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any(
            "extracted-text digest" in error for error in rejected["errors"]
        ))

    def test_semantic_review_rejects_malformed_graph_without_raising(self):
        from copy import deepcopy
        from sra.graph import graph_fingerprint, validate_reasoning_graph_object

        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        review = self.build_template(report)
        malformed = deepcopy(report)
        evidence = next(
            node for node in malformed["reasoning_graph"]["nodes"]
            if node["node_type"] == "evidence"
        )
        evidence.pop("node_id")
        malformed["reasoning_graph"]["graph_fingerprint"] = graph_fingerprint(
            malformed["reasoning_graph"]
        )
        malformed["reasoning_graph"]["validation"] = validate_reasoning_graph_object(
            malformed["reasoning_graph"], allow_unset_validation=True
        )

        rejected = validate_semantic_review(review, malformed, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any("graph integrity validation failed" in error.lower() for error in rejected["errors"]))

    def test_semantic_review_rejects_unhashable_schema_fingerprint_and_mode(self):
        from copy import deepcopy

        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = self.build_template(report)
        for field in ("schema_version", "graph_fingerprint", "review_mode"):
            for value in ([], {}):
                with self.subTest(field=field, value_type=type(value).__name__):
                    malformed = deepcopy(template)
                    malformed[field] = value
                    result = validate_semantic_review(malformed, report, text)
                    self.assertEqual(result["status"], "REJECTED")
                    self.assertTrue(result["errors"])

    def test_semantic_review_rejects_unhashable_graph_node_type_without_raising(self):
        from copy import deepcopy
        from sra.graph import graph_fingerprint, validate_reasoning_graph_object

        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        review = self.build_template(report)
        for invalid_node_type in ([], {}):
            with self.subTest(node_type=type(invalid_node_type).__name__):
                malformed = deepcopy(report)
                inference = next(
                    node for node in malformed["reasoning_graph"]["nodes"]
                    if node["node_type"] == "inference"
                )
                inference["node_type"] = invalid_node_type
                malformed["reasoning_graph"]["graph_fingerprint"] = graph_fingerprint(
                    malformed["reasoning_graph"]
                )
                malformed["reasoning_graph"]["validation"] = validate_reasoning_graph_object(
                    malformed["reasoning_graph"], allow_unset_validation=True
                )

                rejected = validate_semantic_review(review, malformed, text)
                self.assertEqual(rejected["status"], "REJECTED")
                self.assertTrue(any(
                    "graph integrity validation failed" in error.lower()
                    for error in rejected["errors"]
                ))

    def test_semantic_review_rejects_retargeted_evidence_after_fingerprint_rebuild(self):
        from copy import deepcopy
        from sra.graph import (
            _edge_id,
            _stable_id,
            graph_fingerprint,
            validate_reasoning_graph_object,
        )

        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "The unrelated biomarker concentration decreased after storage.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        tampered = deepcopy(report)
        graph = tampered["reasoning_graph"]
        evidence_nodes = [
            node for node in graph["nodes"] if node["node_type"] == "evidence"
        ]
        self.assertGreaterEqual(len(evidence_nodes), 2)
        target = evidence_nodes[0]
        replacement = evidence_nodes[1]
        old_id = target["node_id"]
        node_index = graph["nodes"].index(target)
        ordinal = sum(
            1 for node in graph["nodes"][: node_index + 1]
            if node["node_type"] == "evidence"
        )
        target["text"] = replacement["text"]
        target["source_location"] = deepcopy(replacement["source_location"])
        target["node_id"] = _stable_id(
            graph["source_sha256"],
            "evidence",
            target["source_location"]["line"],
            target["text"],
            ordinal,
        )
        new_id = target["node_id"]
        self.assertNotEqual(old_id, new_id)

        for edge in graph["edges"]:
            if edge["source"] == old_id:
                edge["source"] = new_id
            if edge["target"] == old_id:
                edge["target"] = new_id
            edge["edge_id"] = _edge_id(edge["source"], edge["target"], edge["relation"])

        graph["graph_fingerprint"] = graph_fingerprint(graph)
        graph["validation"] = validate_reasoning_graph_object(
            graph, allow_unset_validation=True
        )
        self.assertEqual(validate_reasoning_graph_object(graph)["status"], "PASS")

        with self.assertRaisesRegex(ValueError, "do not match the supplied manuscript source"):
            self.build_template(tampered)
        tampered_review = self.build_template(report)
        assessment = tampered_review["assessments"][0]
        assessment.update({
            "relation": "entailed",
            "confidence": 0.9,
            "rationale": "The linked source passage is asserted to support the claim.",
            "source_quotes": [target["text"]],
        })
        tampered_review["reviewer"] = {
            "name": "Adversarial reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }

        rejected = validate_semantic_review(tampered_review, tampered, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any(
            "reconstructed from the audited manuscript source" in error
            for error in rejected["errors"]
        ))

    def test_legacy_semantic_reviews_v11_and_v12_remain_importable(self):
        from copy import deepcopy
        from sra.graph import legacy_graph_fingerprint_v1_1

        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = self.build_template(report)
        evidence_id = template["assessments"][0]["evidence_node_ids"][0]
        evidence = next(
            node for node in report["reasoning_graph"]["nodes"]
            if node["node_id"] == evidence_id
        )

        for version in ("1.1", "1.2"):
            with self.subTest(version=version):
                legacy = deepcopy(template)
                legacy["schema_version"] = version
                legacy.pop("graph_schema_version")
                legacy.pop("graph_fingerprint_algorithm")
                legacy.pop("evidence_catalog")
                legacy["graph_fingerprint"] = legacy_graph_fingerprint_v1_1(
                    report["reasoning_graph"]
                )
                legacy["reviewer"] = {
                    "name": "Legacy reviewer",
                    "model_or_agent": f"legacy-{version}",
                    "reviewed_at_utc": "2026-11-02T00:00:00Z",
                }
                legacy["assessments"][0].pop("reviewer_selected_evidence_node_ids")
                legacy["assessments"][0].update({
                    "relation": "entailed",
                    "confidence": 0.9,
                    "rationale": "The result passage matches the conclusion claim.",
                    "source_quotes": [evidence["text"]],
                })
                accepted = validate_semantic_review(legacy, report, text)
                self.assertEqual(accepted["status"], "ACCEPTED_FOR_REVIEW", accepted["errors"])

    def test_semantic_review_rejects_graph_bound_to_different_manuscript_hash(self):
        from copy import deepcopy
        from sra.graph import graph_fingerprint, validate_reasoning_graph_object
        from sra.semantic_review import build_semantic_review_template

        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        review = self.build_template(report)

        mismatched_report = deepcopy(report)
        mismatched_report["reasoning_graph"]["source_sha256"] = "f" * 64
        mismatched_report["reasoning_graph"]["graph_fingerprint"] = graph_fingerprint(
            mismatched_report["reasoning_graph"]
        )
        mismatched_report["reasoning_graph"]["validation"] = validate_reasoning_graph_object(
            mismatched_report["reasoning_graph"], allow_unset_validation=True
        )

        with self.assertRaisesRegex(ValueError, "source SHA-256"):
            self.build_template(mismatched_report)

        rejected = validate_semantic_review(review, mismatched_report, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any(
            "graph source SHA-256" in error
            for error in rejected["errors"]
        ))

    def test_semantic_review_rejects_graph_schema_or_algorithm_mismatch(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = self.build_template(report)
        evidence_id = template["assessments"][0]["evidence_node_ids"][0]
        evidence = next(
            node for node in report["reasoning_graph"]["nodes"]
            if node["node_id"] == evidence_id
        )
        template["assessments"][0].update({
            "relation": "entailed",
            "confidence": 0.9,
            "rationale": "The result passage directly supports the direction of the stated conclusion.",
            "source_quotes": [evidence["text"]],
        })
        template["reviewer"] = {
            "name": "Schema reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }

        wrong_graph_version = json.loads(json.dumps(template))
        wrong_graph_version["graph_schema_version"] = "999"
        result_version = validate_semantic_review(wrong_graph_version, report, text)
        self.assertEqual(result_version["status"], "REJECTED")
        self.assertTrue(any("graph_schema_version" in error for error in result_version["errors"]))

        wrong_algorithm = json.loads(json.dumps(template))
        wrong_algorithm["graph_fingerprint_algorithm"] = "legacy-unversioned"
        result_algorithm = validate_semantic_review(wrong_algorithm, report, text)
        self.assertEqual(result_algorithm["status"], "REJECTED")
        self.assertTrue(any("graph_fingerprint_algorithm" in error for error in result_algorithm["errors"]))

    def test_semantic_review_rejects_wrong_claim_link_and_missing_reviewer(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score.\n"
            "The intervention decreased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = self.build_template(report)
        assessment = template["assessments"][0]
        assessment.update({
            "relation": "entailed",
            "confidence": 0.9,
            "rationale": "Direct match.",
            "source_quotes": ["The intervention increased the measured score."],
        })
        template["reviewer"] = {"name": "", "model_or_agent": "", "reviewed_at_utc": ""}
        other_claim_id = next(
            node["node_id"] for node in report["reasoning_graph"]["nodes"]
            if node["node_type"] == "claim" and node["node_id"] != assessment["claim_node_id"]
        )
        assessment["claim_node_id"] = other_claim_id
        rejected = validate_semantic_review(template, report, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any("reviewer.name" in err for err in rejected["errors"]))
        self.assertTrue(any("does not match" in err for err in rejected["errors"]))

    def test_semantic_review_quote_must_match_the_selected_evidence_node(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = self.build_template(report)
        assessment = template["assessments"][0]
        method_node = next(
            node for node in report["reasoning_graph"]["nodes"]
            if node["node_type"] == "method"
        )
        assessment.update({
            "relation": "entailed",
            "confidence": 0.9,
            "rationale": "A quote from the methods section is not result evidence.",
            "source_quotes": [method_node["text"]],
        })
        template["reviewer"] = {
            "name": "Test reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        rejected = validate_semantic_review(template, report, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any("selected evidence" in err for err in rejected["errors"]))

    def test_semantic_review_rejects_extreme_confidence_without_crashing(self):
        text = """# Methods
A randomized study was conducted.
# Results
The intervention increased the measured score.
# Conclusion
The intervention increased the measured score.
"""
        report = self.audit_text(text).to_dict()
        template = self.build_template(report)
        template["reviewer"] = {
            "name": "Test reviewer",
            "model_or_agent": "unit-test",
            "reviewed_at_utc": "2026-11-02T00:00:00Z",
        }
        template["assessments"][0].update({
            "relation": "entailed",
            "confidence": 10**1000,
            "rationale": "Extreme value test.",
            "source_quotes": ["The intervention increased the measured score."],
        })
        rejected = validate_semantic_review(template, report, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any("confidence" in err for err in rejected["errors"]))

    def test_semantic_review_rejects_unhashable_node_id_inputs_without_crashing(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = self.build_template(report)
        template["assessments"][0]["evidence_node_ids"] = [{"not": "an id"}]
        rejected = validate_semantic_review(template, report, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any("evidence_node_ids" in err for err in rejected["errors"]))

    def test_rejected_semantic_review_still_renders_a_markdown_report(self):
        text = """# Methods
A randomized study was conducted.
# Results
The intervention increased the measured score.
# Conclusion
The intervention increased the measured score.
"""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        source = Path(tmp.name) / "paper.md"
        review_path = Path(tmp.name) / "review.json"
        source.write_text(text, encoding="utf-8")
        report = audit_file(source)
        self._last_source_text = text
        template = self.build_template(report.to_dict())
        template["reviewer"] = {"name": "", "model_or_agent": "", "reviewed_at_utc": ""}
        assessment = template["assessments"][0]
        assessment.update({
            "relation": "entailed",
            "confidence": "not-a-number",
            "rationale": "Invalid test fixture.",
            "source_quotes": ["The intervention increased the measured score."],
        })
        review_path.write_text(json.dumps(template), encoding="utf-8")
        rejected_report = audit_file(source, str(review_path))
        markdown = to_markdown(rejected_report)
        self.assertEqual(rejected_report.semantic_review["status"], "REJECTED")
        self.assertIn("confidence invalid", markdown)

    def test_semantic_review_rejects_wrong_source_hash_and_fabricated_quote(self):
        text = (
            "# Methods\nA randomized study was conducted.\n"
            "# Results\nThe intervention increased the measured score.\n"
            "# Conclusion\nThe intervention increased the measured score."
        )
        report = self.audit_text(text).to_dict()
        template = self.build_template(report)
        assessment = template["assessments"][0]
        assessment.update({
            "relation": "partially_supported",
            "confidence": 0.8,
            "rationale": "Partially supported.",
            "source_quotes": ["A fabricated sentence not present in the document."],
        })
        template["source_sha256"] = "0" * 64
        rejected = validate_semantic_review(template, report, text)
        self.assertEqual(rejected["status"], "REJECTED")
        self.assertTrue(any("SHA-256" in err for err in rejected["errors"]))
        self.assertTrue(any("quote" in err for err in rejected["errors"]))

    def test_turkish_discussion_is_not_confused_with_results(self):
        report = self.audit_text(
            "# Yöntem\nKontrollü deney.\n"
            "# Bulgular\nUygulama ölçülen skoru artırdı.\n"
            "# Tartışma\nBulgular uygulamanın etkisini desteklemektedir."
        )
        self.assertGreaterEqual(len(report.claim_evidence_candidates), 1)
        self.assertEqual(report.section_names[:3], ["Yöntem", "Bulgular", "Tartışma"])
        self.assertEqual(report.claim_evidence_candidates[0].claim_section, "Tartışma")


class StatisticalVerificationTests(unittest.TestCase):
    def test_welch_recalculation_matches_rounded_reported_values(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 25},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
            "reported": {
                "mean_difference": 1.0,
                "t": 3.536,
                "df": 48.0,
                "p_two_sided": 0.001,
            },
            "tolerances": {
                "mean_difference": 0.001,
                "t": 0.01,
                "df": 0.1,
                "p_two_sided": 0.001,
            },
        }
        result = verify_welch_t_test(spec, input_sha256="a" * 64)
        self.assertEqual(result["status"], "PASS")
        self.assertAlmostEqual(result["calculated"]["mean_difference"], 1.0)
        self.assertAlmostEqual(result["calculated"]["df"], 48.0)
        self.assertEqual(len(result["input_sha256"]), 64)

    def test_welch_result_matches_scipy_reference_implementation(self):
        from scipy import stats

        spec = {
            "test": "welch_t",
            "group_a": {"mean": 8.2, "sd": 2.4, "n": 31},
            "group_b": {"mean": 6.7, "sd": 1.8, "n": 27},
        }
        result = verify_welch_t_test(spec)
        reference = stats.ttest_ind_from_stats(
            mean1=8.2, std1=2.4, nobs1=31,
            mean2=6.7, std2=1.8, nobs2=27,
            equal_var=False,
        )
        self.assertAlmostEqual(result["calculated"]["t"], float(reference.statistic), places=12)
        self.assertAlmostEqual(result["calculated"]["p_two_sided"], float(reference.pvalue), places=12)

    def test_welch_recalculation_detects_mismatched_t_statistic(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 25},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
            "reported": {"t": 1.2},
            "tolerances": {"t": 0.01},
        }
        result = verify_welch_t_test(spec)
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["reported_checks"][0]["status"], "FAIL")

    def test_default_tolerance_uses_reported_decimal_precision(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 25},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
            "reported": {"p_two_sided": 0.02},
        }
        result = verify_welch_t_test(spec)
        check = result["reported_checks"][0]
        self.assertEqual(check["status"], "FAIL")
        self.assertAlmostEqual(check["absolute_tolerance"], 0.005)

    def test_welch_rejects_positive_standard_error_contribution_underflow(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 0.0, "sd": 5e-324, "n": 10},
            "group_b": {"mean": 0.0, "sd": 1.0, "n": 10},
        }
        with self.assertRaisesRegex(ValueError, "group_a standard-error contribution underflowed"):
            verify_welch_t_test(spec)

    def test_welch_rejects_nonzero_decimal_that_underflows_to_float_zero(self):
        from decimal import Decimal

        spec = {
            "test": "welch_t",
            "group_a": {"mean": 0, "sd": 1, "n": 10},
            "group_b": {"mean": 0, "sd": 1, "n": 10},
            "reported": {"mean_difference": Decimal("1e-400")},
        }
        with self.assertRaisesRegex(ValueError, "too small to be represented"):
            verify_welch_t_test(spec)

    def test_welch_rejects_decimal_precision_lost_during_float_conversion(self):
        from decimal import Decimal

        spec = {
            "test": "welch_t",
            "group_a": {"mean": 0, "sd": 1, "n": 10},
            "group_b": {"mean": 0, "sd": 1, "n": 10},
            "reported": {"mean_difference": Decimal("1.000000000000000000001")},
        }
        with self.assertRaisesRegex(ValueError, "more decimal precision"):
            verify_welch_t_test(spec)

    def test_welch_rejects_integer_precision_lost_during_float_conversion(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 9007199254740993, "sd": 1, "n": 10},
            "group_b": {"mean": 0, "sd": 1, "n": 10},
        }
        with self.assertRaisesRegex(ValueError, "not exactly representable"):
            verify_welch_t_test(spec)

    def test_precision_tolerance_rejects_decimal_resolution_below_float_range(self):
        from decimal import Decimal
        from sra.stats import _display_precision_tolerance

        precise_one = Decimal("1." + "0" * 400)
        with self.assertRaisesRegex(ValueError, "too small to be represented"):
            _display_precision_tolerance(precise_one)

    def test_verify_stats_file_rejects_all_nonstandard_json_constants(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "nonstandard.json"
            prefix = (
                '{"test":"welch_t","group_a":{"mean":4.2,"sd":1.3,"n":23},'
                '"group_b":{"mean":3.1,"sd":2.0,"n":31},"unused_metadata":'
            )
            for constant in ("NaN", "Infinity", "-Infinity"):
                with self.subTest(constant=constant):
                    source.write_text(prefix + constant + "}", encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Non-standard JSON numeric constant"):
                        verify_stats_file(source)

    def test_unknown_reported_decimal_fields_remain_json_serializable(self):
        import json
        from decimal import Decimal

        spec = {
            "test": "welch_t",
            "group_a": {"mean": 4.2, "sd": 1.3, "n": 23},
            "group_b": {"mean": 3.1, "sd": 2.0, "n": 31},
            "reported": {
                "extra_metric": {
                    "regular": Decimal("1.25"),
                    "high_precision": Decimal("1.000000000000000000001"),
                    "below_float_range": Decimal("1e-400"),
                }
            },
        }
        result = verify_welch_t_test(spec)
        self.assertEqual(result["reported_checks"][0]["status"], "NOT_VERIFIED")
        reported = result["reported_checks"][0]["reported"]
        self.assertEqual(reported["regular"], 1.25)
        self.assertEqual(reported["high_precision"], "1.000000000000000000001")
        self.assertEqual(reported["below_float_range"], "1E-400")
        json.dumps(result, allow_nan=False)

    def test_welch_output_discloses_pooled_effect_size_variance_assumption(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 1.0, "sd": 1.0, "n": 10},
            "group_b": {"mean": 0.0, "sd": 10.0, "n": 100},
        }
        result = verify_welch_t_test(spec)
        self.assertIn("Pooled-SD Cohen's d", result["effect_size_method"])
        self.assertTrue(any("common within-group variance" in item
                            for item in result["effect_size_assumptions"]))
        self.assertTrue(any("normally distributed" in item
                            for item in result["effect_size_assumptions"]))
        self.assertTrue(any("not heteroskedasticity-adjusted" in item
                            for item in result["limitations"]))

    def test_pooled_hedges_effect_size_matches_independent_reference_with_unequal_variances(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 2.0, "sd": 1.0, "n": 10},
            "group_b": {"mean": 0.0, "sd": 10.0, "n": 100},
        }
        result = verify_welch_t_test(spec)
        calculated = result["calculated"]

        degrees = 10 + 100 - 2
        reference_pooled_sd = math.sqrt(
            ((10 - 1) * (1.0 ** 2) + (100 - 1) * (10.0 ** 2)) / degrees
        )
        reference_cohen_d = (2.0 - 0.0) / reference_pooled_sd
        # Independent direct gamma-ratio expression for this moderate df;
        # deliberately does not call the implementation's _hedges_correction.
        reference_j = (
            math.gamma(degrees / 2)
            / (math.sqrt(degrees / 2) * math.gamma((degrees - 1) / 2))
        )
        reference_hedges_g = reference_cohen_d * reference_j

        self.assertAlmostEqual(calculated["cohen_d_pooled"], reference_cohen_d, places=14)
        self.assertAlmostEqual(calculated["hedges_g"], reference_hedges_g, places=14)
        self.assertNotAlmostEqual(
            calculated["cohen_d_pooled"],
            (2.0 / math.sqrt((1.0 ** 2 + 10.0 ** 2) / 2)),
            places=3,
        )

    def test_welch_rejects_zero_reported_p_value(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 25},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
            "reported": {"p_two_sided": 0.0},
        }
        with self.assertRaises(ValueError):
            verify_welch_t_test(spec)

    def test_checked_in_welch_example_file_parses_and_passes(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "welch_t_example.json"
        result = verify_stats_file(example)
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(len(result["input_sha256"]), 64)

    def test_welch_scaled_formula_handles_variance_squares_that_would_overflow(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 0.0, "sd": 1e308, "n": 10},
            "group_b": {"mean": 0.0, "sd": 1e308, "n": 10},
        }
        result = verify_welch_t_test(spec)
        calculated = result["calculated"]
        self.assertAlmostEqual(calculated["standard_error"] / 1e308, (2 / 10) ** 0.5)
        self.assertAlmostEqual(calculated["df"], 18.0)
        self.assertTrue(all(math.isfinite(value) for value in calculated["confidence_interval_95"]))
        self.assertEqual(calculated["cohen_d_pooled"], 0.0)

    def test_welch_scaled_formula_handles_tiny_variance_contributions(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 1e-150, "sd": 1e-150, "n": 10},
            "group_b": {"mean": 0.0, "sd": 1e-150, "n": 10},
        }
        result = verify_welch_t_test(spec)
        calculated = result["calculated"]
        self.assertTrue(math.isfinite(calculated["standard_error"]))
        self.assertAlmostEqual(calculated["df"], 18.0)
        self.assertAlmostEqual(calculated["t"], 2.23606797749979)

    def test_hedges_correction_stays_below_one_for_very_large_degrees(self):
        for sample_size, expected_ratio in (
            (500_000_000, 0.99999999925),
            (500_000_000_000, 0.99999999999925),
        ):
            with self.subTest(sample_size=sample_size):
                spec = {
                    "test": "welch_t",
                    "group_a": {"mean": 1e-5, "sd": 1.0, "n": sample_size},
                    "group_b": {"mean": 0.0, "sd": 1.0, "n": sample_size},
                }
                calculated = verify_welch_t_test(spec)["calculated"]
                ratio = calculated["hedges_g"] / calculated["cohen_d_pooled"]
                self.assertGreater(ratio, 0.0)
                self.assertLess(ratio, 1.0)
                self.assertAlmostEqual(ratio, expected_ratio, delta=1e-15)

    def test_pooled_standard_deviation_does_not_underflow_to_missing_effect_sizes(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 0.0, "sd": 0.0, "n": 10**200},
            "group_b": {"mean": 0.0, "sd": 1e-70, "n": 10},
        }
        calculated = verify_welch_t_test(spec)["calculated"]
        self.assertGreater(calculated["cohen_d_pooled"], -1e-12)
        self.assertEqual(calculated["cohen_d_pooled"], 0.0)
        self.assertEqual(calculated["hedges_g"], 0.0)

    def test_welch_rejects_p_value_underflow_instead_of_reporting_zero(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 1e20, "sd": 1.0, "n": 10},
            "group_b": {"mean": 0.0, "sd": 1.0, "n": 10},
        }
        with self.assertRaisesRegex(ValueError, "p-value underflowed"):
            verify_welch_t_test(spec)

    def test_welch_rejects_mean_difference_overflow(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 1e308, "sd": 1.0, "n": 10},
            "group_b": {"mean": -1e308, "sd": 1.0, "n": 10},
        }
        with self.assertRaisesRegex(ValueError, "mean difference"):
            verify_welch_t_test(spec)

    def test_cli_reports_numeric_overflow_without_writing_nonstandard_json(self):
        import contextlib
        import io
        from unittest.mock import patch
        from sra.cli import main

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "overflow.json"
            output = Path(directory) / "result.json"
            source.write_text(json.dumps({
                "test": "welch_t",
                "group_a": {"mean": 1e308, "sd": 1.0, "n": 10},
                "group_b": {"mean": -1e308, "sd": 1.0, "n": 10},
            }), encoding="utf-8")
            stderr = io.StringIO()
            with patch("sys.argv", ["sra", "verify-stats", str(source), "--out", str(output)]):
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as caught:
                        main()
            self.assertEqual(caught.exception.code, 2)
            self.assertIn("mean difference", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_cli_handles_extreme_decimal_exponent_without_traceback(self):
        import contextlib
        import io
        from unittest.mock import patch
        from sra.cli import main

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "extreme-exponent.json"
            output = Path(directory) / "result.json"
            source.write_text(
                '{"test":"welch_t","group_a":{"mean":1,"sd":1,"n":10},'
                '"group_b":{"mean":0,"sd":1,"n":10},'
                '"reported":{"mean_difference":1e-999999999}}',
                encoding="utf-8",
            )
            stderr = io.StringIO()
            with patch("sys.argv", ["sra", "verify-stats", str(source), "--out", str(output)]):
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as caught:
                        main()
            self.assertEqual(caught.exception.code, 2)
            self.assertIn("too small to be represented", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_welch_rejects_invalid_sample_sizes(self):
        spec = {
            "test": "welch_t",
            "group_a": {"mean": 5.0, "sd": 1.0, "n": 1},
            "group_b": {"mean": 4.0, "sd": 1.0, "n": 25},
        }
        with self.assertRaises(ValueError):
            verify_welch_t_test(spec)


class ModelClientTests(unittest.TestCase):
    def test_extracts_json_from_model_fenced_response(self):
        from sra.model_client import _extract_json_object
        self.assertEqual(_extract_json_object(chr(96)*3 + 'json\n{"ok": true}\n' + chr(96)*3), {"ok": True})

    def test_model_api_response_body_reads_are_bounded(self):
        import io
        from sra.model_client import _read_bounded_response

        class FakeResponse:
            def __init__(self, payload, headers=None):
                self.stream = io.BytesIO(payload)
                self.headers = headers or {}
                self.read_sizes = []

            def read(self, size=-1):
                self.read_sizes.append(size)
                return self.stream.read(size)

        allowed = FakeResponse(b"1234")
        self.assertEqual(_read_bounded_response(allowed, maximum=4), b"1234")
        self.assertEqual(allowed.read_sizes, [5])

        oversized = FakeResponse(b"12345")
        with self.assertRaisesRegex(ValueError, "4-byte response size limit"):
            _read_bounded_response(oversized, maximum=4)
        self.assertEqual(oversized.read_sizes, [5])

        declared_oversized = FakeResponse(b"", {"Content-Length": "5"})
        with self.assertRaisesRegex(ValueError, "4-byte response size limit"):
            _read_bounded_response(declared_oversized, maximum=4)
        self.assertEqual(declared_oversized.read_sizes, [])

    def test_model_api_rejects_non_ascii_or_non_decimal_content_length(self):
        import io
        from sra.model_client import _read_bounded_response

        class FakeResponse:
            def __init__(self, content_length):
                self.headers = {"Content-Length": content_length}
                self.stream = io.BytesIO(b"x")
                self.read_called = False

            def read(self, size=-1):
                self.read_called = True
                return self.stream.read(size)

        for content_length in ("+1", "1_0", "٥", "", "-1", "abc", " 1"):
            with self.subTest(content_length=content_length):
                response = FakeResponse(content_length)
                with self.assertRaisesRegex(ValueError, "ASCII digits only"):
                    _read_bounded_response(response, maximum=4)
                self.assertFalse(response.read_called)

    def test_model_api_http_error_body_also_uses_bounded_reader(self):
        import io
        from urllib.error import HTTPError
        from unittest.mock import patch
        from sra.model_client import MAX_MODEL_API_RESPONSE_BYTES, request_single_model_review

        error_body = io.BytesIO(b"")
        error = HTTPError(
            "https://example.test/v1/chat/completions", 503, "Unavailable",
            {"Content-Length": str(MAX_MODEL_API_RESPONSE_BYTES + 1)},
            error_body,
        )
        with patch.dict("os.environ", {"SRA_TEST_KEY": "test-key"}):
            with patch("sra.model_client._open_api_request", side_effect=error):
                with self.assertRaisesRegex(RuntimeError, "response size limit"):
                    request_single_model_review(
                        {"review_mode": "single"}, "paper", model="m",
                        base_url="https://example.test/v1", api_key_env="SRA_TEST_KEY"
                    )
        self.assertTrue(error_body.closed)

    def test_model_response_parser_rejects_nonstandard_json_constants(self):
        from sra.model_client import _extract_json_object

        for constant in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(constant=constant):
                with self.assertRaisesRegex(ValueError, "Non-standard JSON numeric constant"):
                    _extract_json_object(f'{{"confidence": {constant}}}')

    def test_model_response_parser_rejects_non_finite_or_lossy_json_numbers(self):
        from sra.model_client import _extract_json_object

        invalid_numbers = (
            ("1e9999", "outside the supported floating-point range"),
            ("1e-9999", "too small for floating-point representation"),
            ("1e-99999999999999999999999999", "outside the supported floating-point range"),
            ("1.000000000000000000001", "precision beyond floating-point representation"),
        )
        for number, message in invalid_numbers:
            with self.subTest(number=number):
                with self.assertRaisesRegex(ValueError, message):
                    _extract_json_object(f'{{"metric": {number}}}')

    def test_rejects_non_object_model_response(self):
        from sra.model_client import _extract_json_object
        with self.assertRaises(ValueError):
            _extract_json_object('[{"not":"an object"}]')

    def test_single_model_requires_single_template_and_api_key(self):
        from unittest.mock import patch
        from sra.model_client import request_single_model_review
        with self.assertRaises(ValueError):
            request_single_model_review({"review_mode":"parallel"}, "paper", model="m", base_url="https://example.test/v1")
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "not set"):
                request_single_model_review({"review_mode":"single"}, "paper", model="m",
                    base_url="https://example.test/v1", api_key_env="SRA_TEST_KEY")

    def test_authenticated_request_opener_installs_redirect_blocker(self):
        from unittest.mock import Mock, patch
        from urllib.request import Request
        from sra.model_client import _NoRedirectHandler, _open_api_request

        request = Request("https://trusted.example/v1/chat/completions", data=b"{}")
        response = object()
        opener = Mock()
        opener.open.return_value = response
        with patch("sra.model_client.build_opener", return_value=opener) as build_opener:
            self.assertIs(_open_api_request(request, timeout=17), response)
        build_opener.assert_called_once_with(_NoRedirectHandler)
        opener.open.assert_called_once_with(request, timeout=17)

    def test_local_http_opener_bypasses_environment_proxies(self):
        from unittest.mock import Mock, patch
        from urllib.request import ProxyHandler, Request
        from sra.model_client import _NoRedirectHandler, _open_api_request

        request = Request("http://127.0.0.1:8000/v1/chat/completions", data=b"{}")
        opener = Mock()
        opener.open.return_value = object()
        with patch("sra.model_client.build_opener", return_value=opener) as build_opener:
            _open_api_request(request, timeout=9)
        handlers = build_opener.call_args.args
        self.assertEqual(len(handlers), 2)
        self.assertIsInstance(handlers[0], ProxyHandler)
        self.assertEqual(handlers[0].proxies, {})
        self.assertIs(handlers[1], _NoRedirectHandler)
        opener.open.assert_called_once_with(request, timeout=9)

    def test_all_ipv4_loopback_addresses_are_allowed_for_local_http(self):
        import json
        from unittest.mock import patch
        from sra.model_client import request_single_model_review

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size=-1):
                return json.dumps({"choices": [{"message": {"content": '{"ok": true}'}}]}).encode()

        with patch.dict("os.environ", {"SRA_TEST_KEY": "test-key"}):
            for host in ("127.0.0.1", "127.0.0.2", "127.255.255.254", "[::1]", "localhost"):
                with self.subTest(host=host):
                    with patch("sra.model_client._open_api_request", return_value=FakeResponse()) as mocked:
                        result = request_single_model_review(
                            {"review_mode": "single"}, "paper", model="m",
                            base_url=f"http://{host}:8000/v1", api_key_env="SRA_TEST_KEY"
                        )
                    self.assertEqual(result, {"ok": True})
                    self.assertEqual(
                        mocked.call_args.args[0].full_url,
                        f"http://{host}:8000/v1/chat/completions",
                    )

    def test_local_http_redirect_never_reaches_redirect_target(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from unittest.mock import patch
        from sra.model_client import request_single_model_review

        observed = {
            "redirect_requests": 0, "target_requests": 0,
            "proxy_requests": 0, "authorization": None,
        }
        target = None

        class TargetHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                observed["target_requests"] += 1
                self.send_response(200)
                self.end_headers()

            def log_message(self, *args):
                pass

        target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                observed["redirect_requests"] += 1
                observed["authorization"] = self.headers.get("Authorization")
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{target.server_port}/redirect-target")
                self.end_headers()

            def log_message(self, *args):
                pass

        redirect = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)

        class ProxyServerHandler(BaseHTTPRequestHandler):
            def do_POST(self):
                observed["proxy_requests"] += 1
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"choices":[{"message":{"content":"{\"ok\":true}"}}]}')

            def log_message(self, *args):
                pass

        proxy_server = ThreadingHTTPServer(("127.0.0.1", 0), ProxyServerHandler)
        proxy_url = f"http://127.0.0.1:{proxy_server.server_port}"
        threads = [
            threading.Thread(target=target.serve_forever, daemon=True),
            threading.Thread(target=redirect.serve_forever, daemon=True),
            threading.Thread(target=proxy_server.serve_forever, daemon=True),
        ]
        for thread in threads:
            thread.start()
        try:
            with patch.dict("os.environ", {
                "SRA_TEST_KEY": "integration-test-key",
                "HTTP_PROXY": proxy_url,
                "http_proxy": proxy_url,
                "NO_PROXY": "",
                "no_proxy": "",
            }):
                with self.assertRaisesRegex(RuntimeError, "HTTP 302"):
                    request_single_model_review(
                        {"review_mode": "single"}, "paper", model="test-model",
                        base_url=f"http://127.0.0.1:{redirect.server_port}/v1",
                        api_key_env="SRA_TEST_KEY", timeout=3,
                    )
            self.assertEqual(observed["redirect_requests"], 1)
            self.assertEqual(observed["target_requests"], 0)
            self.assertEqual(observed["proxy_requests"], 0)
            self.assertEqual(observed["authorization"], "Bearer integration-test-key")
        finally:
            redirect.shutdown()
            target.shutdown()
            proxy_server.shutdown()
            redirect.server_close()
            target.server_close()
            proxy_server.server_close()
            for thread in threads:
                thread.join(timeout=2)

    def test_authenticated_model_client_rejects_http_redirects(self):
        from email.message import Message
        from urllib.error import HTTPError
        from urllib.request import Request
        from sra.model_client import _NoRedirectHandler

        request = Request(
            "https://trusted.example/v1/chat/completions", data=b"{}",
            headers={"Authorization": "Bearer test-key"}, method="POST"
        )
        with self.assertRaises(HTTPError) as caught:
            _NoRedirectHandler().redirect_request(
                request, None, 302, "Found", Message(),
                "https://untrusted.example/collect"
            )
        self.assertEqual(caught.exception.code, 302)
        self.assertIn("Redirects are disabled", caught.exception.msg)
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")

    def test_single_model_rejects_nonstandard_constants_in_provider_envelope(self):
        import json
        from unittest.mock import patch
        from sra.model_client import request_single_model_review

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size=-1):
                return b'{"choices":[{"message":{"content":"{}"}}],"usage":{"total_tokens":NaN}}'

        with patch.dict("os.environ", {"SRA_TEST_KEY": "test-key"}):
            with patch("sra.model_client._open_api_request", return_value=FakeResponse()):
                with self.assertRaisesRegex(ValueError, "Non-standard JSON numeric constant"):
                    request_single_model_review(
                        {"review_mode": "single"}, "paper", model="m",
                        base_url="https://example.test/v1", api_key_env="SRA_TEST_KEY"
                    )

    def test_single_model_rejects_remote_plain_http_before_sending_api_key(self):
        from unittest.mock import patch
        from sra.model_client import request_single_model_review

        with patch.dict("os.environ", {"SRA_TEST_KEY": "must-not-leak"}):
            with patch("sra.model_client._open_api_request") as mocked:
                with self.assertRaisesRegex(ValueError, "HTTPS for remote model APIs"):
                    request_single_model_review(
                        {"review_mode": "single"}, "paper", model="m",
                        base_url="http://model.example/v1", api_key_env="SRA_TEST_KEY"
                    )
                mocked.assert_not_called()

    def test_single_model_rejects_empty_query_and_fragment_delimiters(self):
        from unittest.mock import patch
        from sra.model_client import request_single_model_review

        with patch.dict("os.environ", {"SRA_TEST_KEY": "test-key"}):
            for base_url in (
                "https://example.test/v1?",
                "https://example.test/v1#",
            ):
                with self.subTest(base_url=base_url):
                    with patch("sra.model_client._open_api_request") as mocked:
                        with self.assertRaisesRegex(ValueError, "delimiters"):
                            request_single_model_review(
                                {"review_mode": "single"}, "paper", model="m",
                                base_url=base_url, api_key_env="SRA_TEST_KEY"
                            )
                        mocked.assert_not_called()

    def test_single_model_accepts_encoded_query_fragment_characters_in_path(self):
        import json
        from unittest.mock import patch
        from sra.model_client import request_single_model_review

        class FakeResponse:
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size=-1):
                return json.dumps({"choices": [{"message": {"content": '{"ok": true}'}}]}).encode()

        with patch.dict("os.environ", {"SRA_TEST_KEY": "test-key"}):
            with patch("sra.model_client._open_api_request", return_value=FakeResponse()) as mocked:
                result = request_single_model_review(
                    {"review_mode": "single"}, "paper", model="m",
                    base_url="https://example.test/v1/%3F/%23", api_key_env="SRA_TEST_KEY"
                )
        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            mocked.call_args.args[0].full_url,
            "https://example.test/v1/%3F/%23/chat/completions",
        )

    def test_single_model_rejects_credentials_and_query_in_base_url(self):
        from unittest.mock import patch
        from sra.model_client import request_single_model_review

        with patch.dict("os.environ", {"SRA_TEST_KEY": "test-key"}):
            for base_url in (
                "https://user:password@example.test/v1",
                "https://%75ser:password@example.test/v1",
                "https://example.test/v1?redirect=http://other.test",
                "https://example.test/v1#fragment",
            ):
                with self.subTest(base_url=base_url):
                    with patch("sra.model_client._open_api_request") as mocked:
                        with self.assertRaises(ValueError):
                            request_single_model_review(
                                {"review_mode": "single"}, "paper", model="m",
                                base_url=base_url, api_key_env="SRA_TEST_KEY"
                            )
                        mocked.assert_not_called()

    def test_review_model_cli_does_not_write_nonstandard_json(self):
        import contextlib
        import io
        import math
        from unittest.mock import patch
        from sra.cli import main

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "review.json"
            fake_report = type("FakeReport", (), {"to_dict": lambda self: {}})()
            fake_document = type("FakeDocument", (), {"text": "paper"})()
            stderr = io.StringIO()
            with (
                patch("sys.argv", [
                    "sra", "review-model", "input.md", "--model", "model",
                    "--base-url", "https://example.test/v1", "--api-key-env", "SRA_TEST_KEY",
                    "--out", str(output),
                ]),
                patch("sra.cli.audit_parsed_document", return_value=fake_report),
                patch("sra.cli.load_document", return_value=fake_document),
                patch("sra.cli.build_semantic_review_template", return_value={"review_mode": "single"}),
                patch("sra.cli.request_single_model_review", return_value={"confidence": math.nan}),
                patch("sra.cli.validate_semantic_review", return_value={"status": "REJECTED", "errors": ["confidence must be finite"]}),
                contextlib.redirect_stderr(stderr),
            ):
                with self.assertRaises(SystemExit) as caught:
                    main()
            self.assertEqual(caught.exception.code, 2)
            self.assertIn("Out of range float values", stderr.getvalue())
            self.assertFalse(output.exists())

    def test_single_model_posts_to_openai_compatible_endpoint(self):
        import json
        from unittest.mock import patch
        from sra.model_client import request_single_model_review

        class FakeResponse:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, size=-1):
                return json.dumps({"choices":[{"message":{"content":'{"review_mode":"single"}'}}]}).encode()

        template = {"review_mode":"single", "assessments":[]}
        with patch.dict("os.environ", {"SRA_TEST_KEY":"test-key"}):
            with patch("sra.model_client._open_api_request", return_value=FakeResponse()) as mocked:
                result = request_single_model_review(
                    template, "Full manuscript", model="test-model",
                    base_url="https://example.test/v1", api_key_env="SRA_TEST_KEY"
                )
        self.assertEqual(result, {"review_mode":"single"})
        request = mocked.call_args.args[0]
        self.assertEqual(request.full_url, "https://example.test/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        sent = json.loads(request.data.decode())
        self.assertEqual(sent["model"], "test-model")
        self.assertEqual(sent["temperature"], 0)

        # Local inference servers may use HTTP because traffic stays on loopback.
        with patch.dict("os.environ", {"SRA_TEST_KEY": "test-key"}):
            with patch("sra.model_client._open_api_request", return_value=FakeResponse()) as local_mock:
                request_single_model_review(
                    template, "Full manuscript", model="test-model",
                    base_url="http://127.0.0.1:8000/v1", api_key_env="SRA_TEST_KEY"
                )
        self.assertEqual(
            local_mock.call_args.args[0].full_url,
            "http://127.0.0.1:8000/v1/chat/completions",
        )


if __name__ == "__main__":
    unittest.main()
