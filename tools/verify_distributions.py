#!/usr/bin/env python3
"""Verify that built Python distributions preserve the declared provenance scope."""

from __future__ import annotations

import argparse
import base64
import csv
import email.parser
import gzip
import hashlib
import io
import json
import os
import re
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import venv
import zipfile
import zlib
from pathlib import Path, PurePosixPath
from packaging.markers import Marker
from packaging.requirements import Requirement

from sra.provenance import _source_tree_sha256


MAX_ARCHIVE_METADATA_BYTES = 4 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
ARCHIVE_READ_CHUNK_BYTES = 1024 * 1024


def _canonical_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _expected_metadata_fields(project: dict) -> dict[str, object]:
    authors = project.get("authors", [])
    author_names = [entry.get("name") for entry in authors if entry.get("name")]
    author_emails = [
        f"{entry['name']} <{entry['email']}>"
        if entry.get("name") and entry.get("email")
        else entry.get("email")
        for entry in authors
        if entry.get("email")
    ]
    optional_dependencies = project.get("optional-dependencies", {})
    requires_dist = list(project.get("dependencies", []))
    for extra, dependencies in optional_dependencies.items():
        for dependency in dependencies:
            requirement=Requirement(dependency)
            existing=f'({requirement.marker}) and ' if requirement.marker is not None else ''
            requirement.marker=Marker(existing+f'extra == "{extra}"')
            requires_dist.append(str(requirement))
    urls = project.get("urls", {})
    license_value = project.get("license")
    if isinstance(license_value, dict):
        license_expression = license_value.get("text")
    else:
        license_expression = license_value
    readme = project.get("readme", "README.md")
    description_content_type = (
        "text/markdown"
        if isinstance(readme, str) and Path(readme).suffix.lower() in {".md", ".markdown"}
        else None
    )
    expected: dict[str, object] = {
        "Metadata-Version": "2.4",
        "Name": project["name"],
        "Version": project["version"],
        "Summary": project.get("description"),
        "Author": ", ".join(author_names) if author_names else None,
        "Author-email": ", ".join(author_emails) if author_emails else None,
        "License-Expression": license_expression,
        "Requires-Python": project.get("requires-python"),
        "Keywords": ",".join(project.get("keywords", [])) or None,
        "Classifier": project.get("classifiers", []),
        "Project-URL": [f"{label}, {url}" for label, url in urls.items()],
        "License-File": project.get("license-files", []),
        "Provides-Extra": list(optional_dependencies),
        "Requires-Dist": requires_dist,
        "Description-Content-Type": description_content_type,
        "Dynamic": ["license-file"],
    }
    return expected


def _verify_metadata(
    metadata_bytes: bytes,
    expected_name: str,
    expected_version: str,
    artifact_name: str,
    expected_project: dict | None = None,
    repository_root: Path | None = None,
) -> None:
    metadata = email.parser.BytesParser().parsebytes(metadata_bytes)
    if metadata.defects:
        raise SystemExit(
            f"{artifact_name}: malformed distribution metadata: {metadata.defects!r}"
        )
    actual_name = metadata.get("Name")
    actual_version = metadata.get("Version")
    if not actual_name or _canonical_distribution_name(actual_name) != _canonical_distribution_name(expected_name):
        raise SystemExit(
            f"{artifact_name}: distribution Name mismatch; expected {expected_name!r}, got {actual_name!r}"
        )
    if actual_version != expected_version:
        raise SystemExit(
            f"{artifact_name}: distribution Version mismatch; expected {expected_version!r}, got {actual_version!r}"
        )
    if expected_project is None:
        return

    expected_fields = _expected_metadata_fields(expected_project)
    allowed_headers = {field.casefold() for field in expected_fields}
    actual_headers = {field.casefold() for field in metadata.keys()}
    unexpected_headers = sorted(actual_headers - allowed_headers)
    if unexpected_headers:
        raise SystemExit(
            f"{artifact_name}: unrecognized metadata headers: {unexpected_headers}"
        )
    for field, expected_value in expected_fields.items():
        actual_values = metadata.get_all(field) or []
        if expected_value is None:
            if actual_values:
                raise SystemExit(
                    f"{artifact_name}: unexpected {field} metadata values: {actual_values!r}"
                )
            continue
        if isinstance(expected_value, list):
            if actual_values != expected_value:
                raise SystemExit(
                    f"{artifact_name}: {field} metadata differs from pyproject.toml; "
                    f"expected={expected_value!r}, actual={actual_values!r}"
                )
        else:
            if len(actual_values) != 1 or actual_values[0] != expected_value:
                raise SystemExit(
                    f"{artifact_name}: {field} metadata differs from pyproject.toml; "
                    f"expected={expected_value!r}, actual={actual_values!r}"
                )

    readme = expected_project.get("readme", "README.md")
    if isinstance(readme, str) and repository_root is not None:
        expected_description = (repository_root / readme).read_bytes()
        actual_description = metadata.get_payload(decode=True)
        # Core metadata is a text message; Windows builders may serialize its
        # payload with RFC CRLF. Source README members are still compared byte-
        # for-byte below, so only generated metadata line endings are normalized.
        if actual_description.replace(b"\r\n", b"\n") != expected_description.replace(b"\r\n", b"\n"):
            raise SystemExit(f"{artifact_name}: distribution description differs from {readme}")


