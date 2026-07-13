from __future__ import annotations

import re


TARGET_TYPES = {"phone", "username"}


def validate_target_type(target_type: str | None) -> str:
    value = (target_type or "phone").strip().lower()
    if value not in TARGET_TYPES:
        raise ValueError("Target type must be phone or username")
    return value


def parse_targets(content: bytes | str, target_type: str | None = "phone") -> list[str]:
    target_type = validate_target_type(target_type)
    text = content.decode("utf-8-sig", errors="ignore") if isinstance(content, bytes) else content
    targets: list[str] = []
    seen: set[str] = set()

    for line in text.splitlines():
        target = _parse_phone(line) if target_type == "phone" else _parse_username(line)
        if not target:
            continue
        dedupe_key = target.lower() if target_type == "username" else target
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        targets.append(target)
    return targets


def normalize_username(value: str | None) -> str | None:
    if not value:
        return None
    username = value.strip()
    if username.startswith("@"):
        username = username[1:]
    if not re.fullmatch(r"[A-Za-z0-9_]{3,32}", username):
        return None
    return f"@{username}"


def _parse_phone(line: str) -> str | None:
    match = re.search(r"\+?\d[\d\s().-]{4,}\d", line)
    if not match:
        return None
    phone = re.sub(r"[\s().-]+", "", match.group(0))
    return phone[:32] if phone else None


def _parse_username(line: str) -> str | None:
    value = line.strip()
    link_match = re.fullmatch(r"(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/@?([A-Za-z0-9_]{3,32})/?(?:\?.*)?", value, re.IGNORECASE)
    if link_match:
        return normalize_username(link_match.group(1))
    return normalize_username(value)
