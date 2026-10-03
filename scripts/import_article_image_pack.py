"""Imports one article's 5-image pack from a single ZIP instead of 5
separate file drops -- the standard path for article image delivery
from here on (see the project's article-production-run / enqueue_article
standard pipeline for the analogous DB-side "one input, one file" design;
this is the same idea applied to images).

Usage:
    python3 scripts/import_article_image_pack.py <slug>
    python3 scripts/import_article_image_pack.py <slug> --overwrite
    python3 scripts/import_article_image_pack.py <slug> --delete-zip-on-success

Input: assets/image-packs/<slug>-images.zip, containing exactly 5 flat
(no subdirectories) WebP files:
    hero.webp            -- landscape
    point-1-*.webp       -- square
    point-2-*.webp       -- square
    point-3-*.webp       -- square
    point-4-*.webp       -- square

Only the standard library (zipfile) is used to read the ZIP; WebP
dimensions are decoded from the raw RIFF/VP8/VP8L/VP8X header bytes
(see _webp_dimensions()) rather than depending on Pillow or any other
new package -- there is no external service or paid API involved, and
no new dependency for the rest of the project to carry.

Safety: every ZIP member is checked BEFORE anything is extracted --
directory traversal (`..`, absolute paths), symlinks, and subdirectory
entries are all rejected outright (ValueError), and nothing is written
to disk until every one of the 5 required images has independently
passed its own format/dimension checks. Existing files under
assets/images/<slug>/ are never silently overwritten (pass --overwrite
to allow it, which still only touches the 5 files this pack provides).
"""

from __future__ import annotations

import argparse
import fnmatch
import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE_PACKS_DIR = ROOT / "assets" / "image-packs"
IMAGES_DIR = ROOT / "assets" / "images"

REQUIRED_PATTERNS = (
    ("hero", "hero.webp"),
    ("point-1", "point-1-*.webp"),
    ("point-2", "point-2-*.webp"),
    ("point-3", "point-3-*.webp"),
    ("point-4", "point-4-*.webp"),
)

# "around 1600px" / "900-1000px" per the project's quality bar -- these
# are floors, not exact targets, so a pack slightly above or below the
# nominal number still passes; only a clearly too-small (speed-optimized
# / corrupt-looking) image is rejected.
MIN_HERO_WIDTH = 1200
MIN_POINT_SIZE = 800


class ImagePackError(ValueError):
    """The pack is missing a required image, fails a quality/format
    check, or is unsafe to extract. Raised before any file is written."""


