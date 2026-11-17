"""Avoid full-cap allocations without weakening actual-byte input bounds."""
import hashlib
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sra.document import load_document


class ReadBudgetStream(BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.requests = []

    def read(self, size=-1):
        self.requests.append(size)
        if not 0 < size <= 64 * 1024:
            raise MemoryError('Simulated allocation limit for a single read.')
        return super().read(size)


class BoundedDocumentReadTests(unittest.TestCase):
    def test_chunked_snapshot_keeps_complete_bytes_hash_and_text(self):
        data = b'# Methods\n' + b'Calibration measurement.\n' * 4000
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'paper.md'
            path.write_bytes(data)
            stream = ReadBudgetStream(data)
            with patch.object(Path, 'open', return_value=stream):
                result = load_document(path)
            self.assertGreater(len(stream.requests), 2)
            self.assertLessEqual(max(stream.requests), 64 * 1024)
            self.assertEqual(result.sha256, hashlib.sha256(data).hexdigest())
            self.assertEqual(result.source_size_bytes, len(data))
            self.assertEqual(result.text, data.decode())
            self.assertEqual(path.read_bytes(), data)

    def test_growing_stream_is_bounded_by_actual_bytes_not_small_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'paper.md'
            path.write_bytes(b'x')
            stream = ReadBudgetStream(b'x' * 1000)
            with patch('sra.document.MAX_DOCUMENT_BYTES', 128), patch.object(Path, 'open', return_value=stream):
                with self.assertRaisesRegex(ValueError, 'input limit'):
                    load_document(path)
            self.assertEqual(stream.requests, [129])
            self.assertEqual(path.read_bytes(), b'x')
