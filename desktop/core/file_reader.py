from dataclasses import dataclass
from pathlib import Path


MAX_FILE_BYTES = 1024 * 1024
TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "utf-16", "cp949")
UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
ALLOWED_CONTROL_CHARS = {"\n", "\r", "\t", "\f"}
SOURCE_CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cfg",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".htm",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".kts",
    ".m",
    ".mm",
    ".php",
    ".plist",
    ".properties",
    ".py",
    ".rb",
    ".rs",
    ".sh",
    ".sql",
    ".swift",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
}


class FileReadError(Exception):
    pass


@dataclass(frozen=True)
class FileReadResult:
    path: Path
    name: str
    suffix: str
    summary: str
    truncated: bool = False


def read_file_for_chat(path: str | Path) -> FileReadResult:
    file_path = Path(path).expanduser().resolve()
    suffix = file_path.suffix.lower()

    if not file_path.exists():
        raise FileReadError(f"File does not exist: {file_path}")
    if not file_path.is_file():
        raise FileReadError(f"Path is not a file: {file_path}")

    if suffix == ".csv":
        summary, truncated = _read_csv_summary(file_path)
    else:
        summary, truncated = _read_text_summary(file_path)

    return FileReadResult(
        path=file_path,
        name=file_path.name,
        suffix=suffix,
        summary=summary,
        truncated=truncated,
    )


def build_file_context_message(result: FileReadResult) -> str:
    truncated_note = "\n\n[Note: File content was truncated for chat context.]" if result.truncated else ""
    tag = _content_tag_for_suffix(result.suffix)
    return (
        "Attached file metadata:\n"
        f"- name: {result.name}\n"
        f"- type: {result.suffix or '(none)'}\n\n"
        "Actual attached file content:\n"
        f"<{tag} filename=\"{result.name}\">\n"
        f"{result.summary}"
        f"\n</{tag}>"
        f"{truncated_note}"
    )


def _read_text_summary(path: Path) -> tuple[str, bool]:
    try:
        raw_content = _read_limited_bytes(path)
        truncated = _is_larger_than_limit(path)
        content = _decode_text_content(raw_content, truncated, path.name)
    except OSError as error:
        raise FileReadError(f"Could not read file: {path.name}") from error

    _raise_if_binary_text(content, path.name, truncated=truncated)
    return content, truncated


def _read_csv_summary(path: Path) -> tuple[str, bool]:
    try:
        raw_content = _read_limited_bytes(path)
        truncated = _is_larger_than_limit(path)
        content = _decode_text_content(raw_content, truncated, path.name)
    except OSError as error:
        raise FileReadError(f"Could not read file: {path.name}") from error

    _raise_if_binary_text(content, path.name, truncated=truncated)
    return content, truncated


def _read_limited_bytes(path: Path) -> bytes:
    with path.open("rb") as file:
        return file.read(MAX_FILE_BYTES)


def _is_larger_than_limit(path: Path) -> bool:
    try:
        return path.stat().st_size > MAX_FILE_BYTES
    except OSError:
        return False


def _content_tag_for_suffix(suffix: str) -> str:
    if suffix == ".csv":
        return "CSV"
    if suffix == ".md":
        return "MARKDOWN"
    if suffix in SOURCE_CODE_SUFFIXES:
        return "CODE"
    return "TEXT"


def _decode_text_content(raw_content: bytes, truncated: bool, name: str) -> str:
    if _has_binary_null_bytes(raw_content):
        raise FileReadError(f"File appears to be binary: {name}")

    decode_errors = "replace" if truncated else "strict"
    last_error: UnicodeDecodeError | None = None
    for encoding in TEXT_ENCODINGS:
        try:
            return raw_content.decode(encoding, errors=decode_errors)
        except UnicodeDecodeError as error:
            last_error = error

    raise FileReadError(f"Could not read file as text: {name}") from last_error


def _has_binary_null_bytes(raw_content: bytes) -> bool:
    if raw_content.startswith(UTF16_BOMS):
        return False
    return b"\x00" in raw_content


def _raise_if_binary_text(content: str, name: str, *, truncated: bool) -> None:
    if not content:
        return

    control_count = sum(
        1
        for character in content
        if ord(character) < 32 and character not in ALLOWED_CONTROL_CHARS
    )
    replacement_count = content.count("\ufffd")
    if truncated:
        replacement_count = max(0, replacement_count - 1)
    binary_signal_count = control_count + replacement_count
    if binary_signal_count / len(content) > 0.05:
        raise FileReadError(f"File appears to be binary: {name}")
