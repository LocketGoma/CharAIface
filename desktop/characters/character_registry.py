from pathlib import Path

from desktop.characters.character_pack import CharacterPack
from desktop.characters.character_scanner import CharacterPackScanner


class CharacterRegistry:
    def __init__(
        self,
        builtin_characters_dir: str | Path,
        user_characters_dir: str | Path,
    ) -> None:
        self.builtin_characters_dir = Path(builtin_characters_dir)
        self.user_characters_dir = Path(user_characters_dir)

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
        return self._packs.get(character_id)

    def get_default_pack(self) -> CharacterPack | None:
        if not self._packs:
            return None

        if "default_sakura" in self._packs:
            return self._packs["default_sakura"]

        builtin_packs = [
            pack
            for pack in self._packs.values()
            if pack.id in self._builtin_pack_ids
        ]

        if builtin_packs:
            return sorted(builtin_packs, key=lambda pack: pack.name.lower())[0]

        return sorted(self._packs.values(), key=lambda pack: pack.name.lower())[0]

    def is_builtin(self, character_id: str) -> bool:
        return character_id in self._builtin_pack_ids

    def is_user_pack(self, character_id: str) -> bool:
        return character_id in self._user_pack_ids

    def _load_builtin_characters(self) -> None:
        scanner = CharacterPackScanner(characters_dir=self.builtin_characters_dir)
        result = scanner.scan()

        self._invalid_packs.extend(
            self._with_source(result.invalid_packs, source="builtin")
        )

        for pack in result.valid_packs:
            self._register_pack(pack=pack, source="builtin")

    def _load_user_characters(self) -> None:
        scanner = CharacterPackScanner(characters_dir=self.user_characters_dir)
        result = scanner.scan()

        self._invalid_packs.extend(
            self._with_source(result.invalid_packs, source="user")
        )

        for pack in result.valid_packs:
            self._register_pack(pack=pack, source="user")

    def _register_pack(self, pack: CharacterPack, source: str) -> None:
        if pack.id in self._packs:
            self._invalid_packs.append(
                {
                    "source": source,
                    "folder": pack.root_dir.name,
                    "path": str(pack.root_dir),
                    "messages": [
                        f'Duplicate character id "{pack.id}". '
                        "User character packs cannot override built-in character packs."
                    ],
                }
            )
            return

        self._packs[pack.id] = pack

        if source == "builtin":
            self._builtin_pack_ids.add(pack.id)
        elif source == "user":
            self._user_pack_ids.add(pack.id)

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