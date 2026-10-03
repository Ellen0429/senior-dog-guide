import io
import struct
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.import_article_image_pack import (
    ImagePackError,
    import_image_pack,
    validate_and_load_pack,
)


def make_webp(width: int, height: int, padding: int = 100) -> bytes:
    """A minimal, structurally valid VP8L WebP file with the given
    dimensions encoded in its header -- enough for _webp_dimensions()
    to decode, without needing a real image codec or Pillow."""
    bits = (((height - 1) & 0x3FFF) << 14) | ((width - 1) & 0x3FFF)
    chunk_data = bytes([0x2F]) + struct.pack("<I", bits) + b"\x00" * padding
    if len(chunk_data) % 2 == 1:
        chunk_data += b"\x00"
    chunk = b"VP8L" + struct.pack("<I", len(chunk_data)) + chunk_data
    riff_size = 4 + len(chunk)
    return b"RIFF" + struct.pack("<I", riff_size) + b"WEBP" + chunk


def make_pack_zip(
    dest: Path, *, hero=(1600, 900), points=((900, 900),) * 4, filenames=None, extra=None,
) -> None:
    filenames = filenames or {
        "hero": "hero.webp",
        "point-1": "point-1-usage.webp",
        "point-2": "point-2-ingredient.webp",
        "point-3": "point-3-material.webp",
        "point-4": "point-4-care.webp",
    }
    with zipfile.ZipFile(dest, "w") as zf:
        zf.writestr(filenames["hero"], make_webp(*hero))
        for i, size in enumerate(points, start=1):
            zf.writestr(filenames[f"point-{i}"], make_webp(*size))
        for name, data in (extra or {}).items():
            zf.writestr(name, data)


