from dataclasses import dataclass
import csv
from io import StringIO
from pathlib import Path


MAX_FILE_BYTES = 1024 * 1024
MIN_INLINE_CSV_ROWS = 2
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
    model_context: str = ""
    truncated: bool = False


def read_file_for_chat(path: str | Path) -> FileReadResult:
    file_path = Path(path).expanduser().resolve()
    suffix = file_path.suffix.lower()

    if not file_path.exists():
        raise FileReadError(f"File does not exist: {file_path}")
    if not file_path.is_file():
        raise FileReadError(f"Path is not a file: {file_path}")

    if suffix == ".csv":
        summary, model_context, truncated = _read_csv_summary(file_path)
    else:
        summary, truncated = _read_text_summary(file_path)
        model_context = ""

    return FileReadResult(
        path=file_path,
        name=file_path.name,
        suffix=suffix,
        summary=summary,
        model_context=model_context,
        truncated=truncated,
    )


def build_file_context_message(result: FileReadResult) -> str:
    truncated_note = "\n\n[Note: File content was truncated for chat context.]" if result.truncated else ""
    tag = _content_tag_for_suffix(result.suffix)
    metadata = (
        "Attached file metadata:\n"
        f"- name: {result.name}\n"
        f"- type: {result.suffix or '(none)'}"
    )
    if result.model_context.strip():
        return (
            f"{metadata}\n\n"
            f"{result.model_context}"
            f"{truncated_note}"
        )

    return (
        f"{metadata}\n\n"
        "Actual attached file content:\n"
        f"<{tag} filename=\"{result.name}\">\n"
        f"{result.summary}"
        f"\n</{tag}>"
        f"{truncated_note}"
    )


def build_inline_csv_context_message(text: str) -> str:
    rows = _extract_csv_like_rows(text)
    if not rows:
        return ""
    return _build_csv_model_context_from_rows(rows, "inline_user_input")


def _read_text_summary(path: Path) -> tuple[str, bool]:
    try:
        raw_content = _read_limited_bytes(path)
        truncated = _is_larger_than_limit(path)
        content = _decode_text_content(raw_content, truncated, path.name)
    except OSError as error:
        raise FileReadError(f"Could not read file: {path.name}") from error

    _raise_if_binary_text(content, path.name, truncated=truncated)
    return content, truncated


def _read_csv_summary(path: Path) -> tuple[str, str, bool]:
    try:
        raw_content = _read_limited_bytes(path)
        truncated = _is_larger_than_limit(path)
        content = _decode_text_content(raw_content, truncated, path.name)
    except OSError as error:
        raise FileReadError(f"Could not read file: {path.name}") from error

    _raise_if_binary_text(content, path.name, truncated=truncated)
    return content, _build_csv_model_context(content, path.name), truncated


def _build_csv_model_context(content: str, name: str) -> str:
    rows = _parse_csv_rows(content)
    if not rows:
        return (
            "Machine-readable file/data context:\n"
            f"- parser: csv\n"
            f"- parse_status: failed\n"
            f"- filename: {name}"
        )

    return _build_csv_model_context_from_rows(rows, name)


def _build_csv_model_context_from_rows(rows: list[list[str]], name: str) -> str:
    column_count = max(len(row) for row in rows)
    has_header = _looks_like_header_row(rows[0])
    header = rows[0] if has_header else []
    data_rows = rows[1:] if has_header else rows
    normalized_header = _normalized_csv_header(header, column_count)
    normalized_rows = [_normalize_csv_row(row, column_count) for row in data_rows]
    table = _render_indexed_tsv(normalized_header, normalized_rows)
    profile = _render_csv_profile(normalized_header, normalized_rows)
    numeric_frequency_csv = _render_numeric_frequency_csv(normalized_rows)
    value_frequency_csv = _render_value_frequency_csv(normalized_header, normalized_rows)

    return (
        "Machine-readable file/data context:\n"
        "- parser: csv\n"
        "- parse_status: ok\n"
        f"- filename: {name}\n"
        f"- header_row_detected: {str(has_header).lower()}\n"
        f"- data_row_count: {len(normalized_rows)}\n"
        f"- column_count: {column_count}\n"
        f"- columns: {', '.join(normalized_header)}\n\n"
        "Parsed CSV table, tab-separated and row-indexed for exact counting:\n"
        "<PARSED_CSV_TSV>\n"
        f"{table}\n"
        "</PARSED_CSV_TSV>\n\n"
        "All cell value frequency CSV for general CSV reasoning:\n"
        "Each non-empty CSV cell is treated as a value. row_appearance_count counts how many data rows contain that value at least once.\n"
        "row_appearance_probability_percent is row_appearance_count divided by data_row_count times 100.\n"
        "If the user asks for a value's total appearances, row appearances, or row appearance probability, use ALL_CELL_VALUE_FREQUENCY_CSV directly.\n"
        "<ALL_CELL_VALUE_FREQUENCY_CSV>\n"
        f"{value_frequency_csv}\n"
        "</ALL_CELL_VALUE_FREQUENCY_CSV>\n\n"
        "Cell value frequency CSV for numeric-frequency questions:\n"
        "Treat every numeric CSV cell as one independent occurrence.\n"
        "Do not interpret rows as combinations unless the user explicitly asks for combination analysis.\n"
        "If the user asks for each number's appearance count or per-round appearance probability, use CELL_VALUE_FREQUENCY_CSV directly.\n"
        "<CELL_VALUE_FREQUENCY_CSV>\n"
        f"{numeric_frequency_csv}\n"
        "</CELL_VALUE_FREQUENCY_CSV>\n\n"
        f"{profile}"
    ).strip()


