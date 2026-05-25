from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from shared.schema.chat import ChatMessage


SESSION_INDEX_FILENAME = "session_index.json"
SESSIONS_DIRNAME = "sessions"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_session_title(title: str | None) -> str:
    normalized = " ".join(str(title or "").strip().split())
    if len(normalized.encode("utf-8")) < 2:
        return "New Chat Session"
    return normalized


def is_valid_session_title(title: str | None) -> bool:
    normalized = " ".join(str(title or "").strip().split())
    return len(normalized.encode("utf-8")) >= 2


class ChatSessionStore:
    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.sessions_dir = self.root_dir / SESSIONS_DIRNAME
        self.index_path = self.root_dir / SESSION_INDEX_FILENAME

    def ensure_dirs(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def create_session_id(self) -> str:
        return str(uuid4())

    def save_session(
        self,
        session_id: str | None,
        messages: list[ChatMessage],
        *,
        title: str | None = None,
        character_id: str | None = None,
        character_name: str | None = None,
        user_name: str | None = None,
        route_policy: str | None = None,
        make_current: bool = True,
        touch_updated_at: bool = True,
    ) -> str:
        self.ensure_dirs()

        resolved_session_id = session_id or self.create_session_id()
        now = utc_now_iso()
        existing = self._read_session_payload(resolved_session_id) or {}

        created_at = str(existing.get("created_at") or now)
        updated_at = now if touch_updated_at or not existing else str(existing.get("updated_at") or now)
        resolved_title = normalize_session_title(
            title or str(existing.get("title") or self._make_title(messages))
        )

        payload: dict[str, Any] = {
            "schema_version": 1,
            "session_id": resolved_session_id,
            "title": resolved_title,
            "created_at": created_at,
            "updated_at": updated_at,
            "character_id": character_id or "",
            "character_name": character_name or "",
            "user_name": user_name or "",
            "route_policy": route_policy or "",
            "message_count": len(messages),
            "messages": [message.model_dump(mode="json") for message in messages],
        }

        session_path = self._session_path(resolved_session_id)
        session_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        self._upsert_index_entry(payload, make_current=make_current)
        return resolved_session_id

    def load_session(self, session_id: str) -> dict[str, Any] | None:
        payload = self._read_session_payload(session_id)
        if payload is None:
            return None

        messages: list[ChatMessage] = []
        raw_messages = payload.get("messages") or []
        if isinstance(raw_messages, list):
            for item in raw_messages:
                if not isinstance(item, dict):
                    continue
                try:
                    messages.append(ChatMessage(**item))
                except ValidationError as error:
                    print(f"[SessionStore] Skipped invalid message: {error}")

        payload = dict(payload)
        payload["messages"] = messages
        return payload

    def load_last_session(self) -> dict[str, Any] | None:
        index = self._read_index()
        session_id = str(index.get("last_session_id") or "").strip()
        if not session_id:
            return None
        return self.load_session(session_id)

    def list_sessions(self) -> list[dict[str, Any]]:
        index = self._read_index()
        raw_sessions = index.get("sessions") or []
        if not isinstance(raw_sessions, list):
            return []

        sessions: list[dict[str, Any]] = []
        for entry in raw_sessions:
            if isinstance(entry, dict):
                sessions.append(dict(entry))

        return self._sort_sessions(sessions)

    def delete_session(self, session_id: str) -> bool:
        self.ensure_dirs()
        session_path = self._session_path(session_id)
        deleted = False
        if session_path.exists():
            session_path.unlink()
            deleted = True

        index = self._read_index()
        sessions = [
            entry
            for entry in index.get("sessions", [])
            if isinstance(entry, dict) and entry.get("session_id") != session_id
        ]
        sessions = self._sort_sessions(sessions)
        index["sessions"] = sessions
        if index.get("last_session_id") == session_id:
            index["last_session_id"] = sessions[0].get("session_id") if sessions else ""
        self._write_index(index)
        return deleted


    def rename_session(self, session_id: str, title: str) -> bool:
        self.ensure_dirs()
        normalized_title = " ".join(title.strip().split())
        if not session_id or not is_valid_session_title(normalized_title):
            return False

        payload = self._read_session_payload(session_id)
        if payload is None:
            return False

        now = utc_now_iso()
        payload["title"] = normalized_title
        payload["updated_at"] = now
        session_path = self._session_path(session_id)
        session_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        index = self._read_index()
        changed = False
        for entry in index.get("sessions", []):
            if isinstance(entry, dict) and entry.get("session_id") == session_id:
                entry["title"] = normalized_title
                entry["updated_at"] = now
                changed = True
                break

        if changed:
            self._write_index(index)
        else:
            self._upsert_index_entry(payload, make_current=False)

        return True

    def resolve_session_selector(self, selector: str) -> str | None:
        normalized = selector.strip()
        if not normalized:
            return None

        sessions = self.list_sessions()

        if normalized.isdigit():
            index = int(normalized) - 1
            if 0 <= index < len(sessions):
                return str(sessions[index].get("session_id") or "") or None

        lowered = normalized.lower()
        for session in sessions:
            session_id = str(session.get("session_id") or "")
            if session_id.lower() == lowered:
                return session_id
            if session_id.lower().startswith(lowered):
                return session_id

        return None

    def mark_current(self, session_id: str) -> None:
        index = self._read_index()
        index["last_session_id"] = session_id
        self._write_index(index)

    def _session_path(self, session_id: str) -> Path:
        safe_id = "".join(ch for ch in session_id if ch.isalnum() or ch in "-_")
        return self.sessions_dir / f"{safe_id}.json"

    def _read_session_payload(self, session_id: str) -> dict[str, Any] | None:
        session_path = self._session_path(session_id)
        if not session_path.exists():
            return None
        try:
            data = json.loads(session_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (OSError, json.JSONDecodeError) as error:
            print(f"[SessionStore] Failed to read session {session_id}: {error}")
        return None

    def _read_index(self) -> dict[str, Any]:
        self.ensure_dirs()
        if not self.index_path.exists():
            return {"schema_version": 1, "last_session_id": "", "sessions": []}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if not isinstance(data.get("sessions"), list):
                    data["sessions"] = []
                return data
        except (OSError, json.JSONDecodeError) as error:
            print(f"[SessionStore] Failed to read session index: {error}")
        return {"schema_version": 1, "last_session_id": "", "sessions": []}

    def _write_index(self, index: dict[str, Any]) -> None:
        self.ensure_dirs()
        index.setdefault("schema_version", 1)
        index.setdefault("last_session_id", "")
        raw_sessions = index.setdefault("sessions", [])
        if isinstance(raw_sessions, list):
            deduped_sessions: dict[str, dict[str, Any]] = {}
            for item in raw_sessions:
                if not isinstance(item, dict):
                    continue
                session_id = str(item.get("session_id") or "").strip()
                if not session_id:
                    continue
                normalized_item = dict(item)
                normalized_item["session_id"] = session_id
                normalized_item["title"] = normalize_session_title(
                    str(normalized_item.get("title") or "")
                )
                deduped_sessions[session_id] = normalized_item
            index["sessions"] = self._sort_sessions(list(deduped_sessions.values()))
        else:
            index["sessions"] = []
        self.index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _upsert_index_entry(self, payload: dict[str, Any], *, make_current: bool) -> None:
        index = self._read_index()
        session_id = str(payload.get("session_id") or "")
        if not session_id:
            return

        entry = {
            "session_id": session_id,
            "title": normalize_session_title(str(payload.get("title") or "")),
            "created_at": payload.get("created_at") or "",
            "updated_at": payload.get("updated_at") or "",
            "character_id": payload.get("character_id") or "",
            "character_name": payload.get("character_name") or "",
            "user_name": payload.get("user_name") or "",
            "message_count": payload.get("message_count") or 0,
        }

        sessions = [
            item
            for item in index.get("sessions", [])
            if isinstance(item, dict) and item.get("session_id") != session_id
        ]
        sessions.append(entry)
        index["sessions"] = self._sort_sessions(sessions)
        if make_current:
            index["last_session_id"] = session_id
        self._write_index(index)

    def _sort_sessions(self, sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_sessions = [dict(session) for session in sessions if isinstance(session, dict)]
        normalized_sessions.sort(key=lambda item: str(item.get("session_id") or ""))
        normalized_sessions.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        normalized_sessions.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
        return normalized_sessions

    def _make_title(self, messages: list[ChatMessage]) -> str:
        for message in messages:
            if message.role != "user":
                continue
            title = " ".join(message.content.strip().split())
            if title:
                return title[:40]
        return "New Chat Session"
