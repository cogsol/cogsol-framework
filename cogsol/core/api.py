from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional
from urllib import error, request


class CogSolAPIError(RuntimeError):
    pass


@dataclass
class CogSolClient:
    base_url: str
    token: Optional[str] = None

    def _url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["x-api-key"] = f"{self.token}"
        return headers

    def request(self, method: str, path: str, payload: Optional[dict[str, Any]] = None) -> Any:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
        req = request.Request(self._url(path), data=body, headers=self._headers(), method=method)
        try:
            with request.urlopen(req) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except error.HTTPError as exc:  # pragma: no cover - I/O
            detail = exc.read().decode("utf-8", errors="ignore")
            raise CogSolAPIError(f"{exc.code} {exc.reason}: {detail}") from exc
        except error.URLError as exc:  # pragma: no cover - I/O
            raise CogSolAPIError(f"Connection error: {exc.reason}") from exc

    # Convenience wrappers -------------------------------------------------
    def _ensure_id(self, data: Any, label: str) -> int:
        if not data or "id" not in data:
            raise CogSolAPIError(f"{label} response did not include an id: {data}")
        return int(data["id"])

    def upsert_script(self, *, remote_id: Optional[int], payload: dict[str, Any]) -> int:
        if remote_id:
            data = self.request("PUT", f"/tools/scripts/{remote_id}/", payload)
        else:
            data = self.request("POST", "/tools/scripts/", payload)
        return self._ensure_id(data, "Script tool")

    def upsert_assistant(self, *, remote_id: Optional[int], payload: dict[str, Any]) -> int:
        if remote_id:
            data = self.request("PUT", f"/assistants/{remote_id}/", payload)
        else:
            data = self.request("POST", "/assistants/", payload)
        return self._ensure_id(data, "Assistant")

    def upsert_common_question(
        self, *, assistant_id: int, remote_id: Optional[int], payload: dict[str, Any]
    ) -> int:
        if remote_id:
            data = self.request(
                "PUT",
                f"/assistants/{assistant_id}/common_questions/{remote_id}/",
                payload,
            )
        else:
            data = self.request("POST", f"/assistants/{assistant_id}/common_questions/", payload)
        if data and "id" in data:
            return int(data["id"])
        if remote_id:
            return int(remote_id)
        # Attempt to resolve by listing
        try:
            listing = self.list_common_questions(assistant_id) or []
            for item in listing:
                if item.get("name") == payload.get("name"):
                    return int(item.get("id"))
        except Exception:
            pass
        raise CogSolAPIError(f"FAQ response did not include an id: {data}")

    def upsert_fixed_response(
        self, *, assistant_id: int, remote_id: Optional[int], payload: dict[str, Any]
    ) -> int:
        if remote_id:
            data = self.request(
                "PUT",
                f"/assistants/{assistant_id}/fixed_questions/{remote_id}/",
                payload,
            )
        else:
            data = self.request("POST", f"/assistants/{assistant_id}/fixed_questions/", payload)
        if data and "id" in data:
            return int(data["id"])
        if remote_id:
            return int(remote_id)
        try:
            listing = self.list_fixed_responses(assistant_id) or []
            for item in listing:
                if item.get("name") == payload.get("name") or item.get("topic") == payload.get(
                    "topic"
                ):
                    return int(item.get("id"))
        except Exception:
            pass
        raise CogSolAPIError(f"Fixed response did not include an id: {data}")

    def upsert_lesson(
        self, *, assistant_id: int, remote_id: Optional[int], payload: dict[str, Any]
    ) -> int:
        if remote_id:
            data = self.request(
                "PUT",
                f"/assistants/{assistant_id}/lessons/{remote_id}/",
                payload,
            )
        else:
            data = self.request("POST", f"/assistants/{assistant_id}/lessons/", payload)
        if data and "id" in data:
            return int(data["id"])
        if remote_id:
            return int(remote_id)
        try:
            listing = self.list_lessons(assistant_id) or []
            for item in listing:
                if item.get("name") == payload.get("name"):
                    return int(item.get("id"))
        except Exception:
            pass
        raise CogSolAPIError(f"Lesson did not include an id: {data}")

    # Chat utilities -------------------------------------------------------
    def create_chat(self, assistant_id: int, message: Optional[str] = None) -> Any:
        payload = {"message": message} if message else {}
        return self.request("POST", f"/assistants/{assistant_id}/chats/", payload or None)

    def send_message(self, chat_id: int, message: str) -> Any:
        return self.request("POST", f"/chats/{chat_id}/", {"message": message})

    def get_chat(self, chat_id: int) -> Any:
        return self.request("GET", f"/chats/{chat_id}/")

    # Deletes --------------------------------------------------------------
    def delete_script(self, script_id: int) -> None:
        self.request("DELETE", f"/tools/scripts/{script_id}/")

    def delete_assistant(self, assistant_id: int) -> None:
        self.request("DELETE", f"/assistants/{assistant_id}/")

    def delete_common_question(self, assistant_id: int, faq_id: int) -> None:
        self.request("DELETE", f"/assistants/{assistant_id}/common_questions/{faq_id}/")

    def delete_fixed_response(self, assistant_id: int, fixed_id: int) -> None:
        self.request("DELETE", f"/assistants/{assistant_id}/fixed_questions/{fixed_id}/")

    def delete_lesson(self, assistant_id: int, lesson_id: int) -> None:
        self.request("DELETE", f"/assistants/{assistant_id}/lessons/{lesson_id}/")

    # Listing helpers ------------------------------------------------------
    def list_common_questions(self, assistant_id: int) -> Any:
        return self.request("GET", f"/assistants/{assistant_id}/common_questions/")

    def list_fixed_responses(self, assistant_id: int) -> Any:
        return self.request("GET", f"/assistants/{assistant_id}/fixed_questions/")

    def list_lessons(self, assistant_id: int) -> Any:
        return self.request("GET", f"/assistants/{assistant_id}/lessons/")

    def get_assistant(self, assistant_id: int) -> Any:
        return self.request("GET", f"/assistants/{assistant_id}/")

    def get_script(self, script_id: int) -> Any:
        return self.request("GET", f"/tools/scripts/{script_id}/")