def _safe_archive_path(name: str, artifact_name: str) -> str:
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or name.startswith("/")
        or re.match(r"^[A-Za-z]:", name) is not None
    ):
        raise SystemExit(f"{artifact_name}: invalid or drive-prefixed archive member path {name!r}")
    normalized_input = name[:-1] if name.endswith("/") else name
    components = normalized_input.split("/")
    if not normalized_input or any(part in {"", ".", ".."} for part in components):
        raise SystemExit(f"{artifact_name}: unsafe archive member path {name!r}")
    return PurePosixPath(normalized_input).as_posix()


def _expected_directories(files: set[str], root: str = "") -> set[str]:
    directories: set[str] = set()
    if root:
        directories.add(root)
    for filename in files:
        parent = PurePosixPath(filename).parent
        while parent.as_posix() not in {"", "."}:
            directories.add(parent.as_posix())
            parent = parent.parent
    return directories


def _expected_sdist_metadata_files(expected_name: str, expected_version: str) -> set[str]:
    egg_info = f"src/{expected_name.replace('-', '_')}.egg-info"
    return {
        "PKG-INFO",
        "setup.cfg",
        f"{egg_info}/PKG-INFO",
        f"{egg_info}/SOURCES.txt",
        f"{egg_info}/dependency_links.txt",
        f"{egg_info}/entry_points.txt",
        f"{egg_info}/requires.txt",
        f"{egg_info}/top_level.txt",
    }


def _expected_sdist_sidecar_contents(root: Path, files: set[str], name: str, project: dict) -> dict[str, bytes]:
    egg = f"src/{name.replace('-', '_')}.egg-info"
    scripts = project.get("scripts", {})
    entry_points = "[console_scripts]\n" + "".join(
        f"{key} = {value}\n" for key, value in scripts.items()
    ) if scripts else ""
    dependency_groups = {}
    for extra, items in project.get("optional-dependencies", {}).items():
        if items:
            dependency_groups.setdefault(extra, [])
        for item in items:
            requirement = Requirement(item)
            group = extra if requirement.marker is None else f"{extra}:{requirement.marker}"
            requirement.marker = None
            dependency_groups.setdefault(group, []).append(str(requirement))
    requires = "".join(
        f"\n[{group}]\n" + ("\n".join(items) + "\n" if items else "")
        for group, items in sorted(dependency_groups.items())
    )
    packages = sorted(
        item.name for item in (root / "src").iterdir()
        if item.is_dir() and (item / "__init__.py").is_file()
    )
    return {
        "setup.cfg": b"[egg_info]\ntag_build = \ntag_date = 0\n\n",
        f"{egg}/SOURCES.txt": ("\n".join(sorted(
            files - {"setup.cfg", "PKG-INFO"}, key=lambda path: os.path.split(path)
        ))).encode(),
        f"{egg}/dependency_links.txt": b"\n",
        f"{egg}/entry_points.txt": entry_points.encode(),
        f"{egg}/requires.txt": requires.encode(),
        f"{egg}/top_level.txt": ("".join(f"{item}\n" for item in packages)).encode(),
    }


def _read_tar_member_bounded(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    artifact_name: str,
) -> bytes:
    if member.size > MAX_ARCHIVE_METADATA_BYTES:
        raise SystemExit(
            f"{artifact_name}: archive metadata member exceeds "
            f"{MAX_ARCHIVE_METADATA_BYTES} bytes: {member.name}"
        )
    stream = archive.extractfile(member)
    if stream is None:
        raise SystemExit(f"{artifact_name}: cannot read archive member {member.name}")
    with stream:
        content = stream.read(MAX_ARCHIVE_METADATA_BYTES + 1)
    if len(content) != member.size or len(content) > MAX_ARCHIVE_METADATA_BYTES:
        raise SystemExit(f"{artifact_name}: invalid or oversized archive member {member.name}")
    return content


