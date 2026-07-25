import os
import tempfile
import copy
from typing import Tuple, List, Any, Dict, Optional, Set, Union


def atomic_write(path: str, data: str, fsync: bool = True) -> None:
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    if not isinstance(data, str):
        raise TypeError("data must be a string")
    directory = os.path.dirname(os.path.abspath(path)) or "."
    try:
        os.makedirs(directory, exist_ok=True)
    except Exception:
        pass
    tmp_fd = None
    tmp_path = None
    try:
        tmp_fd, tmp_path = tempfile.mkstemp(prefix=".ndca-", dir=directory)
        try:
            if hasattr(os, "fchmod"):
                try:
                    os.fchmod(tmp_fd, 0o600)
                except Exception:
                    pass
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                tmp_fd = None
                f.write(data)
                f.flush()
                if fsync and hasattr(os, "fsync"):
                    try:
                        os.fsync(f.fileno())
                    except Exception:
                        pass
            os.replace(tmp_path, path)
            tmp_path = None
            if fsync and hasattr(os, "O_RDONLY") and hasattr(os, "open") and hasattr(os, "fsync"):
                try:
                    dir_fd = os.open(directory, os.O_RDONLY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                except Exception:
                    pass
        finally:
            pass
    finally:
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except Exception:
                pass
        if tmp_path is not None and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def normalize_path(path: str) -> List[Union[str, int]]:
    if not isinstance(path, str):
        raise ValueError("path must be string")
    p = path.strip()
    if p == "" or p == ".":
        return []
    if p.startswith("[") and p.endswith("]"):
        p = p[1:-1].strip()
    tokens: List[Union[str, int]] = []
    i = 0
    n = len(p)
    while i < n:
        while i < n and p[i] == ".":
            i += 1
        if i >= n:
            break
        if p[i] == "[":
            i += 1
            j = i
            in_quote = None
            escaped = False
            buf = []
            while j < n:
                ch = p[j]
                if in_quote:
                    if escaped:
                        buf.append(ch)
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == in_quote:
                        in_quote = None
                    else:
                        buf.append(ch)
                else:
                    if ch in ("'", '"'):
                        in_quote = ch
                    elif ch == "]":
                        break
                    else:
                        buf.append(ch)
                j += 1
            if j >= n:
                raise ValueError("unterminated bracket in path")
            inner = "".join(buf).strip()
            i = j + 1
            if inner == "":
                tokens.append(-1)
            else:
                try:
                    tokens.append(int(inner))
                except ValueError:
                    tokens.append(inner)
            continue
        start = i
        while i < n and p[i] not in ".[":
            i += 1
        tok = p[start:i].strip()
        if tok:
            tokens.append(tok)
    return tokens


def deepcopy(obj: Any, _memo: Optional[Dict[int, Any]] = None) -> Any:
    if _memo is None:
        _memo = {}
    oid = id(obj)
    if oid in _memo:
        return _memo[oid]
    if obj is None:
        return None
    if isinstance(obj, (int, float, str, bool, bytes)):
        return obj
    if isinstance(obj, dict):
        new_dict: Dict[Any, Any] = {}
        _memo[oid] = new_dict
        for k, v in obj.items():
            if isinstance(k, (list, dict, set)):
                raise TypeError("unhashable key type in dict copy")
            new_dict[k] = deepcopy(v, _memo)
        return new_dict
    if isinstance(obj, list):
        new_list: List[Any] = []
        _memo[oid] = new_list
        for v in obj:
            new_list.append(deepcopy(v, _memo))
        return new_list
    if isinstance(obj, tuple):
        new_tuple = tuple(deepcopy(v, _memo) for v in obj)
        _memo[oid] = new_tuple
        return new_tuple
    if isinstance(obj, set):
        new_set: Set[Any] = set()
        _memo[oid] = new_set
        for v in obj:
            new_set.add(deepcopy(v, _memo))
        return new_set
    try:
        new_obj = copy.deepcopy(obj, memo=_memo)
        _memo[oid] = new_obj
        return new_obj
    except Exception:
        return obj


def merge_dicts(a: dict, b: dict, concat_lists: bool = True) -> dict:
    if not isinstance(a, dict) or not isinstance(b, dict):
        raise TypeError("merge_dicts expects dicts")
    result = deepcopy(a)
    stack: List[Tuple[Dict[str, Any], Dict[str, Any]]] = [(result, b)]
    while stack:
        target, src = stack.pop()
        for key, val in src.items():
            if key in target:
                if isinstance(target[key], dict) and isinstance(val, dict):
                    stack.append((target[key], val))
                    continue
                if concat_lists and isinstance(target[key], list) and isinstance(val, list):
                    target[key] = deepcopy(target[key]) + deepcopy(val)
                    continue
            target[key] = deepcopy(val)
    return result


def diff_dicts(a: dict, b: dict, path: str = "") -> Dict[str, Any]:
    changes: Dict[str, Any] = {"added": {}, "modified": {}, "removed": {}}
    keys_a = set(a.keys()) if isinstance(a, dict) else set()
    keys_b = set(b.keys()) if isinstance(b, dict) else set()
    for k in keys_b - keys_a:
        p = f"{path}.{k}" if path else k
        changes["added"][p] = deepcopy(b[k])
    for k in keys_a - keys_b:
        p = f"{path}.{k}" if path else k
        changes["removed"][p] = deepcopy(a[k])
    for k in keys_a & keys_b:
        p = f"{path}.{k}" if path else k
        val_a, val_b = a[k], b[k]
        if isinstance(val_a, dict) and isinstance(val_b, dict):
            sub = diff_dicts(val_a, val_b, p)
            changes["added"].update(sub["added"])
            changes["modified"].update(sub["modified"])
            changes["removed"].update(sub["removed"])
        elif val_a != val_b:
            changes["modified"][p] = {"old": deepcopy(val_a), "new": deepcopy(val_b)}
    return changes


def patch_dict(target: dict, diff: dict) -> dict:
    res = deepcopy(target)
    for p in diff.get("removed", {}):
        toks = normalize_path(p)
        curr = res
        for t in toks[:-1]:
            if isinstance(t, str) and isinstance(curr, dict) and t in curr:
                curr = curr[t]
            elif isinstance(t, int) and isinstance(curr, list) and 0 <= t < len(curr):
                curr = curr[t]
        if toks:
            last = toks[-1]
            if isinstance(last, str) and isinstance(curr, dict):
                curr.pop(last, None)
            elif isinstance(last, int) and isinstance(curr, list) and 0 <= last < len(curr):
                curr.pop(last)
    for p, val in diff.get("added", {}).items():
        toks = normalize_path(p)
        curr = res
        for i, t in enumerate(toks[:-1]):
            nxt = toks[i + 1]
            if isinstance(t, str):
                if t not in curr or not isinstance(curr[t], (dict, list)):
                    curr[t] = [] if isinstance(nxt, int) else {}
                curr = curr[t]
            elif isinstance(t, int):
                while len(curr) <= t:
                    curr.append(None)
                if curr[t] is None or not isinstance(curr[t], (dict, list)):
                    curr[t] = [] if isinstance(nxt, int) else {}
                curr = curr[t]
        if toks:
            last = toks[-1]
            if isinstance(last, str) and isinstance(curr, dict):
                curr[last] = deepcopy(val)
            elif isinstance(last, int) and isinstance(curr, list):
                while len(curr) <= last:
                    curr.append(None)
                curr[last] = deepcopy(val)
    for p, mod in diff.get("modified", {}).items():
        val = mod.get("new") if isinstance(mod, dict) and "new" in mod else mod
        toks = normalize_path(p)
        curr = res
        for i, t in enumerate(toks[:-1]):
            nxt = toks[i + 1]
            if isinstance(t, str):
                if t not in curr or not isinstance(curr[t], (dict, list)):
                    curr[t] = [] if isinstance(nxt, int) else {}
                curr = curr[t]
            elif isinstance(t, int):
                while len(curr) <= t:
                    curr.append(None)
                if curr[t] is None or not isinstance(curr[t], (dict, list)):
                    curr[t] = [] if isinstance(nxt, int) else {}
                curr = curr[t]
        if toks:
            last = toks[-1]
            if isinstance(last, str) and isinstance(curr, dict):
                curr[last] = deepcopy(val)
            elif isinstance(last, int) and isinstance(curr, list):
                while len(curr) <= last:
                    curr.append(None)
                curr[last] = deepcopy(val)
    return res


def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    items: List[Tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else str(k)
        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, deepcopy(v)))
    return dict(items)


def unflatten_dict(d: dict, sep: str = ".") -> dict:
    result: Dict[str, Any] = {}
    for k, v in d.items():
        parts = k.split(sep)
        curr = result
        for p in parts[:-1]:
            if p not in curr:
                curr[p] = {}
            curr = curr[p]
        curr[parts[-1]] = deepcopy(v)
    return result


def validate_schema(data: Any, schema: dict) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    if not isinstance(schema, dict):
        return True, errors
    if not isinstance(data, dict):
        return False, ["data is not a dictionary"]
    for field, specs in schema.items():
        if not isinstance(specs, dict):
            continue
        req = specs.get("required", False)
        if req and field not in data:
            errors.append(f"field '{field}' is required")
            continue
        if field in data:
            val = data[field]
            expected_type = specs.get("type")
            if expected_type:
                type_map = {
                    "str": str,
                    "int": int,
                    "float": float,
                    "bool": bool,
                    "dict": dict,
                    "list": list,
                }
                t = type_map.get(expected_type)
                if t and not isinstance(val, t):
                    errors.append(f"field '{field}' must be of type {expected_type}")
    return len(errors) == 0, errors