class TestImportArticleImagePack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.packs_dir = self.root / "image-packs"
        self.images_dir = self.root / "images"
        self.packs_dir.mkdir()

    def _import(self, slug="joint-care", **kwargs):
        return import_image_pack(
            slug, image_packs_dir=self.packs_dir, images_dir=self.images_dir, **kwargs,
        )

    def test_valid_pack_imports_all_five_images(self):
        make_pack_zip(self.packs_dir / "joint-care-images.zip")
        written = self._import()
        self.assertEqual(len(written), 5)
        for path in written.values():
            self.assertTrue(path.is_file())
        self.assertEqual(written["hero"].name, "hero.webp")
        self.assertEqual(written["point-1"].name, "point-1-usage.webp")

    def test_missing_pack_file_is_refused(self):
        with self.assertRaises(ImagePackError):
            self._import(slug="nonexistent-slug")

    def test_missing_one_required_image_is_refused(self):
        with zipfile.ZipFile(self.packs_dir / "joint-care-images.zip", "w") as zf:
            zf.writestr("hero.webp", make_webp(1600, 900))
            zf.writestr("point-1-usage.webp", make_webp(900, 900))
            zf.writestr("point-2-ingredient.webp", make_webp(900, 900))
            zf.writestr("point-3-material.webp", make_webp(900, 900))
            # point-4 missing
        with self.assertRaises(ImagePackError) as ctx:
            self._import()
        self.assertIn("point-4", str(ctx.exception))

    def test_ambiguous_duplicate_match_is_refused(self):
        with zipfile.ZipFile(self.packs_dir / "joint-care-images.zip", "w") as zf:
            zf.writestr("hero.webp", make_webp(1600, 900))
            zf.writestr("point-1-usage.webp", make_webp(900, 900))
            zf.writestr("point-1-alt.webp", make_webp(900, 900))
            zf.writestr("point-2-ingredient.webp", make_webp(900, 900))
            zf.writestr("point-3-material.webp", make_webp(900, 900))
            zf.writestr("point-4-care.webp", make_webp(900, 900))
        with self.assertRaises(ImagePackError) as ctx:
            self._import()
        self.assertIn("ambiguous", str(ctx.exception))

    def test_non_webp_file_is_rejected_as_corrupt(self):
        make_pack_zip(
            self.packs_dir / "joint-care-images.zip",
            extra={},
        )
        # overwrite hero with garbage after building a normally-valid zip
        with zipfile.ZipFile(self.packs_dir / "joint-care-images.zip", "w") as zf:
            zf.writestr("hero.webp", b"not a real webp file" + b"\x00" * 100)
            zf.writestr("point-1-usage.webp", make_webp(900, 900))
            zf.writestr("point-2-ingredient.webp", make_webp(900, 900))
            zf.writestr("point-3-material.webp", make_webp(900, 900))
            zf.writestr("point-4-care.webp", make_webp(900, 900))
        with self.assertRaises(ImagePackError) as ctx:
            self._import()
        self.assertIn("RIFF", str(ctx.exception))

    def test_hero_must_be_landscape(self):
        make_pack_zip(self.packs_dir / "joint-care-images.zip", hero=(900, 1600))
        with self.assertRaises(ImagePackError) as ctx:
            self._import()
        self.assertIn("landscape", str(ctx.exception))

    def test_hero_below_minimum_width_is_rejected(self):
        make_pack_zip(self.packs_dir / "joint-care-images.zip", hero=(800, 500))
        with self.assertRaises(ImagePackError) as ctx:
            self._import()
        self.assertIn("too low", str(ctx.exception))

    def test_point_image_must_be_square(self):
        make_pack_zip(
            self.packs_dir / "joint-care-images.zip",
            points=((900, 900), (900, 700), (900, 900), (900, 900)),
        )
        with self.assertRaises(ImagePackError) as ctx:
            self._import()
        self.assertIn("square", str(ctx.exception))

    def test_point_image_below_minimum_size_is_rejected(self):
        make_pack_zip(
            self.packs_dir / "joint-care-images.zip",
            points=((300, 300), (900, 900), (900, 900), (900, 900)),
        )
        with self.assertRaises(ImagePackError) as ctx:
            self._import()
        self.assertIn("too low", str(ctx.exception))

    def test_path_traversal_entry_is_rejected(self):
        with zipfile.ZipFile(self.packs_dir / "joint-care-images.zip", "w") as zf:
            zf.writestr("../../etc/evil.webp", make_webp(900, 900))
            zf.writestr("hero.webp", make_webp(1600, 900))
            zf.writestr("point-1-usage.webp", make_webp(900, 900))
            zf.writestr("point-2-ingredient.webp", make_webp(900, 900))
            zf.writestr("point-3-material.webp", make_webp(900, 900))
            zf.writestr("point-4-care.webp", make_webp(900, 900))
        with self.assertRaises(ImagePackError) as ctx:
            self._import()
        self.assertIn("unsafe", str(ctx.exception))

    def test_subdirectory_entry_is_rejected(self):
        with zipfile.ZipFile(self.packs_dir / "joint-care-images.zip", "w") as zf:
            zf.writestr("sub/hero.webp", make_webp(1600, 900))
            zf.writestr("point-1-usage.webp", make_webp(900, 900))
            zf.writestr("point-2-ingredient.webp", make_webp(900, 900))
            zf.writestr("point-3-material.webp", make_webp(900, 900))
            zf.writestr("point-4-care.webp", make_webp(900, 900))
        with self.assertRaises(ImagePackError):
            self._import()

    def test_symlink_entry_is_rejected(self):
        zip_path = self.packs_dir / "joint-care-images.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("hero.webp", make_webp(1600, 900))
            zf.writestr("point-1-usage.webp", make_webp(900, 900))
            zf.writestr("point-2-ingredient.webp", make_webp(900, 900))
            zf.writestr("point-3-material.webp", make_webp(900, 900))
            info = zipfile.ZipInfo("point-4-care.webp")
            info.external_attr = (0o120777 << 16)  # symlink mode bits
            zf.writestr(info, "/etc/passwd")
        with self.assertRaises(ImagePackError) as ctx:
            self._import()
        self.assertIn("symlink", str(ctx.exception))

    def test_bad_zip_file_is_refused(self):
        (self.packs_dir / "joint-care-images.zip").write_bytes(b"not a zip at all")
        with self.assertRaises(ImagePackError):
            self._import()

    def test_does_not_overwrite_existing_file_without_flag(self):
        make_pack_zip(self.packs_dir / "joint-care-images.zip")
        self._import()
        # A second import attempt, without --overwrite, must refuse and
        # must not touch the already-written files.
        existing_bytes = (self.images_dir / "joint-care" / "hero.webp").read_bytes()
        with self.assertRaises(ImagePackError):
            self._import()
        self.assertEqual(existing_bytes, (self.images_dir / "joint-care" / "hero.webp").read_bytes())

    def test_overwrite_flag_allows_replacing_existing_files(self):
        make_pack_zip(self.packs_dir / "joint-care-images.zip", hero=(1600, 900))
        self._import()
        make_pack_zip(self.packs_dir / "joint-care-images.zip", hero=(1800, 1000))
        written = self._import(overwrite=True)
        self.assertTrue(written["hero"].is_file())

    def test_validation_failure_writes_nothing_to_disk(self):
        make_pack_zip(self.packs_dir / "joint-care-images.zip", hero=(900, 1600))  # portrait: invalid
        with self.assertRaises(ImagePackError):
            self._import()
        self.assertFalse((self.images_dir / "joint-care").exists())

    def test_validate_and_load_pack_returns_canonical_keys(self):
        make_pack_zip(self.packs_dir / "joint-care-images.zip")
        loaded = validate_and_load_pack(self.packs_dir / "joint-care-images.zip")
        for key in ("hero", "point-1", "point-2", "point-3", "point-4"):
            self.assertIn(key, loaded)
            self.assertIsInstance(loaded[key], bytes)


if __name__ == "__main__":
    unittest.main()
