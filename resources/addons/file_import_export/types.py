from __future__ import annotations

from pathlib import Path

from resources.addons.file_import_export import (
    CONFIG_SUFFIXES,
    JSON_SUFFIXES,
    MARKDOWN_SUFFIXES,
    SOURCE_CODE_SUFFIXES,
    SPREADSHEET_SUFFIXES,
    SUPPORTED_EXPORT_SUFFIXES,
    SUPPORTED_FILE_SUFFIXES,
    SUPPORTED_TEXT_FILE_SUFFIXES,
    TABLE_LIKE_SUFFIXES,
    TABLE_SUFFIXES,
    TEXT_SUFFIXES,
    export_filter,
    export_suffixes,
    file_dialog_filter,
    supported_file_types_description,
)


def default_export_suffixes(settings_snapshot=None) -> set[str]:
    try:
        return set(export_suffixes(settings_snapshot))
    except TypeError:
        return set(export_suffixes())

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
