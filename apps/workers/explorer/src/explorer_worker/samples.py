"""Realistic sample files Explorer attaches when a screen asks for an upload,
so it never has to stop and ask a person for a file. One per kind:

- image: a small photo of a damaged car (samples/claim-photo.jpg)
- png:   the same idea as a PNG, for apps that only take PNG
- pdf:   a one-page document
- text / csv: plain files, mainly to check a wrong type is rejected
"""

import struct
import tempfile
import zlib
from pathlib import Path

_HERE = Path(__file__).parent / "samples"
_MADE = Path(tempfile.gettempdir()) / "explorer-samples"

KINDS = ("image", "png", "pdf", "text", "csv")

_PDF = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 88>>stream
BT /F1 18 Tf 72 720 Td (Repair estimate) Tj 0 -28 Td /F1 12 Tf (Front bumper and door panel.) Tj ET
endstream endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
trailer<</Root 1 0 R>>
%%EOF
"""


def _png(width: int = 240, height: int = 160) -> bytes:
    """A plain two-tone PNG, built with the standard library only."""
    sky, road = b"\xc4\xd4\xde", b"\x5c\x62\x68"
    rows = b"".join(b"\x00" + (sky if y < height * 0.6 else road) * width for y in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(kind + data))
        return struct.pack(">I", len(data)) + kind + data + crc

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    body = chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + body


def sample_file(kind: str) -> Path:
    """Path to a ready sample of this kind (unknown kinds get the photo)."""
    kind = kind.lower().strip()
    if kind not in KINDS or kind == "image":
        return _HERE / "claim-photo.jpg"
    _MADE.mkdir(parents=True, exist_ok=True)
    name, data = {
        "png": ("damage-photo.png", _png),
        "pdf": ("repair-estimate.pdf", lambda: _PDF),
        "text": ("notes.txt", lambda: b"Notes about the incident.\n"),
        "csv": ("items.csv", lambda: b"item,cost\nbumper,450\ndoor panel,620\n"),
    }[kind]
    path = _MADE / name
    if not path.exists():
        path.write_bytes(data())
    return path