def _compare_tar_member_to_file(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    expected_path: Path,
    artifact_name: str,
) -> None:
    expected_size = expected_path.stat().st_size
    if member.size != expected_size:
        raise SystemExit(
            f"{artifact_name}: size mismatch for {member.name}; "
            f"expected={expected_size}, archived={member.size}"
        )
    stream = archive.extractfile(member)
    if stream is None:
        raise SystemExit(f"{artifact_name}: cannot read {member.name}")
    with expected_path.open("rb") as expected_stream, stream:
        while True:
            expected_chunk = expected_stream.read(ARCHIVE_READ_CHUNK_BYTES)
            if not expected_chunk:
                break
            archived_chunk = stream.read(len(expected_chunk))
            if archived_chunk != expected_chunk:
                raise SystemExit(f"{artifact_name}: content mismatch for {member.name}")
        if stream.read(1):
            raise SystemExit(f"{artifact_name}: content longer than expected for {member.name}")


def _read_zip_member_bounded(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    artifact_name: str,
    *,
    limit: int = MAX_ARCHIVE_METADATA_BYTES,
) -> bytes:
    if info.file_size > limit:
        raise SystemExit(
            f"{artifact_name}: wheel metadata member exceeds {limit} bytes: {info.filename}"
        )
    with archive.open(info, "r") as stream:
        content = stream.read(limit + 1)
    if len(content) != info.file_size or len(content) > limit:
        raise SystemExit(f"{artifact_name}: invalid or oversized wheel member {info.filename}")
    return content


def _compare_zip_member_to_file(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    expected_path: Path,
    artifact_name: str,
) -> tuple[str, int]:
    expected_size = expected_path.stat().st_size
    if info.file_size != expected_size:
        raise SystemExit(
            f"{artifact_name}: size mismatch for {info.filename}; "
            f"expected={expected_size}, archived={info.file_size}"
        )
    digest = hashlib.sha256()
    total = 0
    with expected_path.open("rb") as expected_stream, archive.open(info, "r") as archived_stream:
        while True:
            expected_chunk = expected_stream.read(ARCHIVE_READ_CHUNK_BYTES)
            if not expected_chunk:
                break
            archived_chunk = archived_stream.read(len(expected_chunk))
            if archived_chunk != expected_chunk:
                raise SystemExit(f"{artifact_name}: wheel content mismatch for {info.filename}")
            digest.update(archived_chunk)
            total += len(archived_chunk)
        if archived_stream.read(1):
            raise SystemExit(f"{artifact_name}: wheel member longer than expected: {info.filename}")
    return digest.hexdigest(), total


def _check_gzip_archive_expansion(archive_path: Path) -> None:
    expanded_bytes = 0
    try:
        with gzip.open(archive_path, "rb") as stream:
            while True:
                chunk = stream.read(ARCHIVE_READ_CHUNK_BYTES)
                if not chunk:
                    break
                expanded_bytes += len(chunk)
                if expanded_bytes > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                    raise SystemExit(
                        f"{archive_path.name}: expanded source archive exceeds "
                        f"{MAX_ARCHIVE_UNCOMPRESSED_BYTES} bytes"
                    )
    except (OSError, EOFError, zlib.error) as exc:
        raise SystemExit(f"{archive_path.name}: invalid gzip source archive: {exc}") from exc


