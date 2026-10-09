#!/usr/bin/env python3
"""Download, verify, and stage unofficial Codync host archives.

The publisher is stdlib-only. It understands both Linux archive names
upstream has shipped:

* v2.2.0 and later: ``codync-host-linux-x86_64.tar.gz`` and
  ``codync-host-linux-arm64.tar.gz``
* v2.1.0: ``codync-host-2.1.0-x86_64-unknown-linux-gnu.tar.gz`` and
  ``codync-host-2.1.0-aarch64-unknown-linux-gnu.tar.gz``

A tag is eligible only when both architectures and both ``.sha256`` files
exist for one scheme. Desktop app archives (``codync-linux-*``, AppImage,
``.deb``) are never selected. v1.0.0 through v1.0.5 are macOS-only and are
below the 2.1.0 floor.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Iterable, Mapping, Sequence

UPSTREAM_API = "https://api.github.com/repos/leepokai/Codync/releases"
USER_AGENT = "codync-host-image"
MIN_VERSION = (2, 1, 0)
# Docker TARGETARCH -> archive role. The Dockerfile copies $TARGETARCH/.
ARCHES = ("amd64", "arm64")
MODERN_ARCHIVES = {
    "amd64": "codync-host-linux-x86_64.tar.gz",
    "arm64": "codync-host-linux-arm64.tar.gz",
}
LEGACY_TRIPLES = {
    "amd64": "x86_64-unknown-linux-gnu",
    "arm64": "aarch64-unknown-linux-gnu",
}
HOST_FILES = ("codync-host", "codync-screen", "cua-driver", "LICENSE")
REQUIRED_FILES = ("codync-host", "LICENSE")
SEMVER_RE = re.compile(r"v(\d+)\.(\d+)\.(\d+)\Z")
SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")


class PublishError(Exception):
    """A release cannot be staged."""


class IneligibleRelease(PublishError):
    """The tag is missing a Linux archive or its checksum."""


class ChecksumError(PublishError):
    """The archive bytes do not match the checksum file."""


def parse_semver(tag: str) -> tuple[int, int, int] | None:
    match = SEMVER_RE.fullmatch(tag.strip())
    if match is None:
        return None
    return tuple(int(part) for part in match.groups())


def is_publishable_tag(tag: str) -> bool:
    parsed = parse_semver(tag)
    return parsed is not None and parsed >= MIN_VERSION


def numeric_version(tag: str) -> str:
    text = tag.strip()
    if text[:1] in ("v", "V"):
        text = text[1:]
    return text


def legacy_archive_name(tag: str, arch: str) -> str:
    version = numeric_version(tag)
    triple = LEGACY_TRIPLES[arch]
    return f"codync-host-{version}-{triple}.tar.gz"


def scheme_archives(names_by_arch: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    """Pair each archive with the checksum file that must sit beside it."""
    return {arch: (name, name + ".sha256") for arch, name in names_by_arch.items()}


def candidate_schemes(tag: str) -> list[dict[str, tuple[str, str]]]:
    """Modern names first, then the v2.1.0 triple names."""
    legacy = {arch: legacy_archive_name(tag, arch) for arch in ARCHES}
    return [scheme_archives(MODERN_ARCHIVES), scheme_archives(legacy)]


def resolve_archives(tag: str, asset_names: Iterable[str]) -> dict[str, tuple[str, str]]:
    """Pick the one complete Linux scheme for ``tag``.

    Both architectures and both checksum files are required. When both
    schemes are complete, the modern ``codync-host-linux-*`` names win.
    """
    if not is_publishable_tag(tag):
        raise IneligibleRelease(f"{tag} is below v2.1.0 or is not a stable host tag")
    available = set(asset_names)
    for scheme in candidate_schemes(tag):
        if all(archive in available and checksum in available for archive, checksum in scheme.values()):
            return scheme
    raise IneligibleRelease(
        f"{tag} does not have both Linux host archives and their .sha256 files"
    )


def parse_sha256(checksum_text: str) -> str:
    """Return the first whitespace-separated field of a checksum file.

    ``shasum -a 256`` writes ``<hex>  <filename>``. Only the hex field is
    checked; the filename token is ignored.
    """
    for line in checksum_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        field = stripped.split()[0]
        if SHA256_RE.fullmatch(field) is None:
            raise ChecksumError("checksum file does not start with a sha256 hex digest")
        return field.lower()
    raise ChecksumError("checksum file is empty")


def verify_sha256(archive_bytes: bytes, checksum_text: str) -> str:
    expected = parse_sha256(checksum_text)
    actual = hashlib.sha256(archive_bytes).hexdigest()
    if actual != expected:
        raise ChecksumError(f"sha256 mismatch: archive is {actual}, checksum file says {expected}")
    return actual


def _safe_member_name(name: str) -> bool:
    path = PurePosixPath(name)
    if path.is_absolute():
        return False
    return ".." not in path.parts


def extract_host_files(archive_bytes: bytes, dest: Path) -> dict[str, Path]:
    """Write host files into ``dest``, finding them by filename.

    ``codync-host`` and ``LICENSE`` are required. ``codync-screen`` and
    ``cua-driver`` are copied when the archive contains a regular file with
    that name. The first match in archive order wins.
    """
    dest.mkdir(parents=True, exist_ok=True)
    found: dict[str, tarfile.TarInfo] = {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or not _safe_member_name(member.name):
                continue
            filename = PurePosixPath(member.name).name
            if filename in HOST_FILES and filename not in found:
                found[filename] = member
        missing = [name for name in REQUIRED_FILES if name not in found]
        if missing:
            raise PublishError("archive is missing " + ", ".join(missing))
        written: dict[str, Path] = {}
        for filename, member in found.items():
            extracted = tar.extractfile(member)
            if extracted is None:
                raise PublishError(f"cannot read {filename} from archive")
            target = dest / filename
            target.write_bytes(extracted.read())
            if filename != "LICENSE":
                target.chmod(0o755)
            else:
                target.chmod(0o644)
            written[filename] = target
    return written


def eligible_tags_from_releases(releases: Sequence[Mapping[str, object]]) -> list[str]:
    """Stable v2.1.0+ tags whose asset names resolve, oldest first."""
    chosen: list[tuple[tuple[int, int, int], str]] = []
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not is_publishable_tag(tag):
            continue
        assets = release.get("assets") or []
        names: list[str] = []
        if isinstance(assets, list):
            for asset in assets:
                if isinstance(asset, Mapping) and isinstance(asset.get("name"), str):
                    names.append(asset["name"])
        try:
            resolve_archives(tag, names)
        except IneligibleRelease:
            continue
        parsed = parse_semver(tag)
        if parsed is not None:
            chosen.append((parsed, tag))
    chosen.sort()
    return [tag for _, tag in chosen]


def max_semver(tags: Sequence[str]) -> str:
    parsed = [(parse_semver(tag), tag) for tag in tags]
    valid = [(key, tag) for key, tag in parsed if key is not None]
    if not valid:
        raise PublishError("no semver tags")
    return max(valid)[1]


def should_move_latest(current: str, candidate: str) -> bool:
    """True when ``candidate`` is strictly newer than the tag ``latest`` already names.

    An empty ``current`` means ``latest`` is absent or does not match a host
    tag. Backfill must not point ``latest`` at an older release.
    """
    if not candidate:
        raise PublishError("candidate tag is required")
    if not current:
        return True
    current_key = parse_semver(current)
    candidate_key = parse_semver(candidate)
    if current_key is None or candidate_key is None:
        raise PublishError(f"not a stable host tag: {current!r} or {candidate!r}")
    return candidate_key > current_key


def _request(
    url: str,
    timeout: int = 60,
    accept: str = "application/vnd.github+json",
) -> tuple[bytes, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            link = response.headers.get("Link", "")
    except urllib.error.HTTPError as exc:
        raise PublishError(f"GitHub API {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise PublishError(f"cannot reach {url}: {exc.reason}") from exc
    return body, link


def _next_link(link_header: str) -> str | None:
    for part in link_header.split(","):
        section = part.strip()
        if section.endswith('rel="next"') and "<" in section and ">" in section:
            return section.split("<", 1)[1].split(">", 1)[0]
    return None


def fetch_releases() -> list[dict]:
    releases: list[dict] = []
    url: str | None = UPSTREAM_API + "?per_page=100"
    while url:
        body, link = _request(url)
        page = json.loads(body.decode("utf-8"))
        if not isinstance(page, list):
            raise PublishError("unexpected GitHub releases payload")
        releases.extend(page)
        url = _next_link(link)
    return releases


def list_eligible_tags() -> list[str]:
    return eligible_tags_from_releases(fetch_releases())


def fetch_release(tag: str) -> dict:
    body, _link = _request(f"{UPSTREAM_API}/tags/{tag}")
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise PublishError(f"unexpected release payload for {tag}")
    return payload


def _asset_urls(release: Mapping[str, object]) -> dict[str, str]:
    assets = release.get("assets") or []
    urls: dict[str, str] = {}
    if isinstance(assets, list):
        for asset in assets:
            if not isinstance(asset, Mapping):
                continue
            name = asset.get("name")
            download = asset.get("browser_download_url")
            if isinstance(name, str) and isinstance(download, str):
                urls[name] = download
    return urls


def stage_release(tag: str, dest: Path) -> dict[str, tuple[str, str]]:
    """Download both architectures into ``dest/<arch>/`` after checksum verification."""
    release = fetch_release(tag)
    urls = _asset_urls(release)
    scheme = resolve_archives(tag, urls.keys())
    dest.mkdir(parents=True, exist_ok=True)
    for arch, (archive_name, checksum_name) in scheme.items():
        archive_bytes, _ignored = _request(urls[archive_name], timeout=300, accept="application/octet-stream")
        checksum_bytes, _ignored = _request(urls[checksum_name], timeout=60, accept="application/octet-stream")
        verify_sha256(archive_bytes, checksum_bytes.decode("utf-8", errors="replace"))
        arch_dir = dest / arch
        if arch_dir.exists():
            for child in arch_dir.iterdir():
                if child.is_file():
                    child.unlink()
        extract_host_files(archive_bytes, arch_dir)
    return scheme


def _print_tags(tags: Sequence[str]) -> None:
    for tag in tags:
        print(tag)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage Codync host Linux archives")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-eligible", help="Print eligible upstream tags, oldest first")

    check = sub.add_parser("check-eligible", help="Exit 0 when a tag has both Linux archives")
    check.add_argument("--tag", required=True)

    stage = sub.add_parser("stage", help="Verify and extract both architectures")
    stage.add_argument("--tag", required=True)
    stage.add_argument("--dest", type=Path, required=True)

    maximum = sub.add_parser("max-semver", help="Print the highest vX.Y.Z from the remaining args")
    maximum.add_argument("tags", nargs="*")

    as_json = sub.add_parser("json-array", help="Print the remaining args as a JSON array")
    as_json.add_argument("tags", nargs="*")

    move = sub.add_parser(
        "should-move-latest",
        help="Exit 0 when candidate is strictly newer than current",
    )
    move.add_argument("--current", default="")
    move.add_argument("--candidate", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "list-eligible":
            _print_tags(list_eligible_tags())
        elif args.command == "check-eligible":
            release = fetch_release(args.tag)
            resolve_archives(args.tag, _asset_urls(release).keys())
            print(args.tag)
        elif args.command == "stage":
            scheme = stage_release(args.tag, args.dest)
            for arch, (archive_name, _checksum) in scheme.items():
                print(f"{arch} {archive_name}")
        elif args.command == "max-semver":
            print(max_semver(args.tags))
        elif args.command == "json-array":
            print(json.dumps(list(args.tags)))
        elif args.command == "should-move-latest":
            if not should_move_latest(args.current, args.candidate):
                return 1
        else:
            parser.error(f"unknown command {args.command}")
    except PublishError as exc:
        print(f"publisher: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
