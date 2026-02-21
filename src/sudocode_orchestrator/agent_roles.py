from __future__ import annotations

import json
from datetime import datetime
from typing import Callable, cast

from .models import ImplementerResult, ReviewResult, VerificationEvidence

Transport = Callable[[str, str], str]


class RoleAgentAdapter:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def implementer(
        self, rendered_prompt: str, fix_list: list[str] | None
    ) -> ImplementerResult:
        prompt = self._build_implementer_prompt(rendered_prompt, fix_list)
        raw = self._transport("implementer", prompt)
        return self._parse_implementer_output(raw)

    def spec_reviewer(
        self,
        rendered_prompt: str,
        implementer_result: ImplementerResult,
        attempt: int,
    ) -> ReviewResult:
        prompt = self._build_reviewer_prompt(
            role="spec_reviewer",
            rendered_prompt=rendered_prompt,
            implementer_result=implementer_result,
            attempt=attempt,
        )
        raw = self._transport("spec_reviewer", prompt)
        return self._parse_review_output(raw, "spec reviewer")

    def quality_reviewer(
        self,
        rendered_prompt: str,
        implementer_result: ImplementerResult,
        attempt: int,
    ) -> ReviewResult:
        prompt = self._build_reviewer_prompt(
            role="quality_reviewer",
            rendered_prompt=rendered_prompt,
            implementer_result=implementer_result,
            attempt=attempt,
        )
        raw = self._transport("quality_reviewer", prompt)
        return self._parse_review_output(raw, "quality reviewer")

    def _build_implementer_prompt(
        self, rendered_prompt: str, fix_list: list[str] | None
    ) -> str:
        fix_lines = "- (none)"
        if fix_list:
            fix_lines = "\n".join(f"- {item}" for item in fix_list)
        return f"role: implementer\n{rendered_prompt}\n\nfix_list:\n{fix_lines}"

    def _build_reviewer_prompt(
        self,
        *,
        role: str,
        rendered_prompt: str,
        implementer_result: ImplementerResult,
        attempt: int,
    ) -> str:
        verification = "null"
        if implementer_result.verification is not None:
            verification = json.dumps(
                {
                    "command": implementer_result.verification.command,
                    "output": implementer_result.verification.output,
                    "exit_code": implementer_result.verification.exit_code,
                    "produced_at": implementer_result.verification.produced_at.isoformat(),
                },
                sort_keys=True,
            )
        return (
            f"role: {role}\n"
            f"attempt: {attempt}\n"
            f"{rendered_prompt}\n\n"
            "implementer_result:\n"
            f"code_changed_at: {implementer_result.code_changed_at.isoformat()}\n"
            f"notes: {implementer_result.notes}\n"
            f"verification: {verification}"
        )

    def _parse_implementer_output(self, raw: str) -> ImplementerResult:
        payload = self._load_object(raw, "implementer")
        code_changed_at = self._parse_datetime(
            payload.get("code_changed_at"),
            "Malformed implementer output: 'code_changed_at' must be timezone-aware ISO datetime",
        )
        notes = payload.get("notes")
        if not isinstance(notes, str):
            raise ValueError("Malformed implementer output: 'notes' must be a string")

        verification_raw = payload.get("verification")
        verification = None
        if verification_raw is not None:
            if not isinstance(verification_raw, dict):
                raise ValueError(
                    "Malformed implementer output: 'verification' must be an object"
                )
            command = verification_raw.get("command")
            output = verification_raw.get("output")
            exit_code = verification_raw.get("exit_code")
            produced_at = self._parse_datetime(
                verification_raw.get("produced_at"),
                "Malformed implementer output: 'verification.produced_at' must be timezone-aware ISO datetime",
            )
            if not isinstance(command, str):
                raise ValueError(
                    "Malformed implementer output: 'verification.command' must be a string"
                )
            if not isinstance(output, str):
                raise ValueError(
                    "Malformed implementer output: 'verification.output' must be a string"
                )
            if type(exit_code) is not int:
                raise ValueError(
                    "Malformed implementer output: 'verification.exit_code' must be an int"
                )

            verification = VerificationEvidence(
                command=command,
                output=output,
                exit_code=exit_code,
                produced_at=produced_at,
            )

        return ImplementerResult(
            verification=verification,
            code_changed_at=code_changed_at,
            notes=notes,
        )

    def _parse_review_output(self, raw: str, reviewer_name: str) -> ReviewResult:
        payload = self._load_object(raw, reviewer_name)
        passed = payload.get("passed")
        failed_items = payload.get("failed_items")
        fix_list = payload.get("fix_list")
        notes = payload.get("notes")

        if not isinstance(passed, bool):
            raise ValueError(
                f"Malformed {reviewer_name} output: 'passed' must be a bool"
            )
        if not self._is_string_list(failed_items):
            raise ValueError(
                f"Malformed {reviewer_name} output: 'failed_items' must be a list[str]"
            )
        if not self._is_string_list(fix_list):
            raise ValueError(
                f"Malformed {reviewer_name} output: 'fix_list' must be a list[str]"
            )
        if not isinstance(notes, str):
            raise ValueError(
                f"Malformed {reviewer_name} output: 'notes' must be a string"
            )

        failed_items_list = cast(list[str], failed_items)
        fix_list_items = cast(list[str], fix_list)

        return ReviewResult(
            passed=passed,
            failed_items=failed_items_list,
            fix_list=fix_list_items,
            notes=notes,
        )

    def _load_object(self, raw: str, role_name: str) -> dict[str, object]:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed {role_name} output: invalid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Malformed {role_name} output: expected JSON object")
        return payload

    def _parse_datetime(self, value: object, error_message: str) -> datetime:
        if not isinstance(value, str):
            raise ValueError(error_message)
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(error_message) from exc
        if parsed.tzinfo is None:
            raise ValueError(error_message)
        return parsed

    def _is_string_list(self, value: object) -> bool:
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
