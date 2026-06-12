from __future__ import annotations

import csv
import json
import statistics
from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Any

import pandas as pd
from charset_normalizer import from_bytes
from pandas.api import types as pd_types
from pygments import lex
from pygments.lexers import guess_lexer_for_filename
from pygments.token import Token
from pygments.util import ClassNotFound

from shared.runtime_paths import app_data_path, runtime_root
from shared.file_types import (
    JSON_SUFFIXES,
    SOURCE_CODE_SUFFIXES,
    SPREADSHEET_SUFFIXES,
    SUPPORTED_FILE_SUFFIXES,
    SUPPORTED_TEXT_FILE_SUFFIXES,
    TABLE_SUFFIXES,
)

try:
    from tree_sitter_language_pack import detect_language_from_path, get_parser
except Exception:  # pragma: no cover - optional parser integration
    detect_language_from_path = None
    get_parser = None


MAX_ANALYSIS_FILE_BYTES = 1024 * 1024
TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "utf-16", "cp949")
TREE_SITTER_LANGUAGE_ALIASES = {
    "c++": "cpp",
    "cc": "cpp",
    "cxx": "cpp",
    "h": "c",
    "hpp": "cpp",
    "hxx": "cpp",
    "js": "javascript",
    "jsx": "javascript",
    "py": "python",
    "ts": "typescript",
    "tsx": "tsx",
}
TREE_SITTER_SUFFIX_LANGUAGES = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".h": "c",
    ".hh": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".java": "java",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".php": "php",
    ".rb": "ruby",
    ".sh": "bash",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
}


class FileAnalysisError(Exception):
    pass


@dataclass(frozen=True)
class FileAnalysisRequest:
    file_path: str
    sample_size: int = 10
    include_value_frequencies: bool = True
    save_result: bool = False
    output_format: str = "json"


