from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


CHARPACK_FORMAT = "charaiface.character_pack"
CHARPACK_FORMAT_VERSION = 1
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".apng"}


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
    theme_base: str = "light"
    palette_override: dict[str, str] | None = None


def write_charpack(target: Path, draft: CharacterPackDraft) -> None:
    image_paths: dict[str, str] = {}
    used_names: set[str] = set()

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


def load_charpack(source: Path, workspace_dir: Path) -> CharacterPackDraft:
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp_dir = Path(tmp_name)
        with zipfile.ZipFile(source, "r") as archive:
            _validate_archive_names(archive)
            manifest_data = json.loads(archive.read("manifest.json").decode("utf-8"))
            _validate_manifest(manifest_data)
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
        theme_base=theme.get("base_theme", "light"),
        palette_override=theme.get("palette_override", {}),
    )


def _validate_archive_names(archive: zipfile.ZipFile) -> None:
    names = archive.namelist()
    if "manifest.json" not in names:
        raise ValueError("manifest.json not found")

    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"Unsafe archive path: {name}")


def _validate_manifest(manifest: dict) -> None:
    if manifest.get("format") != CHARPACK_FORMAT:
        raise ValueError("Unsupported character pack format")
    if manifest.get("format_version") != CHARPACK_FORMAT_VERSION:
        raise ValueError("Unsupported character pack format_version")