def _verify_sdist(
    archive_path: Path,
    root: Path,
    expected_files: list[str],
    expected_name: str,
    expected_version: str,
    expected_project: dict | None = None,
) -> None:
    if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise SystemExit(
            f"{archive_path.name}: compressed source archive exceeds {MAX_ARCHIVE_BYTES} bytes"
        )
    _check_gzip_archive_expansion(archive_path)
    expected_sdist_files = set(expected_files) | _expected_sdist_metadata_files(
        expected_name, expected_version
    )
    canonical_source_root = (
        f"{re.sub(r'[-_.]+', '_', expected_name)}-{expected_version}"
    )
    expected_archive_files = {
        f"{canonical_source_root}/{relative}" for relative in expected_sdist_files
    }
    maximum_member_count = len(expected_archive_files) + len(
        _expected_directories(expected_archive_files, root=canonical_source_root)
    )
    with tarfile.open(archive_path, "r:gz") as archive:
        normalized_members: dict[str, tarfile.TarInfo] = {}
        file_paths: set[str] = set()
        directory_paths: set[str] = set()
        while True:
            member = archive.next()
            if member is None:
                break
            if len(normalized_members) >= maximum_member_count:
                raise SystemExit(
                    f"{archive_path.name}: source archive contains too many members"
                )
            normalized = _safe_archive_path(member.name, archive_path.name)
            if normalized in normalized_members:
                raise SystemExit(
                    f"{archive_path.name}: duplicate archive member path {normalized!r}"
                )
            normalized_members[normalized] = member
            is_directory = member.isdir()
            if member.name.endswith("/") and not is_directory:
                raise SystemExit(
                    f"{archive_path.name}: regular file has a directory-style path: {normalized!r}"
                )
            if is_directory:
                if member.type != tarfile.DIRTYPE or member.size != 0:
                    raise SystemExit(
                        f"{archive_path.name}: directory member must be a zero-size directory: "
                        f"{normalized!r}"
                    )
                directory_paths.add(normalized)
            elif member.type in {tarfile.REGTYPE, tarfile.AREGTYPE}:
                file_paths.add(normalized)
            else:
                raise SystemExit(
                    f"{archive_path.name}: non-regular archive member is forbidden: "
                    f"{normalized!r} (type={member.type!r})"
                )

        roots = {
            PurePosixPath(name).parts[0]
            for name in normalized_members
            if PurePosixPath(name).parts
        }
        if len(roots) != 1:
            raise SystemExit(f"{archive_path.name}: expected one source root, found {sorted(roots)}")
        source_root = next(iter(roots))
        if source_root != canonical_source_root:
            raise SystemExit(
                f"{archive_path.name}: source root {source_root!r} does not match "
                f"canonical project root {canonical_source_root!r}"
            )
        expected_archive_directories = _expected_directories(
            expected_archive_files, root=source_root
        )
        actual_archive_files = {
            name for name in file_paths if name.startswith(source_root + "/")
        }
        actual_archive_directories = {
            name for name in directory_paths
            if name == source_root or name.startswith(source_root + "/")
        }
        if actual_archive_files != expected_archive_files:
            unexpected = sorted(actual_archive_files - expected_archive_files)
            missing = sorted(expected_archive_files - actual_archive_files)
            raise SystemExit(
                f"{archive_path.name}: complete source archive file inventory differs; "
                f"unexpected={unexpected}, missing={missing}"
            )
        if actual_archive_directories != expected_archive_directories:
            unexpected = sorted(actual_archive_directories - expected_archive_directories)
            missing = sorted(expected_archive_directories - actual_archive_directories)
            raise SystemExit(
                f"{archive_path.name}: complete source archive directory inventory differs; "
                f"unexpected={unexpected}, missing={missing}"
            )
        if set(normalized_members) != expected_archive_files | expected_archive_directories:
            outside_root = sorted(
                set(normalized_members) - expected_archive_files - expected_archive_directories
            )
            raise SystemExit(
                f"{archive_path.name}: archive members outside the declared package root: {outside_root}"
            )

        pkg_info_relatives = sorted(
            relative for relative in expected_sdist_files
            if relative == "PKG-INFO" or relative.endswith("/PKG-INFO")
        )
        for relative in pkg_info_relatives:
            member = normalized_members[f"{source_root}/{relative}"]
            metadata_bytes = _read_tar_member_bounded(archive, member, archive_path.name)
            _verify_metadata(
                metadata_bytes,
                expected_name,
                expected_version,
                archive_path.name,
                expected_project=expected_project,
                repository_root=root,
            )
        for relative in expected_files:
            member = normalized_members[f"{source_root}/{relative}"]
            _compare_tar_member_to_file(
                archive, member, root / relative, archive_path.name
            )
        if expected_project is not None:
            for relative, expected_content in _expected_sdist_sidecar_contents(
                root, expected_sdist_files, expected_name, expected_project
            ).items():
                member = normalized_members[f"{source_root}/{relative}"]
                actual_content = _read_tar_member_bounded(archive, member, archive_path.name)
                if actual_content.replace(b"\r\n", b"\n") != expected_content.replace(b"\r\n", b"\n"):
                    raise SystemExit(
                        f"{archive_path.name}: source archive metadata sidecar content mismatch: {relative}"
                    )
    print(
        f"sdist provenance inventory: PASS "
        f"({len(expected_files)} source files, complete archive allowlist, byte-identical)"
    )


