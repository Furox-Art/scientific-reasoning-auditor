"""Assert two SOURCE_DATE_EPOCH builds have byte-identical distributions."""
import argparse
import hashlib
from pathlib import Path


def verify_identical_distributions(left: Path | str, right: Path | str) -> dict:
    a,b=Path(left),Path(right)
    if not a.is_dir() or not b.is_dir():
        raise ValueError("Both distribution directories must exist.")
    files_a={p.name:p for p in a.iterdir() if p.is_file() and p.name.endswith((".whl",".tar.gz"))}
    files_b={p.name:p for p in b.iterdir() if p.is_file() and p.name.endswith((".whl",".tar.gz"))}
    if files_a.keys()!=files_b.keys() or len(files_a)!=2:
        raise ValueError("Distribution inventories differ or do not contain exactly wheel and sdist.")
    hashes={}
    for name in sorted(files_a):
        first=hashlib.sha256(files_a[name].read_bytes()).hexdigest()
        second=hashlib.sha256(files_b[name].read_bytes()).hexdigest()
        if first != second:
            raise ValueError(f"Byte-reproducibility mismatch for {name}.")
        hashes[name]=first
    return {"package_count":len(hashes),"sha256":hashes,"byte_identical":True}


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("first_dir")
    parser.add_argument("second_dir")
    args=parser.parse_args()
    output=verify_identical_distributions(args.first_dir,args.second_dir)
    for name,digest in output["sha256"].items():
        print(f"REPRODUCIBLE {name} sha256={digest}")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
