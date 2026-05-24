import csv
from pathlib import Path


BUILTIN_TRANSLATIONS: dict[str, dict[str, str]] = {
    "app.title": {
        "ko": "CharAIface",
        "en": "CharAIface",
    },
    "chat.backend_fallback": {
        "ko": "백엔드 응답을 가져오지 못했습니다. 임시 로컬 응답입니다.",
        "en": "Could not get a backend response. This is a temporary local response.",
    },
    "chat.initial_notice.model_required": {
        "ko": "안내 : 안녕하세요! {app_name}의 {character_name} 입니다! 사용을 위해서는 로컬 AI 모델 설치가 필요합니다. 가이드를 따라주세요",
        "en": "Notice: Hello! I'm {character_name} from {app_name}! To use the app, a local AI model must be installed. Please follow the guide.",
    },
    "chat.initial_notice.new_session": {
        "ko": "안내 : 안녕하세요. {app_name}의 {character_name} 입니다! 새로운 세션이 확인되었습니다.",
        "en": "Notice: Hello. I'm {character_name} from {app_name}! A new session has been detected.",
    },
}


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

            for key, translations in BUILTIN_TRANSLATIONS.items():
                if key not in table:
                    table[key] = {}

                for language, value in translations.items():
                    if language not in self._available_languages:
                        continue

                    if not table[key].get(language):
                        table[key][language] = value

            self._table = table

    def set_language(self, language: str) -> None:
        if language not in self._available_languages:
            raise ValueError(f"Unsupported language: {language}")

        self.current_language = language

    def t(self, key: str, **kwargs) -> str:
        row = self._table.get(key)

        if row is None:
            return f"{{{key}}}"

        text = row.get(self.current_language) or ""
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

    def t_mode(self, key: str, developer_mode: bool = False, **kwargs) -> str:
        if developer_mode:
            dev_key = f"{key}.dev"
            dev_text = self.t(dev_key, **kwargs)

            if dev_text != f"{{{dev_key}}}":
                return dev_text

        return self.t(key, **kwargs)