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
    if math.isnan(f):
        return '"NaN"'
    if math.isinf(f):
        return '"Infinity"' if f > 0 else '"-Infinity"'
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


def _serialize_value(
    value: Any,
    seen: Optional[Set[int]] = None,
    indent_level: int = 0,
    pretty: bool = False,
    indent_step: int = 2,
) -> str:
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
        return _serialize_mapping(value, seen, indent_level, pretty, indent_step)
    if isinstance(value, (Sequence, set)) and not isinstance(value, (str, bytes, bytearray)):
        seen.add(vid)
        try:
            items = value
            if isinstance(value, set):
                try:
                    items = sorted(value)
                except TypeError:
                    items = sorted(value, key=lambda x: repr(x))
            parts: List[str] = ["("]
            first = True
            for item in items:
                if not first:
                    parts.append("; ")
                parts.append(_serialize_value(item, seen, indent_level, pretty, indent_step))
                first = False
            parts.append(")")
            return "".join(parts)
        finally:
            seen.discard(vid)
    raise TypeError(f"unsupported type: {type(value).__name__}")


def _serialize_mapping(
    m: Mapping,
    seen: Optional[Set[int]] = None,
    indent_level: int = 0,
    pretty: bool = False,
    indent_step: int = 2,
) -> str:
    if seen is None:
        seen = set()
    vid = id(m)
    if vid in seen:
        raise TypeError("circular reference detected in object")
    seen.add(vid)
    try:
        keys = []
        for k in m.keys():
            if k == "_comments" or k == "_parent":
                continue
            if not isinstance(k, str):
                raise TypeError("mapping keys must be strings")
            _ensure_valid_key(k)
            keys.append(k)
        keys_sorted = sorted(keys)
        parts: List[str] = ["<"]
        if pretty and keys_sorted:
            parts.append("\n")
        first = True
        for k in keys_sorted:
            if pretty:
                parts.append(" " * ((indent_level + 1) * indent_step))
            elif not first:
                parts.append(" ")
            parts.append("[")
            parts.append(k)
            parts.append("]=")
            val = m[k]
            parts.append(
                _serialize_value(val, seen, indent_level + 1, pretty, indent_step)
            )
            parts.append(";")
            if pretty:
                parts.append("\n")
            first = False
        if pretty and keys_sorted:
            parts.append(" " * (indent_level * indent_step))
        parts.append(">")
        return "".join(parts)
    finally:
        seen.discard(vid)


def serialize_object(d: Dict[str, Any], pretty: bool = False, indent: int = 2) -> str:
    if not isinstance(d, dict):
        raise TypeError("serialize_object expects a dict")
    return _serialize_mapping(d, pretty=pretty, indent_step=indent)
