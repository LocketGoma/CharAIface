from datetime import datetime
import csv
from html import escape
from pathlib import Path
import re

from shared.schema.chat import ChatMessage


SUPPORTED_EXPORT_SUFFIXES = {".txt", ".md", ".pdf", ".csv"}


class ChatExportError(Exception):
    pass


def default_chat_export_filename(title: str, exported_at: datetime | None = None) -> str:
    timestamp = (exported_at or datetime.now()).strftime("%Y%m%d-%H%M%S")
    safe_title = re.sub(r"[^\w .-]+", "_", title.strip() or "chat-session")
    safe_title = re.sub(r"\s+", " ", safe_title).strip(" ._-")
    return f"{safe_title or 'chat-session'}-{timestamp}"


def export_chat_session(
    path: str | Path,
    messages: list[ChatMessage],
    *,
    title: str,
    exported_at: datetime | None = None,
    role_labels: dict[str, str] | None = None,
) -> None:
    export_path = Path(path)
    suffix = export_path.suffix.lower()

    if suffix not in SUPPORTED_EXPORT_SUFFIXES:
        raise ChatExportError(f"Unsupported export format: {suffix or '(none)'}")

    if not messages:
        raise ChatExportError("Cannot export an empty chat session.")

    labels = {
        "system": "System",
        "user": "User",
        "assistant": "Assistant",
        "tool": "Tool",
    }
    labels.update(role_labels or {})

    exported_at = exported_at or datetime.now()
    export_path.parent.mkdir(parents=True, exist_ok=True)

    if suffix == ".txt":
        export_path.write_text(
            _render_text(messages, title=title, exported_at=exported_at, role_labels=labels),
            encoding="utf-8",
        )
        return

    if suffix == ".md":
        export_path.write_text(
            _render_markdown(messages, title=title, exported_at=exported_at, role_labels=labels),
            encoding="utf-8",
        )
        return

    if suffix == ".csv":
        _write_session_csv(export_path, messages, role_labels=labels)
        return

    _write_pdf(export_path, messages, title=title, exported_at=exported_at, role_labels=labels)


def export_text_content(
    path: str | Path,
    content: str,
    *,
    title: str,
) -> None:
    export_path = Path(path)
    suffix = export_path.suffix.lower()

    if suffix not in SUPPORTED_EXPORT_SUFFIXES:
        raise ChatExportError(f"Unsupported export format: {suffix or '(none)'}")

    if not content.strip():
        raise ChatExportError("Cannot export empty text.")

    export_path.parent.mkdir(parents=True, exist_ok=True)

    if suffix in {".txt", ".md"}:
        export_path.write_text(content.rstrip() + "\n", encoding="utf-8")
        return

    if suffix == ".csv":
        _write_text_csv(export_path, content)
        return

    _write_text_pdf(export_path, content, title=title)


def _write_session_csv(
    path: Path,
    messages: list[ChatMessage],
    *,
    role_labels: dict[str, str],
) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["role", "created_at", "content"])
        for message in messages:
            writer.writerow(
                [
                    _role_label(message, role_labels),
                    _format_datetime_string(message.created_at),
                    message.content,
                ]
            )


def _write_text_csv(path: Path, content: str) -> None:
    rows = _extract_markdown_table_rows(content)
    if not rows:
        rows = [["content"], [content]]

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerows(rows)


def _extract_markdown_table_rows(content: str) -> list[list[str]]:
    lines = content.splitlines()
    table_lines: list[str] = []
    best_rows: list[list[str]] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            table_lines.append(stripped)
            continue

        rows = _parse_markdown_table_lines(table_lines)
        if len(rows) > len(best_rows):
            best_rows = rows
        table_lines = []

    rows = _parse_markdown_table_lines(table_lines)
    if len(rows) > len(best_rows):
        best_rows = rows

    return best_rows


def _parse_markdown_table_lines(lines: list[str]) -> list[list[str]]:
    if len(lines) < 2:
        return []

    parsed_rows = [_split_markdown_table_row(line) for line in lines]
    separator_index = next(
        (
            index
            for index, row in enumerate(parsed_rows[:3])
            if row and all(_is_markdown_table_separator(cell) for cell in row)
        ),
        None,
    )
    if separator_index is None or separator_index == 0:
        return []

    rows = parsed_rows[:separator_index] + parsed_rows[separator_index + 1 :]
    rows = [[_clean_markdown_table_cell(cell) for cell in row] for row in rows]
    column_count = len(rows[0]) if rows else 0
    if column_count <= 0:
        return []

    return [_normalize_csv_row(row, column_count) for row in rows if any(row)]


