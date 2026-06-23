from __future__ import annotations

from dataclasses import dataclass

from resources.addons.file_import_export import (
    attached_file_handling_hint_lines,
    inline_data_handling_hint_lines,
)
from resources.addons.file_import_export.types import (
    CONFIG_SUFFIXES,
    JSON_SUFFIXES,
    MARKDOWN_SUFFIXES,
    SOURCE_CODE_SUFFIXES,
    SPREADSHEET_SUFFIXES,
    TABLE_SUFFIXES,
    TEXT_SUFFIXES,
    file_kind_display_label,
    normalized_suffix,
)


@dataclass(frozen=True)
class FileIntakeSummary:
    kind: str
    type_label: str
    model_guidance: str


def summarize_file_intake(name: str, suffix: str | None = None) -> FileIntakeSummary:
    suffix_value = normalized_suffix(suffix or name)
    if suffix_value in TABLE_SUFFIXES or suffix_value in SPREADSHEET_SUFFIXES:
        type_label = (
            f"{suffix_value.lstrip('.').upper()} spreadsheet data"
            if suffix_value in SPREADSHEET_SUFFIXES
            else f"{suffix_value.lstrip('.').upper()} table data"
        )
        return FileIntakeSummary(
            kind="table",
            type_label=type_label,
            model_guidance=(
                "Treat this attachment as structured rows and columns. "
                "For calculations, aggregation, filtering, counting, conversion, or CSV output, "
                "use deterministic parsed/tool context rather than guessing from prose. "
                "Treat delimited values as independent cells unless the user explicitly asks for "
                "combination or row-as-a-single-value analysis."
            ),
        )
    if suffix_value in JSON_SUFFIXES:
        return FileIntakeSummary(
            kind="json",
            type_label="JSON structured data",
            model_guidance=(
                "Treat this attachment as structured JSON data. Preserve keys and hierarchy "
                "when summarizing, extracting, transforming, or validating it."
            ),
        )
    if suffix_value in MARKDOWN_SUFFIXES:
        return FileIntakeSummary(
            kind="markdown",
            type_label="Markdown document",
            model_guidance=(
                "Treat this attachment as a Markdown document. Preserve headings, lists, "
                "links, and code blocks when the user asks for editing or extraction."
            ),
        )
    if suffix_value in SOURCE_CODE_SUFFIXES:
        return FileIntakeSummary(
            kind="source_code",
            type_label=f"{suffix_value.lstrip('.').upper()} source file",
            model_guidance=(
                "Treat this attachment as source code or configuration text. For review, "
                "debugging, refactoring, explanation, or symbol lookup, reason from the file content "
                "and any deterministic code analysis context."
            ),
        )
    if suffix_value in CONFIG_SUFFIXES:
        return FileIntakeSummary(
            kind="text",
            type_label=f"{suffix_value.lstrip('.').upper()} config/document",
            model_guidance=(
                "Treat this attachment as configuration or structured document text. Preserve keys, "
                "sections, hierarchy, and literal values when summarizing, editing, or extracting."
            ),
        )
    if suffix_value in TEXT_SUFFIXES:
        return FileIntakeSummary(
            kind="text",
            type_label="plain text document",
            model_guidance=(
                "Treat this attachment as plain text. Summarize, extract, rewrite, or analyze it "
                "according to the user's request."
            ),
        )
    return FileIntakeSummary(
        kind="text",
        type_label=f"{suffix_value or 'unknown'} text-like file",
        model_guidance=(
            "Treat this attachment as text-like content if it was accepted by the app. "
            "Use the attached content as the primary evidence for the answer."
        ),
    )


def expected_response_guidance(user_content: str) -> str:
    if str(user_content or "").strip():
        return (
            "The user expects the assistant to answer the request using the attached file as "
            "the primary input. Do not merely acknowledge the upload, and do not claim the file "
            "cannot be read if file context or tool access is present. Infer the exact operation "
            "from [User Request]."
        )
    return (
        "The user attached a file without an explicit instruction. Summarize what the file appears "
        "to contain and offer the most likely next actions."
    )


def render_attached_file_handling_hint() -> str:
    return "\n".join(attached_file_handling_hint_lines())


def render_inline_data_handling_hint() -> str:
    return "\n".join(inline_data_handling_hint_lines())


def render_attachment_intake_block(name: str, suffix: str, user_content: str) -> str:
    summary = summarize_file_intake(name, suffix)
    return (
        "[Attachment Intake]\n"
        f"- file_name: {name}\n"
        f"- file_kind: {summary.kind}\n"
        f"- file_category: {file_kind_display_label(suffix or name)}\n"
        f"- file_type: {summary.type_label}\n"
        f"- expected_user_outcome: {expected_response_guidance(user_content)}\n"
        f"- handling_guidance: {summary.model_guidance}"
    )