def _preflight_zip_archive(
    archive_path: Path,
    maximum_member_count: int,
) -> None:
    file_size = archive_path.stat().st_size
    if file_size > MAX_ARCHIVE_BYTES:
        raise SystemExit(
            f"{archive_path.name}: wheel archive exceeds {MAX_ARCHIVE_BYTES} bytes"
        )
    eocd_size = 22
    maximum_comment = 65535
    tail_size = min(file_size, eocd_size + maximum_comment)
    with archive_path.open("rb") as stream:
        stream.seek(file_size - tail_size)
        tail = stream.read(tail_size)
    eocd_signature = b"PK\x05\x06"
    eocd_offset_in_tail = tail.rfind(eocd_signature)
    if eocd_offset_in_tail < 0 or len(tail) - eocd_offset_in_tail < eocd_size:
        raise SystemExit(f"{archive_path.name}: ZIP end-of-central-directory record is missing")
    (
        signature,
        disk_number,
        central_directory_disk,
        entries_on_disk,
        total_entries,
        central_directory_size,
        central_directory_offset,
        comment_length,
    ) = struct.unpack_from("<4s4H2LH", tail, eocd_offset_in_tail)
    eocd_absolute_offset = file_size - tail_size + eocd_offset_in_tail
    if signature != eocd_signature or eocd_offset_in_tail + eocd_size + comment_length != len(tail):
        raise SystemExit(f"{archive_path.name}: invalid ZIP end-of-central-directory record")
    if disk_number != 0 or central_directory_disk != 0 or entries_on_disk != total_entries:
        raise SystemExit(f"{archive_path.name}: multi-disk ZIP archives are forbidden")
    if (
        entries_on_disk == 0xFFFF
        or total_entries == 0xFFFF
        or central_directory_size == 0xFFFFFFFF
        or central_directory_offset == 0xFFFFFFFF
    ):
        raise SystemExit(f"{archive_path.name}: ZIP64 archives are not accepted for this package")
    if total_entries > maximum_member_count:
        raise SystemExit(f"{archive_path.name}: wheel contains too many archive members")
    if central_directory_size > 2 * 1024 * 1024:
        raise SystemExit(f"{archive_path.name}: ZIP central directory exceeds 2 MiB")
    if central_directory_offset + central_directory_size > eocd_absolute_offset:
        raise SystemExit(f"{archive_path.name}: ZIP central directory overlaps its end record")
    with archive_path.open("rb") as stream:
        stream.seek(central_directory_offset)
        central_directory = stream.read(central_directory_size)
    if len(central_directory) != central_directory_size:
        raise SystemExit(f"{archive_path.name}: truncated ZIP central directory")
    _count_zip_central_entries(
        central_directory, total_entries, maximum_member_count, archive_path.name
    )


def _count_zip_central_entries(data: bytes, expected_count: int, maximum: int, name: str) -> None:
    position = 0
    count = 0
    while position < len(data):
        remaining = len(data) - position
        if remaining < 46:
            raise SystemExit(f"{name}: truncated ZIP central-directory entry")
        fields = struct.unpack_from("<4s6H3I5H2I", data, position)
        if fields[0] != b"PK\x01\x02":
            raise SystemExit(f"{name}: invalid ZIP central-directory entry signature")
        name_len, extra_len, comment_len = fields[10:13]
        if 46 + name_len + extra_len + comment_len > remaining:
            raise SystemExit(f"{name}: ZIP central-directory entry exceeds its bounds")
        if fields[13] != 0 or 0xFFFFFFFF in (fields[8], fields[9], fields[16]):
            raise SystemExit(f"{name}: unsupported multi-disk or ZIP64 entry")
        count += 1
        if count > maximum:
            raise SystemExit(f"{name}: wheel contains too many archive members")
        position += 46 + name_len + extra_len + comment_len
    if count != expected_count:
        raise SystemExit(f"{name}: ZIP central-directory entry count mismatch (EOCD={expected_count}, actual={count})")


