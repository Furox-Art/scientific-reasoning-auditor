"""Regression tests for build artifact reproducibility and safe normalization."""
import io
import os
import tarfile
import tempfile
import unittest
from pathlib import Path
from tools.normalize_sdist import normalize_sdist_file
from tools.verify_reproducible_distributions import verify_identical_distributions


def make_archive(path, timestamp, name="scientific_reasoning_auditor-0.5.2/file.txt", data=b"evidence"):
    with tarfile.open(path,"w:gz") as archive:
        parent=tarfile.TarInfo("scientific_reasoning_auditor-0.5.2")
        parent.type=tarfile.DIRTYPE
        parent.mode=0o755
        parent.mtime=timestamp
        archive.addfile(parent)
        member=tarfile.TarInfo(name)
        member.size=len(data)
        member.mode=0o644
        member.mtime=timestamp
        archive.addfile(member,io.BytesIO(data))


class ReproducibleSdists(unittest.TestCase):
    def test_normalization_makes_equivalent_archives_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/"a.tar.gz";b=Path(tmp)/"b.tar.gz"
            make_archive(a,123);make_archive(b,987)
            self.assertNotEqual(a.read_bytes(),b.read_bytes())
            normalize_sdist_file(a,1793820558)
            normalize_sdist_file(b,1793820558)
            self.assertEqual(a.read_bytes(),b.read_bytes())
            with tarfile.open(a) as arc:
                member=arc.getmember("scientific_reasoning_auditor-0.5.2/file.txt")
                self.assertEqual(member.mtime,1793820558)
                self.assertEqual(member.uid,0)
                self.assertEqual(arc.extractfile(member).read(),b"evidence")

    def test_normalization_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"one.tar.gz";make_archive(path,456)
            normalize_sdist_file(path,1793820558)
            first=path.read_bytes()
            normalize_sdist_file(path,1793820558)
            self.assertEqual(path.read_bytes(),first)

    def test_sdist_rejects_unsafe_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"unsafe.tar.gz"
            make_archive(path,20,name="../outside")
            with self.assertRaises(ValueError):
                normalize_sdist_file(path,1793820558)

    def test_sdist_rejects_invalid_epoch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"one.tar.gz";make_archive(path,20)
            for epoch in (-1,True,"zero",2**42):
                with self.subTest(epoch=epoch),self.assertRaises(ValueError):
                    normalize_sdist_file(path,epoch)

    def test_distribution_comparator_detects_different_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/"a";b=Path(tmp)/"b";a.mkdir();b.mkdir()
            for d in (a,b):
                (d/"pkg.tar.gz").write_bytes(b"same")
                (d/"pkg.whl").write_bytes(b"same")
            result=verify_identical_distributions(a,b)
            self.assertEqual(result["package_count"],2)
            (b/"pkg.whl").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify_identical_distributions(a,b)
            (b/"pkg.whl").unlink()
            with self.assertRaises(ValueError):
                verify_identical_distributions(a,b)


if __name__=="__main__":
    unittest.main()
