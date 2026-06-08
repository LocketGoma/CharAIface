from pathlib import Path

from desktop.characters.character_pack import CharacterPack
from desktop.characters.character_scanner import CharacterPackScanner


DEFAULT_CHARACTER_ID = "default_sakura"


class CharacterRegistry:
    def __init__(
        self,
        builtin_characters_dir: str | Path,
        user_characters_dir: str | Path,
        additional_user_characters_dirs: list[str | Path] | None = None,
    ) -> None:
        self.builtin_characters_dir = Path(builtin_characters_dir)
        self.user_characters_dir = Path(user_characters_dir)
        self.additional_user_characters_dirs = [
            Path(path)
            for path in (additional_user_characters_dirs or [])
        ]

        self._packs: dict[str, CharacterPack] = {}
        self._builtin_pack_ids: set[str] = set()
        self._user_pack_ids: set[str] = set()
        self._invalid_packs: list[dict] = []
        self._warnings: list[str] = []

    @property
    def packs(self) -> list[CharacterPack]:
        return list(self._packs.values())

    @property
    def invalid_packs(self) -> list[dict]:
        return self._invalid_packs.copy()

    @property
    def warnings(self) -> list[str]:
        return self._warnings.copy()

    def load(self) -> None:
        self._packs.clear()
        self._builtin_pack_ids.clear()
        self._user_pack_ids.clear()
        self._invalid_packs.clear()
        self._warnings.clear()

        self._load_builtin_characters()
        self._load_user_characters()

    def get_pack(self, character_id: str) -> CharacterPack | None:
        return self._packs.get(_character_id_key(character_id))

    def get_default_pack(self) -> CharacterPack | None:
        if not self._packs:
            return None

        default_key = _character_id_key(DEFAULT_CHARACTER_ID)
        if default_key in self._packs:
            return self._packs[default_key]

        builtin_packs = [
            pack
            for pack in self._packs.values()
            if _character_id_key(pack.id) in self._builtin_pack_ids
        ]

        if builtin_packs:
            return sorted(builtin_packs, key=lambda pack: pack.name.casefold())[0]

        return sorted(self._packs.values(), key=lambda pack: pack.name.casefold())[0]

    def is_builtin(self, character_id: str) -> bool:
        return _character_id_key(character_id) in self._builtin_pack_ids

    def is_user_pack(self, character_id: str) -> bool:
        return _character_id_key(character_id) in self._user_pack_ids

    def _load_builtin_characters(self) -> None:
        scanner = CharacterPackScanner(characters_dir=self.builtin_characters_dir)
        result = scanner.scan()

        self._invalid_packs.extend(
            self._with_source(result.invalid_packs, source="builtin")
        )

        for pack in result.valid_packs:
            self._register_pack(pack=pack, source="builtin")

    def _load_user_characters(self) -> None:
        self._scan_user_character_dir(
            characters_dir=self.user_characters_dir,
            source="user",
            create_if_missing=True,
        )

        seen_dirs = {self.user_characters_dir.resolve()}
        for characters_dir in self.additional_user_characters_dirs:
            try:
                resolved_dir = characters_dir.resolve()
            except Exception:
                resolved_dir = characters_dir

            if resolved_dir in seen_dirs:
                continue

            seen_dirs.add(resolved_dir)
            self._scan_user_character_dir(
                characters_dir=characters_dir,
                source="user",
                create_if_missing=False,
            )

    def _scan_user_character_dir(
        self,
        characters_dir: Path,
        source: str,
        create_if_missing: bool,
    ) -> None:
        if not create_if_missing and not characters_dir.exists():
            return

        scanner = CharacterPackScanner(characters_dir=characters_dir)
        result = scanner.scan()

        self._invalid_packs.extend(
            self._with_source(result.invalid_packs, source=source)
        )

        for pack in result.valid_packs:
            self._register_pack(pack=pack, source=source)

    def _register_pack(self, pack: CharacterPack, source: str) -> None:
        pack_key = _character_id_key(pack.id)
        if pack_key in self._packs:
            existing_pack = self._packs[pack_key]
            self._invalid_packs.append(
                {
                    "source": source,
                    "folder": pack.root_dir.name,
                    "path": str(pack.root_dir),
                    "messages": [
                        f'Duplicate character id "{pack.id}". '
                        f'Already registered as "{existing_pack.id}". '
                        "Character id matching is case-insensitive."
                    ],
                }
            )
            return

        self._packs[pack_key] = pack

        if source == "builtin":
            self._builtin_pack_ids.add(pack_key)
        elif source == "user":
            self._user_pack_ids.add(pack_key)

        for warning in pack.warnings:
            self._warnings.append(
                f"[{source}] {pack.id}: {warning}"
            )

    def _with_source(self, invalid_packs: list[dict], source: str) -> list[dict]:
        result: list[dict] = []

        for invalid_pack in invalid_packs:
            copied = dict(invalid_pack)
            copied["source"] = source
            result.append(copied)

        return result


def _character_id_key(character_id: str | None) -> str:
    return str(character_id or "").casefold()
