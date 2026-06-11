from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from desktop.characters.character_scanner import SUPPORTED_IMAGE_EXTENSIONS
from shared.schema.character import CharacterPackManifest


CHARPACK_EXTENSION = ".charpack"
CHARPACK_FORMAT = "charaiface.character_pack"
CHARPACK_FORMAT_VERSION = 1
MAX_ARCHIVE_FILES = 64
MAX_EXTRACTED_BYTES = 128 * 1024 * 1024

_SAFE_CHARACTER_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class CharacterPackArchiveInfo:
    source_path: Path
    character_id: str
    name: str
    version: str
    author: str
    description: str


def inspect_charpack(source_path: str | Path) -> CharacterPackArchiveInfo:
    source = Path(source_path)
    manifest_data = _read_archive_manifest(source)
    manifest = _validate_archive_manifest(manifest_data)
    return CharacterPackArchiveInfo(
        source_path=source,
        character_id=manifest.id,
        name=manifest.name,
        version=manifest.version,
        author=manifest.author,
        description=manifest.description,
    )


def import_charpack(
    source_path: str | Path,
    user_characters_dir: str | Path,
    *,
    builtin_character_ids: set[str] | None = None,
    replace_existing: bool = False,
    backup_existing: bool = True,
) -> Path:
    source = Path(source_path)
    destination_root = Path(user_characters_dir)
    builtin_ids = builtin_character_ids or set()
    builtin_id_keys = {_character_id_key(character_id) for character_id in builtin_ids}

    with zipfile.ZipFile(source, "r") as archive:
        _validate_archive_entries(archive)
        manifest_data = json.loads(archive.read("manifest.json").decode("utf-8"))
        manifest = _validate_archive_manifest(manifest_data)
        _validate_archive_manifest_files(archive, manifest)

        if _character_id_key(manifest.id) in builtin_id_keys:
            raise ValueError(
                f'Character id "{manifest.id}" is reserved by a built-in character pack.'
            )

        destination_root.mkdir(parents=True, exist_ok=True)
        destination_archive = _find_case_insensitive_child(
            destination_root,
            f"{manifest.id}{CHARPACK_EXTENSION}",
        )
        existing_folder = _find_case_insensitive_child(destination_root, manifest.id)
        if destination_archive is None:
            destination_archive = destination_root / f"{manifest.id}{CHARPACK_EXTENSION}"

        existing_paths = [
            path
            for path in (destination_archive, existing_folder)
            if path is not None and path.exists()
        ]
        if existing_paths and not replace_existing:
            raise ValueError(f'Character pack already exists: "{existing_paths[0]}"')

        for existing_path in existing_paths:
            if existing_path.resolve() == source.resolve():
                continue
            if backup_existing:
                backup_path = _backup_existing_pack(destination_root, existing_path)
                shutil.move(str(existing_path), str(backup_path))
            elif existing_path.is_dir():
                shutil.rmtree(existing_path)
            else:
                existing_path.unlink()

        if destination_archive.resolve() != source.resolve():
            shutil.copy2(source, destination_archive)

    return destination_archive


def extract_charpack_to_directory(
    source_path: str | Path,
    destination: str | Path,
) -> Path:
    source = Path(source_path)
    target = Path(destination)

    with zipfile.ZipFile(source, "r") as archive:
        _validate_archive_entries(archive)
        manifest_data = json.loads(archive.read("manifest.json").decode("utf-8"))
        manifest = _validate_archive_manifest(manifest_data)
        _validate_archive_manifest_files(archive, manifest)

        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        archive.extractall(target)

    return target


def _backup_existing_pack(destination_root: Path, destination: Path) -> Path:
    backups_root = destination_root / ".backups"
    backups_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = backups_root / f"{destination.name}-{timestamp}"
    counter = 2
    while backup_dir.exists():
        backup_dir = backups_root / f"{destination.name}-{timestamp}-{counter}"
        counter += 1
    return backup_dir


def _find_case_insensitive_child(parent: Path, child_name: str) -> Path | None:
    if not parent.exists():
        return None

    child_key = _character_id_key(child_name)
    for child in parent.iterdir():
        if child.name.casefold() == child_key:
            return child
    return None


def export_folder_to_charpack(
    pack_dir: str | Path,
    target_path: str | Path,
) -> Path:
    source_dir = Path(pack_dir)
    target = _with_charpack_suffix(Path(target_path))

    manifest_path = source_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("manifest.json not found")

    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest = CharacterPackManifest(**manifest_data)
    _validate_character_id(manifest.id)
    _validate_folder_pack_files(source_dir, manifest)

    archive_manifest = dict(manifest_data)
    archive_manifest["format"] = CHARPACK_FORMAT
    archive_manifest["format_version"] = CHARPACK_FORMAT_VERSION
    archive_manifest["style_file"] = "style.md"

    avatar_images: dict[str, str] = {}
    image_entries = _collect_image_entries(source_dir, manifest)
    for state, _source_path, archive_name in image_entries:
        avatar_images[state] = archive_name

    archive_manifest["avatar"] = {
        "type": manifest.avatar.type,
        "images": avatar_images,
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps(archive_manifest, ensure_ascii=False, indent=2),
        )
        archive.write(source_dir / manifest.style_file, "style.md")

        short_style_path = source_dir / "style.short.md"
        if short_style_path.is_file():
            archive.write(short_style_path, "style.short.md")

        for _state, source_path, archive_name in image_entries:
            archive.write(source_path, archive_name)

    return target


