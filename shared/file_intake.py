from __future__ import annotations

from dataclasses import dataclass

from shared.file_types import (
    JSON_SUFFIXES,
    MARKDOWN_SUFFIXES,
    SOURCE_CODE_SUFFIXES,
    TABLE_SUFFIXES,
    TEXT_SUFFIXES,
    normalized_suffix,
)


@dataclass(frozen=True)
class FileIntakeSummary:
    kind: str
    type_label: str
    model_guidance: str


def summarize_file_intake(name: str, suffix: str | None = None) -> FileIntakeSummary:
    suffix_value = normalized_suffix(suffix or name)
    if suffix_value in TABLE_SUFFIXES:
        return FileIntakeSummary(
            kind="table",
            type_label=f"{suffix_value.lstrip('.').upper()} table data",
            model_guidance=(
                "Treat this attachment as structured rows and columns. "
                "For calculations, aggregation, filtering, counting, conversion, or CSV output, "
                "use deterministic parsed/tool context rather than guessing from prose."
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
            type_label=f"{suffix_value.lstrip('.').upper()} source/config file",
            model_guidance=(
                "Treat this attachment as source code or configuration text. For review, "
                "debugging, refactoring, explanation, or symbol lookup, reason from the file content "
                "and any deterministic code analysis context."
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


def render_attachment_intake_block(name: str, suffix: str, user_content: str) -> str:
    summary = summarize_file_intake(name, suffix)
    return (
        "[Attachment Intake]\n"
        f"- file_name: {name}\n"
        f"- file_kind: {summary.kind}\n"
        f"- file_type: {summary.type_label}\n"
        f"- expected_user_outcome: {expected_response_guidance(user_content)}\n"
        f"- handling_guidance: {summary.model_guidance}"
    )
