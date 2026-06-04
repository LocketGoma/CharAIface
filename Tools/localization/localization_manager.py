from __future__ import annotations

import csv
from pathlib import Path


class LocalizationManager:
    def __init__(
        self,
        csv_path: str | Path,
        default_language: str = "ko",
        fallback_language: str = "en",
    ) -> None:
        self.csv_path = Path(csv_path)
        self.current_language = default_language
        self.fallback_language = fallback_language
        self._table: dict[str, dict[str, str]] = {}
        self.load()

    def load(self) -> None:
        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if not reader.fieldnames or "key" not in reader.fieldnames:
                raise ValueError("Localization CSV must contain a key column.")

            languages = [field for field in reader.fieldnames if field != "key"]
            table: dict[str, dict[str, str]] = {}
            for row in reader:
                key = (row.get("key") or "").strip()
                if not key:
                    continue
                table[key] = {
                    language: (row.get(language) or "").strip()
                    for language in languages
                }
            self._table = table

    def t(self, key: str) -> str:
        row = self._table.get(key)
        if row is None:
            return f"{{{key}}}"

        text = row.get(self.current_language) or row.get(self.fallback_language) or ""
        return text or f"{{{key}}}"
