from __future__ import annotations

from pathlib import Path


TABLE_SUFFIXES = {".csv", ".tsv"}
SPREADSHEET_SUFFIXES = {".xlsx"}
TABLE_LIKE_SUFFIXES = TABLE_SUFFIXES | SPREADSHEET_SUFFIXES
JSON_SUFFIXES = {".json"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
TEXT_SUFFIXES = {".txt", ".log"}
CONFIG_SUFFIXES = {
    ".cfg",
    ".conf",
    ".ini",
    ".plist",
    ".properties",
    ".toml",
    ".xml",
    ".yaml",
    ".yml",
}
SOURCE_CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cs",
    ".css",
    ".cxx",
    ".go",
    ".h",
    ".hh",
    ".hpp",
    ".htm",
    ".html",
    ".hxx",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".kts",
    ".m",
    ".mm",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".ts",
    ".tsx",
    ".vue",
}
SUPPORTED_TEXT_FILE_SUFFIXES = (
    TABLE_SUFFIXES
    | JSON_SUFFIXES
    | MARKDOWN_SUFFIXES
    | TEXT_SUFFIXES
    | CONFIG_SUFFIXES
    | SOURCE_CODE_SUFFIXES
)
SUPPORTED_FILE_SUFFIXES = SUPPORTED_TEXT_FILE_SUFFIXES | SPREADSHEET_SUFFIXES

FILE_KIND_DISPLAY_LABELS = {
    "table": "Table/spreadsheet",
    "json": "JSON data",
    "markdown": "Markdown document",
    "source_code": "Source code",
    "text": "Text/document",
}


def normalized_suffix(name_or_suffix: str | Path) -> str:
    value = str(name_or_suffix or "").strip()
    if not value:
        return ""
    if value.startswith(".") and "/" not in value and "\\" not in value:
        return value.lower()
    return Path(value).suffix.lower()


def file_kind_for_suffix(suffix: str) -> str:
    suffix = normalized_suffix(suffix)
    if suffix in TABLE_LIKE_SUFFIXES:
        return "table"
    if suffix in JSON_SUFFIXES:
        return "json"
    if suffix in MARKDOWN_SUFFIXES:
        return "markdown"
    if suffix in CONFIG_SUFFIXES:
        return "text"
    if suffix in SOURCE_CODE_SUFFIXES:
        return "source_code"
    return "text"


def file_kind_display_label(name_or_suffix: str | Path) -> str:
    return FILE_KIND_DISPLAY_LABELS.get(
        file_kind_for_suffix(normalized_suffix(name_or_suffix)),
        "Text/document",
    )


def file_type_label(name_or_suffix: str | Path) -> str:
    suffix = normalized_suffix(name_or_suffix)
    if suffix in SPREADSHEET_SUFFIXES:
        return f"{suffix.lstrip('.').upper()} spreadsheet"
    if suffix in TABLE_SUFFIXES:
        return f"{suffix.lstrip('.').upper()} table"
    if suffix in JSON_SUFFIXES:
        return "JSON data"
    if suffix in MARKDOWN_SUFFIXES:
        return "Markdown document"
    if suffix in CONFIG_SUFFIXES:
        return "Config/document"
    if suffix in SOURCE_CODE_SUFFIXES:
        return f"{suffix.lstrip('.').upper()} source/config"
    if suffix in TEXT_SUFFIXES:
        return "Text document"
    return f"{suffix.lstrip('.').upper()} text" if suffix else "Text file"


def file_dialog_filter() -> str:
    return ";;".join(
        [
            "Documents (*.txt *.md *.json *.ini *.yml)",
            "Tables (*.csv *.tsv *.xlsx)",
            "Code files (*.c *.cpp *.h *.hpp *.py)",
            "All files (*)",
        ]
    )


def supported_file_types_description() -> str:
    return (
        "Documents (*.txt, *.md, *.json, *.ini, *.yml), "
        "tables (*.csv, *.tsv, *.xlsx), and source code "
        "(*.c, *.cpp, *.h, *.hpp, *.py and more)"
    )


def format_file_size(size_bytes: int) -> str:
    size = max(0, int(size_bytes))
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"
