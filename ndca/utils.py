import os
import tempfile
import io
from typing import Tuple, List, Any, Dict, Optional, Set
from collections.abc import Mapping, Sequence


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
            try:
                os.fchmod(tmp_fd, 0o600)
            except Exception:
                pass
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
                tmp_fd = None
                f.write(data)
                f.flush()
                if fsync:
                    try:
                        os.fsync(f.fileno())
                    except Exception:
                        pass
            try:
                os.replace(tmp_path, path)
            except Exception:
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception:
                    pass
                raise
            if fsync:
                try:
                    dir_fd = os.open(directory, os.O_RDONLY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        try:
                            os.close(dir_fd)
                        except Exception:
                            pass
                except Exception:
                    pass
        finally:
            pass
    finally:
        try:
            if tmp_fd is not None:
                try:
                    os.close(tmp_fd)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
        except Exception:
            pass


def normalize_path(path: str) -> Tuple[List[str], List[int]]:
    if not isinstance(path, str):
        raise ValueError("path must be string")
    p = path.strip()
    if p.startswith("[") and p.endswith("]"):
        p = p[1:-1].strip()
    if p == "":
        return [], []
    i = 0
    n = len(p)
    keys: List[str] = []
    idxs: List[int] = []
    while i < n:
        while i < n and p[i] == ".":
            i += 1
        if i >= n:
            break
        if p[i] == "[":
            i += 1
            j = i
            while j < n and p[j] != "]":
                j += 1
            if j >= n:
                raise ValueError("unterminated bracket")
            inner = p[i:j].strip()
            if inner == "":
                raise ValueError("missing key name before index")
            if "[" in inner or "]" in inner:
                raise ValueError("invalid bracket content")
            keys.append(inner)
            i = j + 1
            continue
        j = i
        while j < n and p[j] not in ".[":
            j += 1
        token = p[i:j].strip()
        if token == "":
            i = j + 1
            continue
        if j < n and p[j] == "[":
            keys.append(token)
            i = j + 1
            k = i
            while k < n and p[k] != "]":
                k += 1
            if k >= n:
                raise ValueError("unterminated index")
            idxtext = p[i:k].strip()
            if idxtext == "":
                idxs.append(-1)
            else:
                try:
                    idxs.append(int(idxtext))
                except Exception:
                    raise ValueError("invalid index")
            i = k + 1
            continue
        keys.append(token)
        i = j
    return keys, idxs


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
        new: Dict[Any, Any] = {}
        _memo[oid] = new
        for k, v in obj.items():
            if isinstance(k, (list, dict, set)):
                raise TypeError("unhashable key type in dict copy")
            new[k] = deepcopy(v, _memo)
        return new
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
        import copy as _copy
        new_obj = _copy.deepcopy(obj, memo=_memo)
        _memo[oid] = new_obj
        return new_obj
    except Exception:
        return obj


def merge_dicts(a: dict, b: dict) -> dict:
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
                if isinstance(target[key], list) and isinstance(val, list):
                    target[key] = deepcopy(target[key]) + deepcopy(val)
                    continue
            target[key] = deepcopy(val)
    return result