def _normalize_csv_row(row: list[str], column_count: int) -> list[str]:
    if len(row) > column_count:
        return row[: column_count - 1] + [" | ".join(row[column_count - 1 :])]
    return row + [""] * (column_count - len(row))


def _split_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def _is_markdown_table_separator(cell: str) -> bool:
    return bool(re.fullmatch(r":?-{3,}:?", cell.strip()))


def _clean_markdown_table_cell(cell: str) -> str:
    cleaned = cell.strip()
    cleaned = re.sub(r"<br\s*/?>", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _render_text(
    messages: list[ChatMessage],
    *,
    title: str,
    exported_at: datetime,
    role_labels: dict[str, str],
) -> str:
    lines = [
        title,
        f"Exported at: {_format_datetime(exported_at)}",
        "",
    ]

    for message in messages:
        lines.extend(
            [
                f"[{_format_datetime_string(message.created_at)}] {_role_label(message, role_labels)}",
                message.content.rstrip(),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _render_markdown(
    messages: list[ChatMessage],
    *,
    title: str,
    exported_at: datetime,
    role_labels: dict[str, str],
) -> str:
    lines = [
        f"# {_escape_markdown_heading(title)}",
        "",
        f"Exported at: {_format_datetime(exported_at)}",
        "",
    ]

    for message in messages:
        lines.extend(
            [
                f"## {_role_label(message, role_labels)} - {_format_datetime_string(message.created_at)}",
                "",
                message.content.rstrip(),
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _write_pdf(
    path: Path,
    messages: list[ChatMessage],
    *,
    title: str,
    exported_at: datetime,
    role_labels: dict[str, str],
) -> None:
    try:
        from PySide6.QtGui import QTextDocument
        from PySide6.QtPrintSupport import QPrinter
    except Exception as error:
        raise ChatExportError(f"PDF export is unavailable: {error}") from error

    document = QTextDocument()
    document.setHtml(
        _render_html(messages, title=title, exported_at=exported_at, role_labels=role_labels)
    )

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    document.print_(printer)


def _write_text_pdf(
    path: Path,
    content: str,
    *,
    title: str,
) -> None:
    try:
        from PySide6.QtGui import QTextDocument
        from PySide6.QtPrintSupport import QPrinter
    except Exception as error:
        raise ChatExportError(f"PDF export is unavailable: {error}") from error

    document = QTextDocument()
    document.setHtml(_render_text_html(content, title=title))

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(path))
    document.print_(printer)


def _render_html(
    messages: list[ChatMessage],
    *,
    title: str,
    exported_at: datetime,
    role_labels: dict[str, str],
) -> str:
    message_blocks = []
    for message in messages:
        message_blocks.append(
            "<section>"
            f"<h2>{escape(_role_label(message, role_labels))}</h2>"
            f"<p class=\"meta\">{escape(_format_datetime_string(message.created_at))}</p>"
            f"<div class=\"content\">{_html_content(message.content)}</div>"
            "</section>"
        )

    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<style>"
        "body{font-family:Arial;"
        "font-size:11pt;color:#1f2933;line-height:1.5;}"
        "h1{font-size:20pt;margin:0 0 6px 0;}"
        "h2{font-size:13pt;margin:18px 0 2px 0;}"
        ".meta{color:#687587;font-size:9pt;margin:0 0 8px 0;}"
        ".content{white-space:pre-wrap;border-top:1px solid #d8dee8;padding-top:8px;}"
        "section{margin:0 0 18px 0;page-break-inside:avoid;}"
        "</style></head><body>"
        f"<h1>{escape(title)}</h1>"
        f"<p class=\"meta\">Exported at: {escape(_format_datetime(exported_at))}</p>"
        f"{''.join(message_blocks)}"
        "</body></html>"
    )


def _render_text_html(content: str, *, title: str) -> str:
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        "<style>"
        "body{font-family:Arial;"
        "font-size:11pt;color:#1f2933;line-height:1.5;}"
        "h1{font-size:18pt;margin:0 0 12px 0;}"
        ".content{white-space:pre-wrap;}"
        "</style></head><body>"
        f"<h1>{escape(title)}</h1>"
        f"<div class=\"content\">{_html_content(content)}</div>"
        "</body></html>"
    )


def _role_label(message: ChatMessage, role_labels: dict[str, str]) -> str:
    return role_labels.get(message.role, str(message.role).title())


def _format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _format_datetime_string(value: str) -> str:
    return value.strip() or "unknown time"


def _escape_markdown_heading(text: str) -> str:
    return text.replace("\n", " ").strip() or "Chat Session"


def _html_content(text: str) -> str:
    return escape(text).replace("\n", "<br>")