def _webp_dimensions(data: bytes) -> tuple[int, int]:
    """Decode (width, height) from raw WebP file bytes, supporting the
    three sub-formats (VP8 lossy, VP8L lossless, VP8X extended).
    Raises ImagePackError for anything that isn't a well-formed WebP --
    this is what catches a corrupt or truncated file."""
    if len(data) < 30 or data[0:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ImagePackError("not a valid WebP file (missing RIFF/WEBP header)")
    fourcc = data[12:16]
    payload = data[20:]
    if fourcc == b"VP8X":
        if len(payload) < 10:
            raise ImagePackError("truncated VP8X header")
        width = (payload[4] | (payload[5] << 8) | (payload[6] << 16)) + 1
        height = (payload[7] | (payload[8] << 8) | (payload[9] << 16)) + 1
        return width, height
    if fourcc == b"VP8L":
        if len(payload) < 5 or payload[0] != 0x2F:
            raise ImagePackError("invalid VP8L signature")
        bits = struct.unpack("<I", payload[1:5])[0]
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    if fourcc == b"VP8 ":
        if len(payload) < 10 or payload[3:6] != b"\x9d\x01\x2a":
            raise ImagePackError("invalid VP8 sync code")
        width = struct.unpack("<H", payload[6:8])[0] & 0x3FFF
        height = struct.unpack("<H", payload[8:10])[0] & 0x3FFF
        return width, height
    raise ImagePackError(f"unrecognized WebP chunk type {fourcc!r}")


def _safe_member_path(name: str) -> str:
    """Returns the plain filename if `name` is a safe, flat ZIP entry
    (no directory, no traversal, no absolute path); raises
    ImagePackError otherwise. Used before ANY extraction."""
    if name != name.strip() or not name:
        raise ImagePackError(f"unsafe zip entry name: {name!r}")
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or ":" in normalized:
        raise ImagePackError(f"unsafe zip entry (absolute path): {name!r}")
    parts = normalized.split("/")
    if len(parts) != 1 or parts[0] in ("", ".", ".."):
        raise ImagePackError(f"unsafe zip entry (not a flat file): {name!r}")
    if ".." in normalized:
        raise ImagePackError(f"unsafe zip entry (traversal): {name!r}")
    return parts[0]


def _reject_symlinks(zf: zipfile.ZipFile) -> None:
    for info in zf.infolist():
        # Unix symlink mode bits (S_IFLNK) stored in the high 16 bits of
        # external_attr -- a symlink member could otherwise point
        # extraction at an arbitrary path outside the target directory.
        mode = info.external_attr >> 16
        if (mode & 0o170000) == 0o120000:
            raise ImagePackError(f"zip entry is a symlink, refusing: {info.filename!r}")


def validate_and_load_pack(zip_path: Path) -> dict[str, bytes]:
    """Opens `zip_path`, checks it is safe, and returns {canonical_key:
    file_bytes} for all 5 required images (canonical_key is one of
    "hero", "point-1".."point-4") -- or raises ImagePackError describing
    exactly what's wrong, before anything is extracted to disk."""
    if not zip_path.is_file():
        raise ImagePackError(f"image pack not found: {zip_path}")

    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise ImagePackError(f"not a valid zip file: {exc}") from None

    with zf:
        _reject_symlinks(zf)
        safe_names = {_safe_member_path(info.filename): info for info in zf.infolist()}

        matched: dict[str, str] = {}
        for key, pattern in REQUIRED_PATTERNS:
            candidates = [n for n in safe_names if fnmatch.fnmatch(n, pattern)]
            if not candidates:
                raise ImagePackError(f"missing required image matching {pattern!r}")
            if len(candidates) > 1:
                raise ImagePackError(
                    f"ambiguous: {len(candidates)} files match {pattern!r}: {sorted(candidates)}"
                )
            matched[key] = candidates[0]

        loaded: dict[str, bytes] = {}
        for key, member_name in matched.items():
            data = zf.read(member_name)
            if len(data) < 100:
                raise ImagePackError(f"{member_name!r} is too small to be a real image")
            width, height = _webp_dimensions(data)
            if key == "hero":
                if width <= height:
                    raise ImagePackError(
                        f"hero image must be landscape, got {width}x{height}"
                    )
                if width < MIN_HERO_WIDTH:
                    raise ImagePackError(
                        f"hero image resolution too low: {width}x{height} "
                        f"(minimum width {MIN_HERO_WIDTH}px)"
                    )
            else:
                if width != height:
                    raise ImagePackError(
                        f"{key} image must be square, got {width}x{height}"
                    )
                if width < MIN_POINT_SIZE:
                    raise ImagePackError(
                        f"{key} image resolution too low: {width}x{height} "
                        f"(minimum {MIN_POINT_SIZE}px)"
                    )
            loaded[key] = data
            loaded[f"{key}__filename"] = member_name  # type: ignore[assignment]

    return loaded


def import_image_pack(
    slug: str, *, image_packs_dir: Path = IMAGE_PACKS_DIR, images_dir: Path = IMAGES_DIR,
    overwrite: bool = False,
) -> dict[str, Path]:
    """Validates assets/image-packs/<slug>-images.zip and extracts its 5
    images into assets/images/<slug>/, preserving each image's own
    filename from inside the zip (e.g. point-1-usage.webp). Refuses to
    overwrite any pre-existing file there unless overwrite=True. Returns
    {canonical_key: written_path} for the 5 images. Nothing is written
    if validation fails."""
    zip_path = image_packs_dir / f"{slug}-images.zip"
    loaded = validate_and_load_pack(zip_path)

    target_dir = images_dir / slug
    filenames = {k: v for k, v in loaded.items() if k.endswith("__filename")}
    if not overwrite:
        for key, _pattern in REQUIRED_PATTERNS:
            filename = loaded[f"{key}__filename"]
            existing = target_dir / filename
            if existing.exists():
                raise ImagePackError(
                    f"{existing} already exists -- pass overwrite=True to replace it"
                )

    target_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for key, _pattern in REQUIRED_PATTERNS:
        filename = loaded[f"{key}__filename"]
        dest = target_dir / filename
        dest.write_bytes(loaded[key])
        written[key] = dest
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("slug")
    parser.add_argument(
        "--overwrite", action="store_true",
        help="allow replacing pre-existing files under assets/images/<slug>/",
    )
    parser.add_argument(
        "--delete-zip-on-success", action="store_true",
        help="remove assets/image-packs/<slug>-images.zip after a successful import",
    )
    args = parser.parse_args(argv)

    zip_path = IMAGE_PACKS_DIR / f"{args.slug}-images.zip"
    try:
        written = import_image_pack(args.slug, overwrite=args.overwrite)
    except ImagePackError as exc:
        print(f"[import-image-pack] refused: {exc}", file=sys.stderr)
        return 1

    for key, path in written.items():
        print(f"[import-image-pack] wrote {key}: {path.relative_to(ROOT)}")

    if args.delete_zip_on_success:
        zip_path.unlink(missing_ok=True)
        print(f"[import-image-pack] deleted {zip_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
