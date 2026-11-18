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


# An upload test may ask for several files (a "no more than N" limit) or a
# big one (a size limit): at most this many, and this many MB each.
MAX_FILES = 10
MAX_SIZE_MB = 50


def upload_shape(upload: dict) -> tuple[int, float | None]:
    """(how many files, size in MB or None) asked for by an upload step,
    within MAX_FILES / MAX_SIZE_MB."""
    try:
        count = int(upload.get("count") or 1)
    except TypeError, ValueError:
        count = 1
    try:
        size = float(upload.get("size_mb") or 0)
    except TypeError, ValueError:
        size = 0.0
    return max(1, min(count, MAX_FILES)), (min(size, MAX_SIZE_MB) if size > 0 else None)


def padding(path: Path, size_mb: float | None) -> int:
    """Bytes to add after `path`'s own content to make it `size_mb` big."""
    return max(0, int(size_mb * 1024 * 1024) - path.stat().st_size) if size_mb else 0


def file_names(path: Path, count: int, size_mb: float | None) -> list[str]:
    """Distinct names for `count` copies (apps often refuse a repeated name)."""
    stem = path.stem + (f"-{size_mb:g}mb" if size_mb else "")
    if count == 1:
        return [stem + path.suffix]
    return [f"{stem}-{i}{path.suffix}" for i in range(1, count + 1)]


def sample_files(kind: str, count: int = 1, size_mb: float | None = None) -> list[Path]:
    """`count` sample files of this kind, each `size_mb` big when given (the
    sample, padded at the end: still opens as that kind of file)."""
    base = sample_file(kind)
    if count == 1 and not size_mb:
        return [base]
    pad = padding(base, size_mb)
    out = []
    for name in file_names(base, count, size_mb):
        path = _MADE / name
        if not path.exists() or path.stat().st_size != base.stat().st_size + pad:
            _MADE.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base.read_bytes() + b"\0" * pad)
        out.append(path)
    return out
