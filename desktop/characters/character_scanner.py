import json
from pathlib import Path

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

        for pack_dir in sorted(self.characters_dir.iterdir()):
            if not pack_dir.is_dir():
                continue

            try:
                pack = self._load_pack(pack_dir)

                if pack.id in seen_ids:
                    invalid_packs.append(
                        {
                            "folder": pack_dir.name,
                            "path": str(pack_dir),
                            "messages": [
                                f'Duplicate character id "{pack.id}". Character id must be unique.'
                            ],
                        }
                    )
                    continue

                seen_ids.add(pack.id)
                valid_packs.append(pack)

            except Exception as error:
                invalid_packs.append(
                    {
                        "folder": pack_dir.name,
                        "path": str(pack_dir),
                        "messages": [str(error)],
                    }
                )

        valid_packs.sort(key=lambda pack: pack.name.lower())

        return CharacterPackScanResult(
            valid_packs=valid_packs,
            invalid_packs=invalid_packs,
        )

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

        style_path = pack_dir / manifest.style_file

        if not style_path.exists():
            raise ValueError(f'style_file "{manifest.style_file}" not found')

        if "idle" not in manifest.avatar.images:
            raise ValueError("avatar.images.idle is required")

        warnings: list[str] = []
        resolved_images: dict[str, Path] = {}

        for state, relative_path in manifest.avatar.images.items():
            image_path = pack_dir / relative_path
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