"""Normalize trusted, locally built source distributions for byte-reproducibility.

Reads TAR entries without extracting them. Canonicalizes metadata and gzip
header; does not alter payload bytes. SOURCE_DATE_EPOCH must be explicit.
"""
import argparse
import copy
import gzip
import os
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


def normalize_sdist_file(path: str | Path, epoch: int) -> None:
    if isinstance(epoch, bool) or not isinstance(epoch, int) or not (0 <= epoch <= 2**31-1):
        raise ValueError("SOURCE_DATE_EPOCH must be an integer in [0, 2**31-1].")
    source=Path(path)
    if not source.name.endswith(".tar.gz"):
        raise ValueError("Only .tar.gz source distributions are supported.")
    if not source.is_file():
        raise ValueError("Source distribution does not exist.")
    temp_path=None
    try:
        with tarfile.open(source,"r:gz") as original:
            with tempfile.NamedTemporaryFile(dir=source.parent,
                                             prefix=".normalized-sdist-",
                                             suffix=".tmp",delete=False) as output:
                temp_path=Path(output.name)
                with gzip.GzipFile(fileobj=output,mode="wb",filename="",mtime=0,compresslevel=9) as compressed:
                    with tarfile.open(fileobj=compressed,mode="w",format=tarfile.PAX_FORMAT) as normalized:
                        for member in original:
                            rel=PurePosixPath(member.name)
                            if (rel.is_absolute() or not rel.parts
                                or ".." in rel.parts or "\\" in member.name
                                or not (member.isfile() or member.isdir())):
                                raise ValueError("Unsafe or unsupported source distribution member.")
                            info=copy.copy(member)
                            info.mtime=epoch
                            info.uid=0
                            info.gid=0
                            info.uname=""
                            info.gname=""
                            info.pax_headers={}
                            if member.isfile():
                                data=original.extractfile(member)
                                if data is None:
                                    raise ValueError("Archive file data not available.")
                                with data:
                                    normalized.addfile(info,data)
                            else:
                                normalized.addfile(info)
        # Ensure the entire normalized TAR can be read before replacing source.
        with tarfile.open(temp_path,"r:gz") as archive:
            for member in archive:
                if member.isfile():
                    data=archive.extractfile(member)
                    if data is None:
                        raise ValueError("Normalized data unavailable.")
                    with data:
                        while data.read(1024*1024):
                            pass
        os.chmod(temp_path,source.stat().st_mode & 0o777)
        os.replace(temp_path,source)
        temp_path=None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("sdist",nargs="+",help="Source distribution .tar.gz artifacts")
    args=parser.parse_args()
    value=os.environ.get("SOURCE_DATE_EPOCH")
    if value is None:
        parser.error("SOURCE_DATE_EPOCH environment variable is mandatory.")
    try:
        epoch=int(value)
        for filename in args.sdist:
            normalize_sdist_file(filename,epoch)
    except (OSError,tarfile.TarError,ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
