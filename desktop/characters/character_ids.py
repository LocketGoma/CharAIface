from __future__ import annotations


def character_id_key(character_id: str | None) -> str:
    return str(character_id or "").casefold()


def character_ids_equal(left: str | None, right: str | None) -> bool:
    return character_id_key(left) == character_id_key(right)
