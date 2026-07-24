from typing import Any, Dict, List, Optional, Set
import math
import base64
from collections.abc import Mapping, Sequence


def _to_hex_escape(codepoint: int) -> str:
    return "\\u" + hex(codepoint)[2:].zfill(4)


def _escape_string(s: str) -> str:
    out: List[str] = ['"']
    for ch in s:
        cp = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif 0x20 <= cp <= 0x7E:
            out.append(ch)
        else:
            out.append(_to_hex_escape(cp))
    out.append('"')
    return "".join(out)


def _format_float(f: float) -> str:
    if not math.isfinite(f):
        return "null"
    s = repr(f)
    if "e" in s or "E" in s or "." in s:
        return s
    return s + ".0"


def _ensure_valid_key(k: str) -> str:
    if not isinstance(k, str):
        raise TypeError("keys must be strings")
    if k == "":
        raise TypeError("empty string is not allowed as a key")
    if "\n" in k or "\r" in k:
        raise TypeError("keys must not contain newlines")
    if "[" in k or "]" in k:
        raise TypeError("keys must not contain bracket characters")
    return k


def _serialize_value(value: Any, seen: Optional[Set[int]] = None) -> str:
    if seen is None:
        seen = set()
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return _format_float(value)
    if isinstance(value, str):
        return _escape_string(value)
    vid = id(value)
    if vid in seen:
        raise TypeError("circular reference detected")
    if isinstance(value, (bytes, bytearray)):
        seen.add(vid)
        try:
            b64 = base64.b64encode(bytes(value)).decode("ascii")
            return _escape_string(f"@b64:{b64}")
        finally:
            seen.discard(vid)
    if isinstance(value, Mapping):
        seen.add(vid)
        try:
            return _serialize_mapping(value, seen)
        finally:
            seen.discard(vid)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        seen.add(vid)
        try:
            parts: List[str] = []
            parts.append("(")
            first = True
            for item in value:
                if not first:
                    parts.append(";")
                parts.append(_serialize_value(item, seen))
                first = False
            parts.append(")")
            return "".join(parts)
        finally:
            seen.discard(vid)
    raise TypeError(f"unsupported type: {type(value).__name__}")


def _serialize_mapping(m: Mapping, seen: Optional[Set[int]] = None) -> str:
    if seen is None:
        seen = set()
    vid = id(m)
    if vid in seen:
        raise TypeError("circular reference detected in object")
    seen.add(vid)
    try:
        keys = []
        for k in m.keys():
            if not isinstance(k, str):
                raise TypeError("mapping keys must be strings")
            _ensure_valid_key(k)
            keys.append(k)
        keys_sorted = sorted(keys)
        parts: List[str] = []
        parts.append("<")
        first = True
        for k in keys_sorted:
            if not first:
                pass
            parts.append("[")
            parts.append(k)
            parts.append("]")
            parts.append("=")
            parts.append(_serialize_value(m[k], seen))
            parts.append(";")
            first = False
        parts.append(">")
        return "".join(parts)
    finally:
        seen.discard(vid)


def serialize_object(d: Dict[str, Any]) -> str:
    if not isinstance(d, dict):
        raise TypeError("serialize_object expects a dict")
    return _serialize_mapping(d)