def _parse_csv_rows(content: str) -> list[list[str]]:
    try:
        parsed_rows = list(csv.reader(StringIO(content)))
    except csv.Error:
        return []
    return [
        [str(cell).strip() for cell in row]
        for row in parsed_rows
        if any(str(cell).strip() for cell in row)
    ]


def _extract_csv_like_rows(text: str) -> list[list[str]]:
    candidate_rows: list[list[str]] = []
    best_rows: list[list[str]] = []

    for line in str(text or "").splitlines():
        parsed = _parse_single_csv_like_line(line)
        if parsed is None:
            if _looks_like_csv_dataset(candidate_rows) and len(candidate_rows) > len(best_rows):
                best_rows = candidate_rows
            candidate_rows = []
            continue
        candidate_rows.append(parsed)

    if _looks_like_csv_dataset(candidate_rows) and len(candidate_rows) > len(best_rows):
        best_rows = candidate_rows

    return best_rows


def _parse_single_csv_like_line(line: str) -> list[str] | None:
    stripped = str(line or "").strip()
    if "," not in stripped:
        return None
    try:
        rows = list(csv.reader(StringIO(stripped)))
    except csv.Error:
        return None
    if len(rows) != 1:
        return None
    row = [str(cell).strip() for cell in rows[0]]
    if len(row) < 2 or not any(row):
        return None
    return row


def _looks_like_csv_dataset(rows: list[list[str]]) -> bool:
    if len(rows) < MIN_INLINE_CSV_ROWS:
        return False
    column_counts = [len(row) for row in rows]
    if min(column_counts) < 2:
        return False
    common_column_count = max(set(column_counts), key=column_counts.count)
    consistent_row_count = sum(1 for count in column_counts if count == common_column_count)
    has_consistent_shape = consistent_row_count >= max(2, int(len(rows) * 0.75))
    numeric_cell_count = sum(
        1
        for row in rows
        for cell in row
        if _is_number_like(str(cell).strip())
    )
    if numeric_cell_count >= len(rows):
        return True
    return has_consistent_shape and _looks_like_header_row(rows[0])


def _normalized_csv_header(header: list[str], column_count: int) -> list[str]:
    normalized = _normalize_csv_row(header, column_count)
    return [
        cell if cell else f"column_{index}"
        for index, cell in enumerate(normalized, start=1)
    ]


def _looks_like_header_row(row: list[str]) -> bool:
    cells = [str(cell).strip() for cell in row if str(cell).strip()]
    if not cells:
        return False
    return any(not _is_number_like(cell) for cell in cells)


def _is_number_like(value: str) -> bool:
    try:
        float(str(value).strip())
    except ValueError:
        return False
    return True


def _normalize_csv_row(row: list[str], column_count: int) -> list[str]:
    return [str(cell).strip() for cell in row[:column_count]] + [""] * max(0, column_count - len(row))


def _render_indexed_tsv(header: list[str], rows: list[list[str]]) -> str:
    lines = ["row_index\t" + "\t".join(_sanitize_tsv_cell(cell) for cell in header)]
    for index, row in enumerate(rows, start=1):
        lines.append(
            f"{index}\t"
            + "\t".join(_sanitize_tsv_cell(cell) for cell in _normalize_csv_row(row, len(header)))
        )
    return "\n".join(lines)


