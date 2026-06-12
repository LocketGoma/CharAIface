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
        self._available_languages: list[str] = []

        self.load()

    @property
    def available_languages(self) -> list[str]:
        return self._available_languages.copy()

    def load(self) -> None:
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Localization CSV not found: {self.csv_path}")

        with self.csv_path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            if not reader.fieldnames or "key" not in reader.fieldnames:
                raise ValueError("Localization CSV must contain 'key' column.")

            self._available_languages = [
                field_name
                for field_name in reader.fieldnames
                if field_name and field_name != "key"
            ]

            table: dict[str, dict[str, str]] = {}

            for row in reader:
                key = (row.get("key") or "").strip()

                if not key:
                    continue

                table[key] = {
                    language: (row.get(language) or "").strip()
                    for language in self._available_languages
                }

            self._table = table

    def set_language(self, language: str) -> None:
        if language not in self._available_languages:
            raise ValueError(f"Unsupported language: {language}")

        self.current_language = language

    def t_for_language(self, language: str, key: str, **kwargs) -> str:
        row = self._table.get(key)

        if row is None:
            return f"{{{key}}}"

        text = row.get(language) or ""
        if not text:
            text = row.get(self.fallback_language) or ""

        if not text:
            return f"{{{key}}}"

        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text

        return text

    def t(self, key: str, **kwargs) -> str:
        return self.t_for_language(self.current_language, key, **kwargs)

    def t_mode(self, key: str, developer_mode: bool = False, **kwargs) -> str:
        if developer_mode:
            dev_key = f"{key}.dev"
            dev_text = self.t(dev_key, **kwargs)

            if dev_text != f"{{{dev_key}}}":
                return dev_text

        return self.t(key, **kwargs)
