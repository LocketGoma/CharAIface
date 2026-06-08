import json
from pathlib import Path, PurePosixPath

from desktop.characters.character_pack import CharacterPack
from shared.schema.character import CharacterPackManifest


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".apng",
}


class CharacterPackScanResult:
    def __init__(
        self,
        valid_packs: list[CharacterPack],
        invalid_packs: list[dict],
    ) -> None:
        self.valid_packs = valid_packs
        self.invalid_packs = invalid_packs


class CharacterPackScanner:
    def __init__(self, characters_dir: str | Path) -> None:
        self.characters_dir = Path(characters_dir)

    def scan(self) -> CharacterPackScanResult:
        valid_packs: list[CharacterPack] = []
        invalid_packs: list[dict] = []
        seen_ids: set[str] = set()

        self.characters_dir.mkdir(parents=True, exist_ok=True)

        for pack_dir in self._iter_candidate_pack_dirs():
            try:
                pack = self._load_pack(pack_dir)

                pack_key = _character_id_key(pack.id)
                if pack_key in seen_ids:
                    invalid_packs.append(
                        {
                            "folder": pack_dir.name,
                            "path": str(pack_dir),
                            "messages": [
                                f'Duplicate character id "{pack.id}". '
                                "Character id matching is case-insensitive."
                            ],
                        }
                    )
                    continue

                seen_ids.add(pack_key)
                valid_packs.append(pack)

            except Exception as error:
                invalid_packs.append(
                    {
                        "folder": pack_dir.name,
                        "path": str(pack_dir),
                        "messages": [str(error)],
                    }
                )

        valid_packs.sort(key=lambda pack: pack.name.casefold())

        return CharacterPackScanResult(
            valid_packs=valid_packs,
            invalid_packs=invalid_packs,
        )

    def _iter_candidate_pack_dirs(self) -> list[Path]:
        """Return character pack folders under the configured scan root.

        The normal layout is one folder per pack, for example:
        resources/character/my_character/manifest.json

        For convenience during manual testing, the scan root itself is also
        accepted as a character pack when it directly contains manifest.json.
        This keeps resources/character usable both as a pack collection folder
        and as a temporary single-pack drop target.
        """
        candidate_dirs: list[Path] = []

        if (self.characters_dir / "manifest.json").is_file():
            candidate_dirs.append(self.characters_dir)

        for pack_dir in sorted(self.characters_dir.iterdir()):
            if not pack_dir.is_dir():
                continue
            if pack_dir.name.startswith("."):
                continue
            if not (pack_dir / "manifest.json").is_file():
                continue
            candidate_dirs.append(pack_dir)

        return candidate_dirs

    def _load_pack(self, pack_dir: Path) -> CharacterPack:
        manifest_path = pack_dir / "manifest.json"

        if not manifest_path.exists():
            raise ValueError("manifest.json not found")

        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = CharacterPackManifest(**manifest_data)

        if manifest.avatar.type != "image":
            raise ValueError(
                f'Unsupported avatar type "{manifest.avatar.type}". '
                "Only image avatar is supported for now."
            )

        style_path = self._pack_file_path(pack_dir, manifest.style_file)

        if not style_path.exists():
            raise ValueError(f'style_file "{manifest.style_file}" not found')

        if "idle" not in manifest.avatar.images:
            raise ValueError("avatar.images.idle is required")

        warnings: list[str] = []
        resolved_images: dict[str, Path] = {}

        for state, relative_path in manifest.avatar.images.items():
            image_path = self._pack_file_path(pack_dir, relative_path)
            suffix = image_path.suffix.lower()

            if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
                warnings.append(
                    f'Unsupported image extension for state "{state}": {suffix}'
                )
                continue

            if not image_path.exists():
                warnings.append(
                    f'Image file for state "{state}" not found: {relative_path}'
                )
                continue

            resolved_images[state] = image_path

        if "idle" not in resolved_images:
            raise ValueError("idle image file not found")

        style_prompt = style_path.read_text(encoding="utf-8")

        return CharacterPack(
            id=manifest.id,
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            author=manifest.author,
            root_dir=pack_dir,
            style_path=style_path,
            style_prompt=style_prompt,
            style_strength=manifest.style_strength,
            avatar_type=manifest.avatar.type,
            avatar_images=resolved_images,
            theme=manifest.theme,
            warnings=warnings,
        )

    def _pack_file_path(self, pack_dir: Path, relative_path: str) -> Path:
        path_text = str(relative_path or "")
        path = PurePosixPath(path_text)
        if path.is_absolute() or ".." in path.parts or "\\" in path_text:
            raise ValueError(f"Unsafe manifest path: {relative_path}")
        return pack_dir / Path(*path.parts)


def _character_id_key(character_id: str | None) -> str:
    return str(character_id or "").casefold()