class FileAnalysisService:
    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or runtime_root()
        self.exports_dir = app_data_path("file_analysis")

    def analyze(self, request: FileAnalysisRequest) -> dict[str, Any]:
        path = self._validate_file_path(request.file_path)
        suffix = path.suffix.lower()
        if suffix in SPREADSHEET_SUFFIXES:
            analysis = self._analyze_spreadsheet(
                path,
                sample_size=request.sample_size,
                include_value_frequencies=request.include_value_frequencies,
            )
        else:
            raw_content = self._read_limited_text(path)
            analysis = self._analyze_content(
                path=path,
                content=raw_content,
                sample_size=request.sample_size,
                include_value_frequencies=request.include_value_frequencies,
            )

        payload: dict[str, Any] = {
            "file": self._file_metadata(path),
            "analysis": analysis,
        }

        if request.save_result:
            output_path = self._save_result(payload, path, request.output_format)
            payload["output"] = {
                "path": str(output_path),
                "format": output_path.suffix.lstrip("."),
            }

        return payload

    def _validate_file_path(self, file_path: str) -> Path:
        raw_path = Path(str(file_path or "")).expanduser()
        if not raw_path.is_absolute():
            raw_path = self.project_root / raw_path

        try:
            resolved = raw_path.resolve()
        except OSError as error:
            raise FileAnalysisError(f"Invalid file path: {file_path}") from error

        if not resolved.exists():
            raise FileAnalysisError(f"File does not exist: {resolved}")
        if not resolved.is_file():
            raise FileAnalysisError(f"Path is not a file: {resolved}")
        if resolved.stat().st_size > MAX_ANALYSIS_FILE_BYTES:
            raise FileAnalysisError(
                f"File is too large. Limit is {MAX_ANALYSIS_FILE_BYTES} bytes."
            )

        suffix = resolved.suffix.lower()
        if suffix not in SUPPORTED_FILE_SUFFIXES:
            raise FileAnalysisError(f"Unsupported file type: {suffix or '(none)'}")

        return resolved

    def _read_limited_text(self, path: Path) -> str:
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise FileAnalysisError(f"Could not read file: {path.name}") from error

        if b"\x00" in raw:
            raise FileAnalysisError(f"File appears to be binary: {path.name}")

        last_error: UnicodeDecodeError | None = None
        for encoding in TEXT_ENCODINGS:
            try:
                return raw.decode(encoding)
            except UnicodeDecodeError as error:
                last_error = error

        detected = from_bytes(raw).best()
        if detected is not None and detected.encoding:
            return str(detected)

        raise FileAnalysisError(f"Could not decode text file: {path.name}") from last_error

    def _file_metadata(self, path: Path) -> dict[str, Any]:
        stat = path.stat()
        return {
            "path": str(path),
            "name": path.name,
            "suffix": path.suffix.lower(),
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        }

    def _analyze_content(
        self,
        *,
        path: Path,
        content: str,
        sample_size: int,
        include_value_frequencies: bool,
    ) -> dict[str, Any]:
        suffix = path.suffix.lower()
        if suffix in TABLE_SUFFIXES:
            return self._analyze_table(
                content,
                delimiter="\t" if suffix == ".tsv" else ",",
                sample_size=sample_size,
                include_value_frequencies=include_value_frequencies,
            )
        if suffix in JSON_SUFFIXES:
            return self._analyze_json(content, sample_size=sample_size)
        if suffix in SOURCE_CODE_SUFFIXES:
            return self._analyze_code(path, content, sample_size=sample_size)
        return self._analyze_text(content, sample_size=sample_size)

    def _analyze_table(
        self,
        content: str,
        *,
        delimiter: str,
        sample_size: int,
        include_value_frequencies: bool,
    ) -> dict[str, Any]:
        dataframe, has_header = self._read_table_dataframe(content, delimiter=delimiter)
        if dataframe.empty and not list(dataframe.columns):
            return {"type": "table", "parse_status": "empty"}

        dataframe = self._normalize_dataframe(dataframe)
        return self._analysis_from_dataframe(
            dataframe,
            analysis_type="table",
            engine="pandas",
            parse_status="ok",
            header_row_detected=has_header,
            sample_size=sample_size,
            include_value_frequencies=include_value_frequencies,
            delimiter=delimiter,
        )

    def _analysis_from_dataframe(
        self,
        dataframe: pd.DataFrame,
        *,
        analysis_type: str,
        engine: str,
        parse_status: str,
        header_row_detected: bool,
        sample_size: int,
        include_value_frequencies: bool,
        delimiter: str | None = None,
        sheet_name: str | None = None,
    ) -> dict[str, Any]:
        columns = [str(column) for column in dataframe.columns]

        analysis: dict[str, Any] = {
            "type": analysis_type,
            "parse_status": parse_status,
            "engine": engine,
            "header_row_detected": header_row_detected,
            "row_count": int(len(dataframe.index)),
            "column_count": int(len(dataframe.columns)),
            "columns": columns,
            "sample_rows": self._sample_rows_from_dataframe(dataframe, sample_size),
            "schema": self._schema_from_dataframe(dataframe),
            "column_summary_csv": self._column_summary_csv(dataframe),
            "table_reasoning_hints": self._table_reasoning_hints(dataframe),
        }
        if delimiter is not None:
            analysis["delimiter"] = delimiter
        if sheet_name is not None:
            analysis["sheet_name"] = sheet_name

        if include_value_frequencies:
            value_frequencies = self._value_frequencies_from_dataframe(dataframe)
            numeric_frequencies = [
                row
                for row in value_frequencies
                if self._is_number_like(str(row["value"]))
            ]
            analysis["value_frequencies"] = value_frequencies
            analysis["numeric_value_frequencies"] = numeric_frequencies
            analysis["all_cell_value_frequency_csv"] = self._frequency_rows_to_csv(
                value_frequencies
            )
            analysis["numeric_value_frequency_csv"] = self._frequency_rows_to_csv(
                numeric_frequencies,
                first_column="number",
            )
            analysis["per_column_value_frequency_csv"] = (
                self._per_column_value_frequency_csv(dataframe)
            )

        return analysis

    def _analyze_spreadsheet(
        self,
        path: Path,
        *,
        sample_size: int,
        include_value_frequencies: bool,
    ) -> dict[str, Any]:
        try:
            workbook = pd.ExcelFile(path, engine="openpyxl")
        except Exception as error:
            raise FileAnalysisError(f"Could not read spreadsheet with pandas: {error}") from error

        sheet_analyses: list[dict[str, Any]] = []
        for sheet_name in workbook.sheet_names:
            dataframe, has_header = self._read_excel_sheet_dataframe(
                workbook,
                sheet_name=sheet_name,
            )
            dataframe = self._normalize_dataframe(dataframe)
            sheet_analyses.append(
                self._analysis_from_dataframe(
                    dataframe,
                    analysis_type="table",
                    engine="pandas/openpyxl",
                    parse_status="ok",
                    header_row_detected=has_header,
                    sample_size=sample_size,
                    include_value_frequencies=include_value_frequencies,
                    sheet_name=sheet_name,
                )
            )

        if not sheet_analyses:
            return {
                "type": "workbook",
                "parse_status": "empty",
                "engine": "pandas/openpyxl",
                "sheet_count": 0,
                "sheets": [],
            }

        primary = dict(sheet_analyses[0])
        primary.update(
            {
                "type": "workbook",
                "parse_status": "ok",
                "engine": "pandas/openpyxl",
                "sheet_count": len(sheet_analyses),
                "sheet_names": list(workbook.sheet_names),
                "primary_sheet": sheet_analyses[0].get("sheet_name"),
                "sheets": sheet_analyses,
            }
        )
        primary["table_reasoning_hints"] = [
            "This workbook was parsed from an Excel .xlsx file.",
            "Use primary_sheet for direct CSV-style answers unless the user asks for a different sheet or all sheets.",
            *list(primary.get("table_reasoning_hints") or []),
        ]
        return primary

    def _read_table_dataframe(self, content: str, *, delimiter: str) -> tuple[pd.DataFrame, bool]:
        try:
            preview_rows = [
                [str(cell).strip() for cell in row]
                for row in csv.reader(StringIO(content), delimiter=delimiter)
                if any(str(cell).strip() for cell in row)
            ]
        except csv.Error as error:
            raise FileAnalysisError(f"Could not parse table preview: {error}") from error

        if not preview_rows:
            return pd.DataFrame(), False

        has_header = self._looks_like_header_row(preview_rows[0])
        try:
            dataframe = pd.read_csv(
                StringIO(content),
                sep=delimiter,
                header=0 if has_header else None,
                dtype=str,
                keep_default_na=False,
                na_values=[],
                engine="python",
            )
        except Exception as error:
            raise FileAnalysisError(f"Could not parse table with pandas: {error}") from error

        if not has_header:
            dataframe.columns = [f"column_{index}" for index in range(1, len(dataframe.columns) + 1)]
        else:
            dataframe.columns = [
                str(column).strip() or f"column_{index}"
                for index, column in enumerate(dataframe.columns, start=1)
            ]
        dataframe.columns = self._unique_column_names(
            [str(column) for column in dataframe.columns]
        )

        return dataframe, has_header

    def _read_excel_sheet_dataframe(
        self,
        workbook: pd.ExcelFile,
        *,
        sheet_name: str,
    ) -> tuple[pd.DataFrame, bool]:
        try:
            raw_dataframe = pd.read_excel(
                workbook,
                sheet_name=sheet_name,
                header=None,
                dtype=str,
                keep_default_na=False,
            )
        except Exception as error:
            raise FileAnalysisError(
                f'Could not parse Excel sheet "{sheet_name}" with pandas: {error}'
            ) from error

        raw_dataframe = raw_dataframe.dropna(how="all").dropna(axis=1, how="all")
        rows = [
            [str(cell).strip() for cell in row]
            for row in raw_dataframe.fillna("").values.tolist()
            if any(str(cell).strip() for cell in row)
        ]
        if not rows:
            return pd.DataFrame(), False

        has_header = self._looks_like_header_row(rows[0])
        if has_header:
            columns = [
                cell if cell else f"column_{index}"
                for index, cell in enumerate(rows[0], start=1)
            ]
            data_rows = rows[1:]
        else:
            columns = [f"column_{index}" for index in range(1, len(rows[0]) + 1)]
            data_rows = rows

        columns = self._unique_column_names(columns)
        return pd.DataFrame(data_rows, columns=columns), has_header

    def _unique_column_names(self, columns: list[str]) -> list[str]:
        seen: dict[str, int] = {}
        unique: list[str] = []
        for index, column in enumerate(columns, start=1):
            base = str(column).strip() or f"column_{index}"
            count = seen.get(base, 0) + 1
            seen[base] = count
            unique.append(base if count == 1 else f"{base}_{count}")
        return unique

    def _normalize_dataframe(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        normalized = dataframe.fillna("").astype(str)
        normalized.columns = [str(column) for column in normalized.columns]
        for column in normalized.columns:
            normalized[column] = normalized[column].map(lambda value: str(value).strip())
        return normalized

    def _analyze_json(self, content: str, *, sample_size: int) -> dict[str, Any]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as error:
            raise FileAnalysisError(f"Could not parse JSON: {error}") from error

        if isinstance(parsed, list):
            return {
                "type": "json",
                "root_type": "array",
                "item_count": len(parsed),
                "sample_items": parsed[:sample_size],
            }
        if isinstance(parsed, dict):
            return {
                "type": "json",
                "root_type": "object",
                "keys": list(parsed.keys()),
                "sample": dict(list(parsed.items())[:sample_size]),
            }
        return {
            "type": "json",
            "root_type": type(parsed).__name__,
            "value": parsed,
        }

    def _analyze_text(self, content: str, *, sample_size: int) -> dict[str, Any]:
        lines = content.splitlines()
        non_empty_lines = [line for line in lines if line.strip()]
        return {
            "type": "text",
            "line_count": len(lines),
            "non_empty_line_count": len(non_empty_lines),
            "character_count": len(content),
            "sample_lines": lines[:sample_size],
        }

    def _analyze_code(self, path: Path, content: str, *, sample_size: int) -> dict[str, Any]:
        lines = content.splitlines()
        pygments_info = self._pygments_code_info(path, content)
        tree_info = self._tree_sitter_code_info(path, content)
        return {
            "type": "code",
            "language": tree_info.get("language") or pygments_info.get("language") or path.suffix.lstrip("."),
            "line_count": len(lines),
            "non_empty_line_count": len([line for line in lines if line.strip()]),
            "character_count": len(content),
            "sample_lines": lines[:sample_size],
            "lexer": pygments_info,
            "tree_sitter": tree_info,
            "imports": tree_info.get("imports") or self._fallback_import_lines(lines),
            "symbols": tree_info.get("symbols") or [],
            "token_summary": pygments_info.get("token_summary") or {},
        }

    def _pygments_code_info(self, path: Path, content: str) -> dict[str, Any]:
        try:
            lexer = guess_lexer_for_filename(path.name, content)
        except ClassNotFound:
            return {"available": False, "language": None, "token_summary": {}}

        token_summary: dict[str, int] = {
            "comments": 0,
            "strings": 0,
            "keywords": 0,
            "names": 0,
            "numbers": 0,
        }
        for token_type, value in lex(content, lexer):
            if not str(value).strip():
                continue
            if token_type in Token.Comment:
                token_summary["comments"] += 1
            elif token_type in Token.Literal.String:
                token_summary["strings"] += 1
            elif token_type in Token.Keyword:
                token_summary["keywords"] += 1
            elif token_type in Token.Name:
                token_summary["names"] += 1
            elif token_type in Token.Literal.Number:
                token_summary["numbers"] += 1

        return {
            "available": True,
            "language": lexer.name,
            "aliases": list(getattr(lexer, "aliases", []) or []),
            "token_summary": token_summary,
        }

    def _tree_sitter_code_info(self, path: Path, content: str) -> dict[str, Any]:
        if detect_language_from_path is None or get_parser is None:
            return {"available": False, "error": "tree-sitter-language-pack is unavailable"}

        try:
            language = self._tree_sitter_language(path)
            parser = get_parser(language)
            tree = parser.parse(content)
        except Exception as error:
            return {
                "available": False,
                "language": path.suffix.lstrip("."),
                "error": str(error),
            }

        root = tree.root_node() if callable(tree.root_node) else tree.root_node
        symbols: list[dict[str, Any]] = []
        imports: list[dict[str, Any]] = []
        self._collect_tree_sitter_items(root, content, symbols=symbols, imports=imports)
        return {
            "available": True,
            "language": language,
            "root_type": self._node_kind(root),
            "has_error": bool(self._node_value(root, "has_error", default=False)),
            "symbols": symbols[:200],
            "imports": imports[:200],
        }

    def _tree_sitter_language(self, path: Path) -> str:
        detected = ""
        if detect_language_from_path is not None:
            detected = str(detect_language_from_path(str(path)) or "").strip().lower()
        language = TREE_SITTER_LANGUAGE_ALIASES.get(detected, detected)
        if language:
            return language
        return TREE_SITTER_SUFFIX_LANGUAGES.get(path.suffix.lower(), path.suffix.lstrip("."))

    def _collect_tree_sitter_items(
        self,
        node: Any,
        content: str,
        *,
        symbols: list[dict[str, Any]],
        imports: list[dict[str, Any]],
    ) -> None:
        if self._is_symbol_node(node):
            symbols.append(
                {
                    "kind": self._node_kind(node),
                    "name": self._node_name(node, content),
                    "start_line": self._node_start_line(node),
                    "end_line": self._node_end_line(node),
                }
            )
        if self._is_import_node(node):
            imports.append(
                {
                    "kind": self._node_kind(node),
                    "text": self._node_text(node, content),
                    "start_line": self._node_start_line(node),
                }
            )

        for child in self._node_children(node):
            self._collect_tree_sitter_items(child, content, symbols=symbols, imports=imports)

    def _is_symbol_node(self, node: Any) -> bool:
        return self._node_kind(node) in {
            "function_definition",
            "function_declaration",
            "method_definition",
            "class_definition",
            "class_declaration",
            "struct_specifier",
            "enum_specifier",
            "interface_declaration",
            "lexical_declaration",
        }

    def _is_import_node(self, node: Any) -> bool:
        return self._node_kind(node) in {
            "import_statement",
            "import_from_statement",
            "preproc_include",
            "using_declaration",
            "package_clause",
            "use_declaration",
        }

    def _node_name(self, node: Any, content: str) -> str:
        for field in ("name", "declarator"):
            child = node.child_by_field_name(field)
            if child is not None:
                text = self._node_text(child, content)
                return text.split("(", 1)[0].strip()
        return ""

    def _node_text(self, node: Any, content: str) -> str:
        raw = content.encode("utf-8")[
            self._node_value(node, "start_byte", default=0) : self._node_value(
                node,
                "end_byte",
                default=0,
            )
        ]
        return raw.decode("utf-8", errors="replace").strip()

    def _node_kind(self, node: Any) -> str:
        return str(self._node_value(node, "type", default="") or self._node_value(node, "kind", default=""))

    def _node_children(self, node: Any) -> list[Any]:
        children = self._node_value(node, "children", default=None)
        if children is not None:
            return list(children)
        child_count = int(self._node_value(node, "child_count", default=0) or 0)
        child_method = getattr(node, "child", None)
        if not callable(child_method):
            return []
        return [child_method(index) for index in range(child_count) if child_method(index) is not None]

    def _node_start_line(self, node: Any) -> int:
        position = self._node_value(node, "start_point", default=None)
        if position is None:
            position = self._node_value(node, "start_position", default=(0, 0))
        return self._position_line(position)

    def _node_end_line(self, node: Any) -> int:
        position = self._node_value(node, "end_point", default=None)
        if position is None:
            position = self._node_value(node, "end_position", default=(0, 0))
        return self._position_line(position)

    def _position_line(self, position: Any) -> int:
        row = getattr(position, "row", None)
        if row is not None:
            return int(row) + 1
        return int(position[0]) + 1

    def _node_value(self, node: Any, name: str, *, default: Any = None) -> Any:
        try:
            value = getattr(node, name)
        except AttributeError:
            return default
        if callable(value):
            try:
                return value()
            except TypeError:
                return default
        return value

    def _fallback_import_lines(self, lines: list[str]) -> list[dict[str, Any]]:
        imports: list[dict[str, Any]] = []
        prefixes = ("import ", "from ", "#include", "using ", "use ", "package ")
        for index, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith(prefixes):
                imports.append({"kind": "line_import", "text": stripped, "start_line": index})
        return imports[:200]

    def _sample_rows_from_dataframe(
        self,
        dataframe: pd.DataFrame,
        sample_size: int,
    ) -> list[dict[str, str]]:
        limit = max(0, min(sample_size, 100))
        return dataframe.head(limit).to_dict(orient="records")

    def _schema_from_dataframe(self, dataframe: pd.DataFrame) -> list[dict[str, Any]]:
        schema: list[dict[str, Any]] = []
        for column in dataframe.columns:
            series = dataframe[column].astype(str)
            non_empty_series = series[series.str.strip() != ""]
            non_empty = non_empty_series.tolist()
            schema.append(
                {
                    "name": column,
                    "inferred_type": self._infer_type_from_series(non_empty_series),
                    "missing_count": int(len(series) - len(non_empty_series)),
                    "unique_count": len(set(non_empty)),
                    "numeric_stats": self._numeric_stats(non_empty),
                    "examples": self._example_values(non_empty),
                    "top_values": self._top_values(non_empty),
                }
            )
        return schema

    def _column_summary_csv(self, dataframe: pd.DataFrame) -> str:
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "column",
                "inferred_type",
                "non_empty_count",
                "missing_count",
                "unique_count",
                "example_values",
                "top_values",
                "numeric_min",
                "numeric_max",
                "numeric_mean",
                "numeric_median",
            ]
        )
        for column in dataframe.columns:
            series = dataframe[column].astype(str)
            non_empty_series = series[series.str.strip() != ""]
            non_empty = non_empty_series.tolist()
            numeric_stats = self._numeric_stats(non_empty) or {}
            writer.writerow(
                [
                    column,
                    self._infer_type_from_series(non_empty_series),
                    len(non_empty),
                    int(len(series) - len(non_empty_series)),
                    len(set(non_empty)),
                    "; ".join(self._example_values(non_empty)),
                    "; ".join(
                        f"{item['value']}:{item['count']}"
                        for item in self._top_values(non_empty)
                    ),
                    self._format_stat_value(numeric_stats.get("min")),
                    self._format_stat_value(numeric_stats.get("max")),
                    self._format_stat_value(numeric_stats.get("mean")),
                    self._format_stat_value(numeric_stats.get("median")),
                ]
            )
        return output.getvalue().strip()

    def _per_column_value_frequency_csv(self, dataframe: pd.DataFrame) -> str:
        row_count = int(len(dataframe.index))
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "column",
                "value",
                "total_count",
                "row_appearance_count",
                "row_appearance_probability_percent",
            ]
        )
        for column in dataframe.columns:
            total_counts: dict[str, int] = {}
            row_counts: dict[str, int] = {}
            for value in dataframe[column].astype(str):
                normalized = value.strip()
                if not normalized:
                    continue
                total_counts[normalized] = total_counts.get(normalized, 0) + 1
                row_counts[normalized] = row_counts.get(normalized, 0) + 1

            for value in self._sorted_values(total_counts):
                row_appearance_count = row_counts.get(value, 0)
                writer.writerow(
                    [
                        column,
                        value,
                        total_counts[value],
                        row_appearance_count,
                        self._format_percent((row_appearance_count / row_count) * 100)
                        if row_count
                        else "0",
                    ]
                )
        return output.getvalue().strip()

    def _table_reasoning_hints(self, dataframe: pd.DataFrame) -> list[str]:
        hints = [
            "Use column_summary_csv to understand each column before answering broad analysis requests.",
            "Use per_column_value_frequency_csv for category counts within a specific column.",
            "Use all_cell_value_frequency_csv only when the user asks for values across the entire table.",
        ]
        integer_columns = [
            str(column)
            for column in dataframe.columns
            if self._infer_type_from_series(
                dataframe[column].astype(str)[dataframe[column].astype(str).str.strip() != ""]
            )
            == "integer"
        ]
        if len(integer_columns) >= 2:
            hints.append(
                "Multiple integer columns are present. Do not treat a row as a combination unless the user explicitly describes the rows that way."
            )
        return hints

    def _value_frequencies_from_dataframe(
        self,
        dataframe: pd.DataFrame,
    ) -> list[dict[str, Any]]:
        row_count = int(len(dataframe.index))
        total_counts: dict[str, int] = {}
        row_counts: dict[str, int] = {}
        columns_seen: dict[str, set[str]] = {}

        for _, row in dataframe.iterrows():
            seen_in_row: set[str] = set()
            for column in dataframe.columns:
                value = str(row[column]).strip()
                if not value:
                    continue
                total_counts[value] = total_counts.get(value, 0) + 1
                seen_in_row.add(value)
                columns_seen.setdefault(value, set()).add(str(column))
            for value in seen_in_row:
                row_counts[value] = row_counts.get(value, 0) + 1

        result: list[dict[str, Any]] = []
        for value in self._sorted_values(total_counts):
            row_appearance_count = row_counts.get(value, 0)
            result.append(
                {
                    "value": value,
                    "total_cell_count": total_counts[value],
                    "row_appearance_count": row_appearance_count,
                    "row_appearance_probability_percent": self._format_percent(
                        (row_appearance_count / row_count) * 100
                    )
                    if row_count
                    else "0",
                    "columns_seen": sorted(columns_seen.get(value, set())),
                }
            )
        return result

    def _example_values(self, values: list[str], limit: int = 5) -> list[str]:
        examples: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            examples.append(normalized)
            if len(examples) >= limit:
                break
        return examples

    def _top_values(self, values: list[str], limit: int = 5) -> list[dict[str, Any]]:
        counts: dict[str, int] = {}
        for value in values:
            normalized = str(value).strip()
            if not normalized:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
        return [
            {"value": value, "count": counts[value]}
            for value in sorted(counts, key=lambda item: (-counts[item], item))[:limit]
        ]

    def _frequency_rows_to_csv(
        self,
        rows: list[dict[str, Any]],
        *,
        first_column: str = "value",
    ) -> str:
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                first_column,
                "total_cell_count",
                "row_appearance_count",
                "row_appearance_probability_percent",
                "columns_seen",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["value"],
                    row["total_cell_count"],
                    row["row_appearance_count"],
                    row["row_appearance_probability_percent"],
                    "; ".join(row["columns_seen"]),
                ]
            )
        return output.getvalue().strip()

    def _save_result(
        self,
        payload: dict[str, Any],
        source_path: Path,
        output_format: str,
    ) -> Path:
        suffix = ".csv" if output_format.lower() == "csv" else ".json"
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_path = self.exports_dir / f"{source_path.stem}-analysis-{timestamp}{suffix}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if suffix == ".csv":
            content = str(
                payload.get("analysis", {}).get("all_cell_value_frequency_csv") or ""
            )
            if not content.strip():
                content = self._flatten_analysis_to_csv(payload)
            output_path.write_text(content.rstrip() + "\n", encoding="utf-8-sig")
        else:
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return output_path

    def _flatten_analysis_to_csv(self, payload: dict[str, Any]) -> str:
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["section", "key", "value"])
        for section, values in payload.items():
            if isinstance(values, dict):
                for key, value in values.items():
                    writer.writerow([section, key, json.dumps(value, ensure_ascii=False)])
            else:
                writer.writerow([section, "", json.dumps(values, ensure_ascii=False)])
        return output.getvalue().strip()

    def _looks_like_header_row(self, row: list[str]) -> bool:
        cells = [str(cell).strip() for cell in row if str(cell).strip()]
        return bool(cells) and any(not self._is_number_like(cell) for cell in cells)

    def _infer_type_from_series(self, series: pd.Series) -> str:
        if series.empty:
            return "empty"
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().all():
            if pd_types.is_integer_dtype(numeric) or (numeric % 1 == 0).all():
                return "integer"
            return "number"
        return "text"

    def _infer_type(self, values: list[str]) -> str:
        if not values:
            return "empty"
        if all(self._is_int_like(value) for value in values):
            return "integer"
        if all(self._is_number_like(value) for value in values):
            return "number"
        return "text"

    def _numeric_stats(self, values: list[str]) -> dict[str, Any] | None:
        numbers: list[float] = []
        for value in values:
            try:
                numbers.append(float(value))
            except ValueError:
                return None
        if not numbers:
            return None
        return {
            "min": min(numbers),
            "max": max(numbers),
            "mean": statistics.fmean(numbers),
            "median": statistics.median(numbers),
        }

    def _is_number_like(self, value: str) -> bool:
        try:
            float(str(value).strip())
        except ValueError:
            return False
        return True

    def _is_int_like(self, value: str) -> bool:
        try:
            return float(str(value).strip()).is_integer()
        except ValueError:
            return False

    def _format_percent(self, value: float) -> str:
        formatted = f"{value:.2f}".rstrip("0").rstrip(".")
        return formatted or "0"

    def _format_stat_value(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value)

    def _sorted_values(self, counts: dict[str, int]) -> list[str]:
        def sort_key(value: str) -> tuple[int, float | str]:
            try:
                return (0, float(value))
            except ValueError:
                return (1, value)

        return sorted(counts, key=sort_key)