def _read_archive_manifest(source: Path) -> dict[str, Any]:
    with zipfile.ZipFile(source, "r") as archive:
        _validate_archive_entries(archive)
        manifest_data = json.loads(archive.read("manifest.json").decode("utf-8"))
        manifest = _validate_archive_manifest(manifest_data)
        _validate_archive_manifest_files(archive, manifest)
        return manifest_data


def _validate_archive_entries(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_FILES:
        raise ValueError("Character pack archive contains too many files")

    seen_names: set[str] = set()
    for info in infos:
        if info.filename in seen_names:
            raise ValueError(f"Archive contains a duplicate path: {info.filename}")
        seen_names.add(info.filename)

    names = seen_names
    if "manifest.json" not in names:
        raise ValueError("manifest.json not found")

    total_size = 0
    for info in infos:
        name = info.filename
        if not name:
            raise ValueError("Archive contains an empty path")
        if "\\" in name:
            raise ValueError(f"Unsafe archive path: {name}")

        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe archive path: {name}")

        if _is_zip_symlink(info):
            raise ValueError(f"Archive contains a symbolic link: {name}")

        total_size += info.file_size
        if total_size > MAX_EXTRACTED_BYTES:
            raise ValueError("Character pack archive is too large")


def _validate_archive_manifest(manifest_data: dict[str, Any]) -> CharacterPackManifest:
    if manifest_data.get("format") != CHARPACK_FORMAT:
        raise ValueError("Unsupported character pack format")
    if manifest_data.get("format_version") != CHARPACK_FORMAT_VERSION:
        raise ValueError("Unsupported character pack format_version")

    manifest = CharacterPackManifest(**manifest_data)
    _validate_character_id(manifest.id)

    if manifest.avatar.type != "image":
        raise ValueError(
            f'Unsupported avatar type "{manifest.avatar.type}". '
            "Only image avatar is supported for now."
        )
    if "idle" not in manifest.avatar.images:
        raise ValueError("avatar.images.idle is required")

    _validate_manifest_relative_path(manifest.style_file, required_suffix=None)
    for state, relative_path in manifest.avatar.images.items():
        suffix = _validate_manifest_relative_path(
            relative_path,
            required_suffix=SUPPORTED_IMAGE_EXTENSIONS,
        )
        if not suffix:
            raise ValueError(f'Image file for state "{state}" has no extension')

    return manifest


def _validate_folder_pack_files(
    pack_dir: Path,
    manifest: CharacterPackManifest,
) -> None:
    if manifest.avatar.type != "image":
        raise ValueError(
            f'Unsupported avatar type "{manifest.avatar.type}". '
            "Only image avatar is supported for now."
        )
    if "idle" not in manifest.avatar.images:
        raise ValueError("avatar.images.idle is required")

    style_path = pack_dir / manifest.style_file
    if not style_path.is_file():
        raise ValueError(f'style_file "{manifest.style_file}" not found')

    idle_path = pack_dir / manifest.avatar.images["idle"]
    if not idle_path.is_file():
        raise ValueError(
            f'Image file for state "idle" not found: {manifest.avatar.images["idle"]}'
        )

    for state, relative_path in manifest.avatar.images.items():
        suffix = _validate_manifest_relative_path(
            relative_path,
            required_suffix=SUPPORTED_IMAGE_EXTENSIONS,
        )
        if state == "idle" and not suffix:
            raise ValueError('Image file for state "idle" has no extension')


def _validate_archive_manifest_files(
    archive: zipfile.ZipFile,
    manifest: CharacterPackManifest,
) -> None:
    names = set(archive.namelist())
    if manifest.style_file not in names:
        raise ValueError(f'style_file "{manifest.style_file}" not found')

    for state, relative_path in manifest.avatar.images.items():
        if relative_path not in names:
            raise ValueError(f'Image file for state "{state}" not found: {relative_path}')


def _collect_image_entries(
    pack_dir: Path,
    manifest: CharacterPackManifest,
) -> list[tuple[str, Path, str]]:
    entries: list[tuple[str, Path, str]] = []
    used_archive_names: set[str] = set()
    for index, (state, relative_path) in enumerate(manifest.avatar.images.items(), start=1):
        source_path = pack_dir / relative_path
        if not source_path.is_file():
            continue
        archive_name = f"images/{state}{source_path.suffix.lower()}"
        if archive_name in used_archive_names:
            archive_name = f"images/{state}_{index}{source_path.suffix.lower()}"
        used_archive_names.add(archive_name)
        entries.append((state, source_path, archive_name))
    return entries


def _validate_manifest_relative_path(
    relative_path: str,
    *,
    required_suffix: set[str] | None,
) -> str:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts or "\\" in relative_path:
        raise ValueError(f"Unsafe manifest path: {relative_path}")
    suffix = path.suffix.lower()
    if required_suffix is not None and suffix not in required_suffix:
        raise ValueError(f"Unsupported image extension: {suffix}")
    return suffix


def _validate_character_id(character_id: str) -> None:
    if not _SAFE_CHARACTER_ID.fullmatch(character_id):
        raise ValueError(
            "Character id may only contain ASCII letters, numbers, '_' and '-'."
        )


def _character_id_key(character_id: str | None) -> str:
    return str(character_id or "").casefold()


def _with_charpack_suffix(path: Path) -> Path:
    if path.suffix.lower() == CHARPACK_EXTENSION:
        return path
    return path.with_suffix(CHARPACK_EXTENSION)


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return (info.external_attr >> 16) & 0o170000 == 0o120000
