"""Publisher tests that do not download releases."""

from __future__ import annotations

import hashlib
import io
import sys
import tarfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import publisher


def _names(*pairs: tuple[str, str]) -> list[str]:
    assets: list[str] = []
    for archive, extra in pairs:
        assets.append(archive)
        if extra:
            assets.append(extra)
    return assets


def _modern(with_checksums: bool = True) -> list[str]:
    suffix = ".sha256" if with_checksums else ""
    names = []
    for archive in publisher.MODERN_ARCHIVES.values():
        names.append(archive)
        if suffix:
            names.append(archive + suffix)
    return names


def _legacy(tag: str, with_checksums: bool = True) -> list[str]:
    names = []
    for arch in publisher.ARCHES:
        archive = publisher.legacy_archive_name(tag, arch)
        names.append(archive)
        if with_checksums:
            names.append(archive + ".sha256")
    return names


class ResolveArchivesTest(unittest.TestCase):
    def test_modern_names(self) -> None:
        resolved = publisher.resolve_archives("v2.11.2", _modern())
        self.assertEqual(resolved["amd64"][0], "codync-host-linux-x86_64.tar.gz")
        self.assertEqual(resolved["arm64"][0], "codync-host-linux-arm64.tar.gz")
        self.assertTrue(resolved["amd64"][1].endswith(".sha256"))
        self.assertTrue(resolved["arm64"][1].endswith(".sha256"))

    def test_legacy_v210_names(self) -> None:
        resolved = publisher.resolve_archives("v2.1.0", _legacy("v2.1.0"))
        self.assertEqual(
            resolved["amd64"][0],
            "codync-host-2.1.0-x86_64-unknown-linux-gnu.tar.gz",
        )
        self.assertEqual(
            resolved["arm64"][0],
            "codync-host-2.1.0-aarch64-unknown-linux-gnu.tar.gz",
        )
        self.assertTrue(resolved["amd64"][1].endswith(".sha256"))

    def test_requires_both_arches_and_checksums(self) -> None:
        incomplete = [
            "codync-host-linux-x86_64.tar.gz",
            "codync-host-linux-x86_64.tar.gz.sha256",
            "codync-host-linux-arm64.tar.gz",
        ]
        with self.assertRaises(publisher.IneligibleRelease):
            publisher.resolve_archives("v2.2.0", incomplete)

    def test_prefers_modern_when_both_schemes_are_complete(self) -> None:
        assets = _modern() + _legacy("v2.11.2")
        resolved = publisher.resolve_archives("v2.11.2", assets)
        self.assertEqual(resolved["amd64"][0], "codync-host-linux-x86_64.tar.gz")

    def test_falls_through_to_legacy_when_modern_checksum_is_missing(self) -> None:
        assets = _modern(with_checksums=False) + _legacy("v2.1.0")
        resolved = publisher.resolve_archives("v2.1.0", assets)
        self.assertIn("unknown-linux-gnu", resolved["arm64"][0])

    def test_ignores_desktop_app_archives(self) -> None:
        desktop = [
            "codync-linux-x86_64.tar.gz",
            "codync-linux-x86_64.tar.gz.sha256",
            "codync-linux-arm64.tar.gz",
            "codync-linux-arm64.tar.gz.sha256",
            "Codync-x86_64.AppImage",
            "codync_2.11.2_amd64.deb",
        ]
        with self.assertRaises(publisher.IneligibleRelease):
            publisher.resolve_archives("v2.11.2", desktop)

    def test_skips_v1_tags(self) -> None:
        for tag in ("v1.0.0", "v1.0.5", "v2.0.9"):
            with self.assertRaises(publisher.IneligibleRelease):
                publisher.resolve_archives(tag, _modern())


