"""Fetch frozen official SciFact evaluation inputs; never extract arbitrary paths."""
import argparse
import hashlib
import io
from pathlib import Path
import tarfile
from urllib.request import urlopen

URL='https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz'
ARCHIVE_SHA256='11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be'
FILES={'corpus.jsonl':'b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62',
       'claims_dev.jsonl':'86f0435d08fdb65d1aa41d1472684f57e6e71930626497bdf4d7a9ec1a632217'}


def fetch(destination):
    root=Path(destination)
    if all((root/name).is_file() and hashlib.sha256((root/name).read_bytes()).hexdigest()==sha for name,sha in FILES.items()):
        print('Frozen SciFact inputs already verified.')
        return
    with urlopen(URL,timeout=30) as response:
        raw=response.read(64000001)
    if len(raw)>64000000 or hashlib.sha256(raw).hexdigest()!=ARCHIVE_SHA256:
        raise ValueError('Official archive changed or exceeded its bound; review provenance before updating pins.')
    outputs={}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for name,sha in FILES.items():
            member=archive.getmember('data/'+name)
            if not member.isfile() or member.size>40000000:
                raise ValueError('Unexpected archive member.')
            data=archive.extractfile(member).read(40000001)
            if hashlib.sha256(data).hexdigest()!=sha:
                raise ValueError('Frozen file hash mismatch.')
            target=root/name
            if target.exists() and target.read_bytes()!=data:
                raise ValueError('Refusing to overwrite a different benchmark input.')
            outputs[target]=data
    root.mkdir(parents=True,exist_ok=True)
    for target,data in outputs.items():
        target.write_bytes(data)
    print('Verified official SciFact development split and corpus; see docs/INSPECTION_EXPANSION.md for attribution.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir',required=True)
    fetch(parser.parse_args().out_dir)