def _verify_wheel(
    archive_path: Path,
    root: Path,
    expected_name: str,
    expected_version: str,
    expected_project: dict | None = None,
) -> None:
    expected_sources = sorted(
        path.relative_to(root / "src").as_posix()
        for path in (root / "src" / "sra").rglob("*.py")
        if path.is_file()
    )
    # py.typed is package data rather than a module, but it ships in the wheel
    # and belongs in the inventory exactly like the modules do: without it the
    # complete-file check called a published PEP 561 marker "unexpected".
    py_typed = root / "src" / "sra" / "py.typed"
    if py_typed.is_file():
        expected_sources.append(py_typed.relative_to(root / "src").as_posix())
        expected_sources.sort()
    dist_info_root = (
        f"{expected_name.replace('-', '_')}-{expected_version}.dist-info"
    )
    dist_info_files = {
        f"{dist_info_root}/METADATA",
        f"{dist_info_root}/WHEEL",
        f"{dist_info_root}/entry_points.txt",
        f"{dist_info_root}/top_level.txt",
        f"{dist_info_root}/RECORD",
        f"{dist_info_root}/licenses/LICENSE",
    }
    expected_wheel_files = set(expected_sources) | dist_info_files
    expected_wheel_directories = _expected_directories(expected_wheel_files)
    maximum_member_count = len(expected_wheel_files) + len(expected_wheel_directories)
    _preflight_zip_archive(archive_path, maximum_member_count)
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        if len(infos) > maximum_member_count:
            raise SystemExit(f"{archive_path.name}: wheel contains too many archive members")
        normalized_members: dict[str, zipfile.ZipInfo] = {}
        file_paths: set[str] = set()
        directory_paths: set[str] = set()
        for info in infos:
            normalized = _safe_archive_path(info.filename, archive_path.name)
            if normalized in normalized_members:
                raise SystemExit(
                    f"{archive_path.name}: duplicate wheel member path {normalized!r}"
                )
            normalized_members[normalized] = info
            if info.flag_bits & 0x1:
                raise SystemExit(f"{archive_path.name}: encrypted wheel member is forbidden")
            file_type = stat.S_IFMT(info.external_attr >> 16)
            if info.is_dir():
                if file_type not in {0, stat.S_IFDIR}:
                    raise SystemExit(
                        f"{archive_path.name}: non-directory ZIP type has a directory path: "
                        f"{normalized!r}"
                    )
                if info.file_size != 0:
                    raise SystemExit(
                        f"{archive_path.name}: directory member has a nonzero payload: {normalized!r}"
                    )
                directory_paths.add(normalized)
                continue
            if file_type not in {0, stat.S_IFREG}:
                raise SystemExit(
                    f"{archive_path.name}: non-regular wheel member is forbidden: "
                    f"{normalized!r} (mode={info.external_attr >> 16:#o})"
                )
            file_paths.add(normalized)

        if file_paths != expected_wheel_files:
            unexpected = sorted(file_paths - expected_wheel_files)
            missing = sorted(expected_wheel_files - file_paths)
            raise SystemExit(
                f"{archive_path.name}: complete wheel file inventory differs; "
                f"unexpected={unexpected}, missing={missing}"
            )
        # ZIP archives may omit directory entries; any explicit directory member
        # must still be a parent directory of an allowlisted wheel file.
        if not directory_paths.issubset(expected_wheel_directories):
            unexpected = sorted(directory_paths - expected_wheel_directories)
            raise SystemExit(
                f"{archive_path.name}: unrecognized wheel archive directories: {unexpected}"
            )
        if set(normalized_members) != expected_wheel_files | directory_paths:
            raise SystemExit(f"{archive_path.name}: unrecognized wheel archive members")

        verified_content: dict[str, tuple[str, int]] = {}
        metadata_bytes = _read_zip_member_bounded(
            archive, normalized_members[f"{dist_info_root}/METADATA"], archive_path.name
        )
        verified_content[f"{dist_info_root}/METADATA"] = (
            hashlib.sha256(metadata_bytes).hexdigest(), len(metadata_bytes)
        )
        _verify_metadata(
            metadata_bytes,
            expected_name,
            expected_version,
            archive_path.name,
            expected_project=expected_project,
            repository_root=root,
        )

        wheel_bytes = _read_zip_member_bounded(
            archive, normalized_members[f"{dist_info_root}/WHEEL"], archive_path.name,
            limit=64 * 1024,
        )
        wheel_metadata = email.parser.BytesParser().parsebytes(wheel_bytes)
        if wheel_metadata.defects:
            raise SystemExit(
                f"{archive_path.name}: malformed WHEEL metadata: {wheel_metadata.defects!r}"
            )
        wheel_header_counts: dict[str, int] = {}
        for field in wheel_metadata.keys():
            normalized_field = field.casefold()
            wheel_header_counts[normalized_field] = wheel_header_counts.get(normalized_field, 0) + 1
        allowed_wheel_headers = {
            "wheel-version", "generator", "root-is-purelib", "tag"
        }
        if set(wheel_header_counts) - allowed_wheel_headers:
            raise SystemExit(f"{archive_path.name}: unrecognized WHEEL metadata headers")
        if any(count != 1 for count in wheel_header_counts.values()):
            raise SystemExit(f"{archive_path.name}: duplicate WHEEL metadata headers")
        if (
            (wheel_metadata.get_all("Wheel-Version") or []) != ["1.0"]
            or (wheel_metadata.get_all("Root-Is-Purelib") or []) != ["true"]
            or (wheel_metadata.get_all("Tag") or []) != ["py3-none-any"]
            or not (wheel_metadata.get("Generator") or "").strip()
        ):
            raise SystemExit(f"{archive_path.name}: unsupported or inconsistent WHEEL metadata")
        verified_content[f"{dist_info_root}/WHEEL"] = (
            hashlib.sha256(wheel_bytes).hexdigest(), len(wheel_bytes)
        )

        entry_points_path = f"{dist_info_root}/entry_points.txt"
        entry_points = _read_zip_member_bounded(
            archive, normalized_members[entry_points_path], archive_path.name, limit=64 * 1024
        )
        if entry_points != b"[console_scripts]\nsra = sra.cli:main\n":
            raise SystemExit(f"{archive_path.name}: unexpected console entry-point metadata")
        verified_content[entry_points_path] = (
            hashlib.sha256(entry_points).hexdigest(), len(entry_points)
        )

        top_level_path = f"{dist_info_root}/top_level.txt"
        top_level = _read_zip_member_bounded(
            archive, normalized_members[top_level_path], archive_path.name, limit=64 * 1024
        )
        if top_level != b"sra\n":
            raise SystemExit(f"{archive_path.name}: unexpected top_level.txt metadata")
        verified_content[top_level_path] = (
            hashlib.sha256(top_level).hexdigest(), len(top_level)
        )

        license_path = f"{dist_info_root}/licenses/LICENSE"
        license_hash, license_size = _compare_zip_member_to_file(
            archive, normalized_members[license_path], root / "LICENSE", archive_path.name
        )
        verified_content[license_path] = (license_hash, license_size)

        for relative in expected_sources:
            digest, size = _compare_zip_member_to_file(
                archive, normalized_members[relative], root / "src" / relative, archive_path.name
            )
            verified_content[relative] = (digest, size)

        record_path = f"{dist_info_root}/RECORD"
        record_bytes = _read_zip_member_bounded(
            archive, normalized_members[record_path], archive_path.name
        )
        record_rows = list(csv.reader(io.StringIO(record_bytes.decode("utf-8"), newline="")))
        record: dict[str, tuple[str, str]] = {}
        for row in record_rows:
            if len(row) != 3 or row[0] in record:
                raise SystemExit(f"{archive_path.name}: malformed or duplicate wheel RECORD row")
            record[row[0]] = (row[1], row[2])
        if set(record) != expected_wheel_files:
            raise SystemExit(f"{archive_path.name}: wheel RECORD paths differ from the archive allowlist")
        for relative in expected_wheel_files:
            recorded_hash, recorded_size = record[relative]
            if relative == record_path:
                if recorded_hash or recorded_size:
                    raise SystemExit(f"{archive_path.name}: RECORD must not hash itself")
                continue
            expected_hash, expected_size = verified_content[relative]
            encoded_hash = "sha256=" + base64.urlsafe_b64encode(
                bytes.fromhex(expected_hash)
            ).decode("ascii").rstrip("=")
            if recorded_hash != encoded_hash or recorded_size != str(expected_size):
                raise SystemExit(f"{archive_path.name}: wheel RECORD hash/size mismatch for {relative}")

    # Exercise the actual wheel installer in a temporary virtual environment.
    with tempfile.TemporaryDirectory(prefix="sra-wheel-install-") as temporary:
        temporary_root = Path(temporary)
        environment_dir = temporary_root / "venv"
        venv.EnvBuilder(with_pip=True, clear=True).create(environment_dir)
        python_executable = (
            environment_dir / "Scripts" / "python.exe"
            if os.name == "nt"
            else environment_dir / "bin" / "python"
        )
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("PYTHONHOME", None)
        install = subprocess.run(
            [
                str(python_executable),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                str(archive_path),
            ],
            cwd=temporary_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if install.returncode:
            raise SystemExit(
                f"{archive_path.name}: isolated pip install failed: {install.stderr}"
            )

        scripts_dir = environment_dir / ("Scripts" if os.name == "nt" else "bin")
        entrypoint = scripts_dir / ("sra.exe" if os.name == "nt" else "sra")
        if not entrypoint.is_file():
            raise SystemExit(f"{archive_path.name}: installed sra entry point is missing")
        entrypoint_check = subprocess.run(
            [str(entrypoint), "--help"],
            cwd=temporary_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if entrypoint_check.returncode or "usage:" not in entrypoint_check.stdout.lower():
            raise SystemExit(f"{archive_path.name}: installed sra entry point failed --help")

        code = """
import json
import tempfile
from pathlib import Path
import sra
from sra.audit import audit_file
from sra.graph import validate_reasoning_graph_object
from sra.provenance import _source_tree_sha256
from sra.semantic_review import build_semantic_review_template

sha256, scope, files = _source_tree_sha256()
with tempfile.TemporaryDirectory(prefix="sra-installed-smoke-") as temporary:
    manuscript = Path(temporary) / "paper.md"
    manuscript.write_text(
        chr(10).join((
            "# Methods",
            "Protocol prespecified.",
            "# Results",
            "Signal increased.",
            "# Conclusion",
            "Signal increased.",
        )),
        encoding="utf-8",
    )
    report = audit_file(manuscript).to_dict()
    graph = report["reasoning_graph"]
    graph_validation = validate_reasoning_graph_object(graph)
    template = build_semantic_review_template(
        report,
        source_text=manuscript.read_text(encoding="utf-8"),
    )
    print(json.dumps({
        "sha256": sha256,
        "scope": scope,
        "files": files,
        "audit_schema": report["schema_version"],
        "manifest_schema": report["reproducibility_manifest"]["manifest_schema_version"],
        "graph_schema": graph["schema_version"],
        "semantic_review_schema": template["schema_version"],
        "graph_validation": graph_validation["status"],
        "module_path": str(Path(sra.__file__).resolve()),
    }))
"""
        smoke = subprocess.run(
            [str(python_executable), "-c", code],
            cwd=temporary_root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if smoke.returncode:
            raise SystemExit(
                f"{archive_path.name}: isolated installed-wheel audit smoke test failed: {smoke.stderr}"
            )
        installed_manifest = json.loads(smoke.stdout.strip())
        expected_installed_files = expected_sources
        if installed_manifest["scope"] != "installed Python package source files only":
            raise SystemExit(f"{archive_path.name}: unexpected installed-wheel hash scope")
        if installed_manifest["files"] != expected_installed_files:
            raise SystemExit(f"{archive_path.name}: installed-wheel hash file list mismatch")
        if not isinstance(installed_manifest["sha256"], str) or len(
            installed_manifest["sha256"]
        ) != 64:
            raise SystemExit(f"{archive_path.name}: invalid installed-wheel source hash")
        if (
            installed_manifest["audit_schema"] != "1.5"
            or installed_manifest["manifest_schema"] != "1.4"
            or installed_manifest["graph_schema"] != "1.4"
            or installed_manifest["semantic_review_schema"] != "1.4"
            or installed_manifest["graph_validation"] != "PASS"
        ):
            raise SystemExit(f"{archive_path.name}: installed-wheel audit smoke test failed")
        module_path = Path(installed_manifest["module_path"]).resolve()
        if environment_dir.resolve() not in module_path.parents:
            raise SystemExit(f"{archive_path.name}: wheel imported from outside the isolated environment")

    print(
        f"wheel provenance inventory and isolated pip install: PASS "
        f"({len(expected_sources)} Python modules, complete archive allowlist, byte-identical; entry point and audit passed)"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("distribution_directory", type=Path)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    distribution_directory = args.distribution_directory.expanduser().resolve()
    if not distribution_directory.is_dir():
        raise SystemExit(f"Distribution directory does not exist: {distribution_directory}")

    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    expected_name = project["name"]
    expected_version = project["version"]
    source_hash, source_scope, source_files = _source_tree_sha256(root)
    if source_hash is None or not source_files:
        raise SystemExit("Could not compute the repository provenance inventory.")
    if source_files != sorted(source_files):
        raise SystemExit("Repository provenance file list is not sorted.")
    print(f"repository provenance scope: {source_scope}")
    print(f"repository provenance hash: {source_hash}")

    sdists = sorted(distribution_directory.glob("*.tar.gz"))
    wheels = sorted(distribution_directory.glob("*.whl"))
    directory_entries = list(distribution_directory.iterdir())
    if any(not entry.is_file() or entry.is_symlink() for entry in directory_entries):
        raise SystemExit("Distribution directory may contain only regular wheel/sdist files.")
    if len(directory_entries) != 2 or len(sdists) != 1 or len(wheels) != 1:
        raise SystemExit(
            f"Expected exactly one sdist and one wheel; found {len(sdists)} and {len(wheels)}."
        )

    _verify_sdist(
        sdists[0], root, source_files, expected_name, expected_version, expected_project=project
    )
    _verify_wheel(
        wheels[0], root, expected_name, expected_version, expected_project=project
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
