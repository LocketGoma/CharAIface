from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


CHARPACK_EXTENSION = ".charpack"
CHARPACK_FORMAT = "charaiface.character_pack"
CHARPACK_FORMAT_VERSION = 1
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".apng"}
MAX_ARCHIVE_FILES = 64
MAX_EXTRACTED_BYTES = 128 * 1024 * 1024

_SAFE_CHARACTER_ID = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class ReactionImage:
    path: Path
    reaction: str = "idle"


@dataclass
class CharacterPackDraft:
    character_id: str
    name: str
    version: str
    author: str
    description: str
    style_prompt: str
    images: list[ReactionImage]
    short_style_prompt: str = ""
    theme_base: str = "light"
    palette_override: dict[str, str] | None = None


def write_charpack(target: Path, draft: CharacterPackDraft) -> None:
    image_paths: dict[str, str] = {}
    used_names: set[str] = set()
    target = _with_charpack_suffix(target)
    _validate_draft(draft)
    target.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, image in enumerate(draft.images, start=1):
            suffix = image.path.suffix.lower()
            base_name = f"{image.reaction}{suffix}"
            archive_name = f"images/{base_name}"
            if archive_name in used_names:
                archive_name = f"images/{image.reaction}_{index}{suffix}"
            used_names.add(archive_name)
            archive.write(image.path, archive_name)
            image_paths.setdefault(image.reaction, archive_name)

        manifest = {
            "format": CHARPACK_FORMAT,
            "format_version": CHARPACK_FORMAT_VERSION,
            "id": draft.character_id or "example_character",
            "name": draft.name or "Example Character",
            "version": draft.version or "1.0.0",
            "description": draft.description,
            "author": draft.author,
            "style_file": "style.md",
            "style_strength": 0.5,
            "avatar": {
                "type": "image",
                "images": image_paths,
            },
            "theme": {
                "base_theme": draft.theme_base,
                "palette_override": draft.palette_override or {},
            },
        }

        archive.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2),
        )
        archive.writestr("style.md", draft.style_prompt)
        if draft.short_style_prompt.strip():
            archive.writestr("style.short.md", draft.short_style_prompt)


def load_charpack(source: Path, workspace_dir: Path) -> CharacterPackDraft:
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp_dir = Path(tmp_name)
        with zipfile.ZipFile(source, "r") as archive:
            _validate_archive_entries(archive)
            manifest_data = json.loads(archive.read("manifest.json").decode("utf-8"))
            _validate_manifest(manifest_data)
            _validate_archive_manifest_files(archive, manifest_data)
            archive.extractall(tmp_dir)

        extracted_dir = Path(tempfile.mkdtemp(prefix="opened_", dir=workspace_dir))
        for child in tmp_dir.iterdir():
            target = extracted_dir / child.name
            if child.is_dir():
                shutil.copytree(child, target)
            else:
                shutil.copy2(child, target)

    style_file = manifest_data.get("style_file", "style.md")
    style_path = extracted_dir / style_file
    style_prompt = style_path.read_text(encoding="utf-8") if style_path.exists() else ""
    short_style_path = extracted_dir / "style.short.md"
    short_style_prompt = (
        short_style_path.read_text(encoding="utf-8")
        if short_style_path.exists()
        else ""
    )

    images: list[ReactionImage] = []
    avatar = manifest_data.get("avatar", {})
    for reaction, relative_path in avatar.get("images", {}).items():
        image_path = extracted_dir / relative_path
        if image_path.exists():
            images.append(ReactionImage(path=image_path, reaction=reaction))

    theme = manifest_data.get("theme") or {}

    return CharacterPackDraft(
        character_id=manifest_data.get("id", "example_character"),
        name=manifest_data.get("name", "Example Character"),
        version=manifest_data.get("version", "1.0.0"),
        author=manifest_data.get("author", ""),
        description=manifest_data.get("description", ""),
        style_prompt=style_prompt,
        images=images,
        short_style_prompt=short_style_prompt,
        theme_base=theme.get("base_theme", "light"),
        palette_override=theme.get("palette_override", {}),
    )


def _validate_archive_entries(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_FILES:
        raise ValueError("Character pack archive contains too many files")

    names = {info.filename for info in infos}
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


def _validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("format") != CHARPACK_FORMAT:
        raise ValueError("Unsupported character pack format")
    if manifest.get("format_version") != CHARPACK_FORMAT_VERSION:
        raise ValueError("Unsupported character pack format_version")

    character_id = str(manifest.get("id") or "")
    _validate_character_id(character_id)

    avatar = manifest.get("avatar") or {}
    if avatar.get("type") != "image":
        raise ValueError("Only image avatar is supported for now.")

    images = avatar.get("images") or {}
    if "idle" not in images:
        raise ValueError("avatar.images.idle is required")

    _validate_manifest_relative_path(str(manifest.get("style_file") or "style.md"))
    for relative_path in images.values():
        suffix = _validate_manifest_relative_path(str(relative_path))
        if suffix not in SUPPORTED_IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported image extension: {suffix}")


def _validate_draft(draft: CharacterPackDraft) -> None:
    _validate_character_id(draft.character_id or "example_character")
    if "idle" not in {image.reaction for image in draft.images}:
        raise ValueError("avatar.images.idle is required")

    for image in draft.images:
        if image.path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported image extension: {image.path.suffix}")
        if not image.path.is_file():
            raise ValueError(f"Image file not found: {image.path}")
        _validate_manifest_relative_path(f"images/{image.reaction}{image.path.suffix.lower()}")


def _validate_archive_manifest_files(
    archive: zipfile.ZipFile,
    manifest: dict[str, Any],
) -> None:
    names = set(archive.namelist())
    style_file = str(manifest.get("style_file") or "style.md")
    if style_file not in names:
        raise ValueError(f'style_file "{style_file}" not found')

    avatar = manifest.get("avatar") or {}
    for state, relative_path in (avatar.get("images") or {}).items():
        if relative_path not in names:
            raise ValueError(f'Image file for state "{state}" not found: {relative_path}')


def _validate_manifest_relative_path(relative_path: str) -> str:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts or "\\" in relative_path:
        raise ValueError(f"Unsafe manifest path: {relative_path}")
    return path.suffix.lower()


def _validate_character_id(character_id: str) -> None:
    if not _SAFE_CHARACTER_ID.fullmatch(character_id):
        raise ValueError(
            "Character id may only contain ASCII letters, numbers, '_' and '-'."
        )


def _with_charpack_suffix(path: Path) -> Path:
    if path.suffix.lower() == CHARPACK_EXTENSION:
        return path
    return path.with_suffix(CHARPACK_EXTENSION)


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return (info.external_attr >> 16) & 0o170000 == 0o120000