def _sanitize_tsv_cell(value: str) -> str:
    return str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()


def _render_csv_profile(header: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return "Parsed CSV data profile:\n- empty_data_rows: true"

    lines = [
        "Parsed CSV data profile:",
        "- This profile is deterministic preprocessing for the model, not the final answer.",
    ]
    numeric_frequency = _numeric_value_frequency(rows)
    if numeric_frequency:
        lines.append("- all_numeric_cell_value_frequency:")
        for value, count in numeric_frequency:
            lines.append(f"  - {value}: {count}")

    column_summaries = _column_value_summaries(header, rows)
    if column_summaries:
        lines.append("- per_column_value_frequency:")
        lines.extend(column_summaries)

    return "\n".join(lines)


def _render_numeric_frequency_csv(rows: list[list[str]]) -> str:
    row_count = len(rows)
    lines = ["number,count,round_appearance_probability_percent"]
    row_appearance = _value_row_appearance_counts(rows)
    for value, count in _numeric_value_frequency(rows):
        probability = _format_percent((row_appearance.get(value, 0) / row_count) * 100) if row_count else "0"
        lines.append(f"{value},{count},{probability}")
    return "\n".join(lines)


def _format_percent(value: float) -> str:
    formatted = f"{value:.2f}".rstrip("0").rstrip(".")
    return formatted or "0"


def _numeric_value_frequency(rows: list[list[str]]) -> list[tuple[str, int]]:
    frequency: dict[int, int] = {}
    for row in rows:
        for cell in row:
            value = str(cell).strip()
            if not value:
                continue
            try:
                number = int(value)
            except ValueError:
                continue
            frequency[number] = frequency.get(number, 0) + 1
    return [(str(value), frequency[value]) for value in sorted(frequency)]


def _render_value_frequency_csv(header: list[str], rows: list[list[str]]) -> str:
    row_count = len(rows)
    total_counts = _value_total_counts(rows)
    row_counts = _value_row_appearance_counts(rows)
    columns_by_value = _value_columns(header, rows)

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "value",
            "total_cell_count",
            "row_appearance_count",
            "row_appearance_probability_percent",
            "columns_seen",
        ]
    )
    for value in _sorted_values(total_counts):
        row_appearance_count = row_counts.get(value, 0)
        probability = _format_percent((row_appearance_count / row_count) * 100) if row_count else "0"
        writer.writerow(
            [
                value,
                total_counts[value],
                row_appearance_count,
                probability,
                "; ".join(sorted(columns_by_value.get(value, set()))),
            ]
        )
    return output.getvalue().strip()


def _value_total_counts(rows: list[list[str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        for cell in row:
            value = str(cell).strip()
            if not value:
                continue
            counts[value] = counts.get(value, 0) + 1
    return counts


def _value_row_appearance_counts(rows: list[list[str]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        seen = {str(cell).strip() for cell in row if str(cell).strip()}
        for value in seen:
            counts[value] = counts.get(value, 0) + 1
    return counts


def _value_columns(header: list[str], rows: list[list[str]]) -> dict[str, set[str]]:
    columns: dict[str, set[str]] = {}
    for row in rows:
        for index, cell in enumerate(row):
            value = str(cell).strip()
            if not value:
                continue
            column_name = header[index] if index < len(header) else f"column_{index + 1}"
            columns.setdefault(value, set()).add(column_name)
    return columns


def _sorted_values(counts: dict[str, int]) -> list[str]:
    def sort_key(value: str) -> tuple[int, float | str]:
        try:
            return (0, float(value))
        except ValueError:
            return (1, value)

    return sorted(counts, key=sort_key)


def _column_value_summaries(header: list[str], rows: list[list[str]]) -> list[str]:
    summaries: list[str] = []
    column_count = len(header)
    for column_index in range(column_count):
        frequency: dict[str, int] = {}
        for row in rows:
            value = row[column_index].strip() if column_index < len(row) else ""
            if not value:
                continue
            frequency[value] = frequency.get(value, 0) + 1

        if not frequency or len(frequency) > 40:
            continue

        values = ", ".join(
            f"{value}:{count}"
            for value, count in sorted(frequency.items(), key=lambda item: (-item[1], item[0]))
        )
        summaries.append(f"  - {header[column_index]}: {values}")

    return summaries


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