class ChecksumTest(unittest.TestCase):
    def test_first_whitespace_field(self) -> None:
        digest = "ab" * 32
        text = f"{digest}  codync-host-linux-x86_64.tar.gz\n"
        self.assertEqual(publisher.parse_sha256(text), digest)

    def test_ignores_filename_and_later_lines(self) -> None:
        first = "cd" * 32
        later = "ef" * 32
        text = f"{first} *some-name.tar.gz\n{later}  other\n"
        self.assertEqual(publisher.parse_sha256(text), first)

    def test_rejects_non_hex_first_field(self) -> None:
        text = "SHA256 (codync-host-linux-x86_64.tar.gz) = " + ("a" * 64) + "\n"
        with self.assertRaises(publisher.ChecksumError):
            publisher.parse_sha256(text)

    def test_verify_matches_bytes(self) -> None:
        payload = b"codync-host-bytes"
        digest = hashlib.sha256(payload).hexdigest()
        text = f"{digest}  ignored-name\n"
        self.assertEqual(publisher.verify_sha256(payload, text), digest)

    def test_verify_rejects_mismatch(self) -> None:
        with self.assertRaises(publisher.ChecksumError):
            publisher.verify_sha256(b"nope", "aa" * 32 + "  file\n")


class ExtractTest(unittest.TestCase):
    def test_finds_binaries_by_filename(self) -> None:
        blob = io.BytesIO()
        with tarfile.open(fileobj=blob, mode="w:gz") as tar:
            self._add(tar, "codync-host-linux-x86_64/codync-host", b"host-bin")
            self._add(tar, "codync-host-linux-x86_64/codync-screen", b"screen-bin")
            self._add(tar, "nested/dir/cua-driver", b"driver-bin")
            self._add(tar, "codync-host-linux-x86_64/LICENSE", b"MIT\n")
            self._add(tar, "notes/codync-host.txt", b"not-the-binary")
            self._add(tar, "codync-host-linux-x86_64/codync-host.bak", b"backup")
        with self._tempdir() as raw:
            dest = Path(raw)
            written = publisher.extract_host_files(blob.getvalue(), dest)
            self.assertEqual((dest / "codync-host").read_bytes(), b"host-bin")
            self.assertEqual((dest / "codync-screen").read_bytes(), b"screen-bin")
            self.assertEqual((dest / "cua-driver").read_bytes(), b"driver-bin")
            self.assertEqual((dest / "LICENSE").read_bytes(), b"MIT\n")
            self.assertEqual(set(written), {"codync-host", "codync-screen", "cua-driver", "LICENSE"})
            self.assertTrue((dest / "codync-host").stat().st_mode & 0o111)

    def test_missing_host_binary_fails(self) -> None:
        blob = io.BytesIO()
        with tarfile.open(fileobj=blob, mode="w:gz") as tar:
            self._add(tar, "pkg/LICENSE", b"license")
        with self._tempdir() as raw:
            with self.assertRaises(publisher.PublishError):
                publisher.extract_host_files(blob.getvalue(), Path(raw))

    def _add(self, tar: tarfile.TarFile, name: str, payload: bytes) -> None:
        info = tarfile.TarInfo(name)
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))

    def _tempdir(self):
        import tempfile

        return tempfile.TemporaryDirectory()


class ReleaseSelectionTest(unittest.TestCase):
    def test_filters_assets_without_downloading(self) -> None:
        releases = [
            self._release("v1.0.5", _modern()),
            self._release("v2.1.0", _legacy("v2.1.0")),
            self._release("v2.2.0", _modern(with_checksums=False)),
            self._release("v2.9.0", _modern(), prerelease=True),
            self._release("v2.11.2", _modern() + ["codync-linux-x86_64.tar.gz", "Codync.AppImage"]),
        ]
        self.assertEqual(
            publisher.eligible_tags_from_releases(releases),
            ["v2.1.0", "v2.11.2"],
        )

    def test_max_semver_is_numeric(self) -> None:
        self.assertEqual(
            publisher.max_semver(["v2.9.0", "v2.11.2", "v2.1.0"]),
            "v2.11.2",
        )

    def test_latest_does_not_move_backward(self) -> None:
        self.assertFalse(publisher.should_move_latest("v2.11.2", "v2.1.0"))
        self.assertFalse(publisher.should_move_latest("v2.11.2", "v2.11.2"))
        self.assertTrue(publisher.should_move_latest("v2.5.0", "v2.11.2"))
        self.assertTrue(publisher.should_move_latest("", "v2.1.0"))

    def _release(self, tag: str, names: list[str], prerelease: bool = False) -> dict:
        return {
            "tag_name": tag,
            "draft": False,
            "prerelease": prerelease,
            "assets": [{"name": name} for name in names],
        }


if __name__ == "__main__":
    unittest.main()
