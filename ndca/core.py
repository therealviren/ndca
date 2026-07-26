from typing import Any, Dict, List, Optional, Tuple, Union, Callable, Generator
import os
import hashlib
import csv
import io
import base64
import ast
import threading
from .parser import NDCAParser, NDCAParseError
from .serializer import serialize_object
from .utils import (
    atomic_write,
    normalize_path,
    deepcopy,
    merge_dicts,
    diff_dicts,
    patch_dict,
    flatten_dict,
    unflatten_dict,
    validate_schema,
)

version = "5.0.3"

_SENTINEL = object()


class NDCAError(Exception):
    pass


class Transaction:
    def __init__(self, ndca: "NDCA"):
        self._ndca = ndca
        self._backup = None
        self._active = False

    def __enter__(self):
        with self._ndca._lock:
            self._backup = deepcopy(self._ndca._data)
            self._ndca._in_transaction = True
            self._active = True
        return self

    def commit(self):
        with self._ndca._lock:
            if not self._active:
                raise NDCAError("transaction is not active")
            self._backup = None
            self._ndca._in_transaction = False
            self._active = False
            if self._ndca.autosave and self._ndca.filename:
                self._ndca.save()

    def rollback(self):
        with self._ndca._lock:
            if not self._active:
                raise NDCAError("transaction is not active")
            self._ndca._data = deepcopy(self._backup)
            self._ndca._dirty = True
            self._ndca._in_transaction = False
            self._active = False

    def __exit__(self, exc_type, exc, tb):
        with self._ndca._lock:
            if self._active:
                if exc_type is not None:
                    self.rollback()
                else:
                    self.commit()
        return False


class NDCA:
    def __init__(self, filename: Optional[str] = None, autosave: bool = False):
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self.filename: Optional[str] = None
        self.autosave = bool(autosave)
        self._dirty = False
        self._watchers: Dict[str, List[Callable[[str, Any], None]]] = {}
        self._history: List[Dict[str, Any]] = []
        self._max_history: int = 256
        self._in_transaction: bool = False
        self._comments: Dict[str, str] = {}
        if filename:
            self.file(filename, autosave=self.autosave)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        with self._lock:
            if self.autosave and self._dirty and self.filename:
                try:
                    self.save()
                except Exception:
                    pass

    def __repr__(self) -> str:
        with self._lock:
            return f"<NDCA keys={len(self._data)} dirty={self._dirty} file={self.filename!r}>"

    def file(self, filename: str, autosave: Optional[bool] = None, create: bool = True):
        with self._lock:
            if not isinstance(filename, str) or filename == "":
                raise NDCAError("filename must be a non-empty string")
            if autosave is not None:
                self.autosave = bool(autosave)
            self.filename = filename
            if os.path.exists(filename):
                self.load(filename)
            else:
                self._data = {}
                if create:
                    self.save()
            return self

    def set_autosave(self, autosave: bool):
        with self._lock:
            self.autosave = bool(autosave)
            return self

    def load(self, filename: Optional[str] = None):
        with self._lock:
            path = filename or self.filename
            if not path:
                raise NDCAError("no filename provided")
            if not os.path.exists(path):
                raise NDCAError("file not found")
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            parsed = self.loads(text)
            if not isinstance(parsed, dict):
                raise NDCAError("file content must be an object")
            self._data = parsed
            self._dirty = False
            return self

    def save(self, filename: Optional[str] = None, pretty: bool = False):
        with self._lock:
            path = filename or self.filename
            if not path:
                raise NDCAError("no filename provided")
            text = self.dumps(self._data, pretty=pretty)
            atomic_write(path, text)
            self._dirty = False
            return self

    def backup(self, backup_path: str):
        with self._lock:
            text = self.dumps(self._data)
            atomic_write(backup_path, text)
            return backup_path

    def hash_write(self, filename: Optional[str] = None, data: Optional[str] = None) -> Tuple[str, str]:
        with self._lock:
            path = filename or self.filename
            if not path:
                raise NDCAError("no filename provided")
            text = self.dumps(self._data) if data is None else data
            atomic_write(path, text)
            h = hashlib.sha256(text.encode("utf-8")).hexdigest()
            atomic_write(f"{path}.sha256", h)
            self._dirty = False
            return path, h

    def verify_hash(self, filename: Optional[str] = None) -> bool:
        with self._lock:
            path = filename or self.filename
            if not path or not os.path.exists(path):
                return False
            hash_path = f"{path}.sha256"
            if not os.path.exists(hash_path):
                return False
            with open(path, "r", encoding="utf-8") as f:
                data = f.read()
            with open(hash_path, "r", encoding="utf-8") as f:
                expected = f.read().strip()
            actual = hashlib.sha256(data.encode("utf-8")).hexdigest()
            return actual == expected

    def export(self, path: Optional[str] = None, filename: Optional[str] = None, merge: bool = False):
        with self._lock:
            export_data = self._data if path is None else self.get(path, {})
            if not isinstance(export_data, dict):
                raise NDCAError("export target must be an object")
            text = self.dumps(export_data)
            if filename:
                atomic_write(filename, text)
                if merge:
                    src = NDCA().loads(text)
                    self.merge(src)
                return filename
            return text

    def import_file(self, filename: str, merge: bool = True):
        with self._lock:
            if not os.path.exists(filename):
                raise NDCAError("file not found")
            with open(filename, "r", encoding="utf-8") as f:
                text = f.read()
            data = self.loads(text)
            if merge:
                self.merge(data)
            else:
                if not isinstance(data, dict):
                    raise NDCAError("imported content must be an object")
                self._data = data
            self._dirty = True
            if self.autosave and self.filename:
                self.save()
            return self

    def _resolve_path(self, path: str) -> List[Union[str, int]]:
        return normalize_path(path)

    def _navigate_get(self, tokens: List[Union[str, int]]) -> Tuple[bool, Any]:
        curr = self._data
        for tok in tokens:
            if isinstance(tok, str):
                if not isinstance(curr, dict) or tok not in curr:
                    return False, None
                curr = curr[tok]
            elif isinstance(tok, int):
                if not isinstance(curr, list):
                    return False, None
                if tok < 0 or tok >= len(curr):
                    return False, None
                curr = curr[tok]
            else:
                return False, None
        return True, deepcopy(curr)

    def _expr_context(self) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {}
        for k, v in self._data.items():
            if isinstance(k, str) and k.isidentifier():
                ctx[k] = deepcopy(v)
        ctx["get"] = lambda p, d=None: self.get(p, d)
        ctx["query"] = lambda p, c: self.query(p, c)
        return ctx

    def _safe_eval(self, expr: str, local_ctx: Optional[Dict[str, Any]] = None) -> Any:
        try:
            tree = ast.parse(expr, mode="eval")
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in ("get", "query", "len", "str", "int", "float", "bool"):
                        continue
                    raise NDCAError("function calls are restricted in expressions")
            eval_ctx = self._expr_context()
            if local_ctx:
                eval_ctx.update(local_ctx)
            return eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, eval_ctx)
        except NDCAError:
            raise
        except Exception:
            return expr

    def _resolve_value(self, value: Any) -> Any:
        v = deepcopy(value)
        if isinstance(v, str):
            if v.startswith("->"):
                return self.get(v[2:], None)
            if v.startswith("="):
                return self._safe_eval(v[1:])
            if v.startswith("@expr(") and v.endswith(")"):
                inner = v[6:-1].strip().strip('"').strip("'")
                return self._safe_eval(inner)
            if v.startswith("@file(") and v.endswith(")"):
                p = v[6:-1].strip().strip('"').strip("'")
                if os.path.exists(p):
                    with open(p, "r", encoding="utf-8") as f:
                        try:
                            return self.loads(f.read())
                        except Exception:
                            return f.read()
            if v.startswith("@binary(") and v.endswith(")"):
                p = v[8:-1].strip().strip('"').strip("'")
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        return base64.b64encode(f.read()).decode()
            if v.startswith("@py(") and v.endswith(")"):
                code = v[4:-1].strip().strip('"').strip("'")
                try:
                    return eval(code, {"__builtins__": {}}, self._expr_context())
                except Exception:
                    return v
        return v

    def get(self, path: str, default: Any = None):
        with self._lock:
            if path is None or path == "":
                return deepcopy(self._data)
            tokens = self._resolve_path(path)
            ok, val = self._navigate_get(tokens)
            if not ok:
                return default
            return self._resolve_value(val)

    def get_with_meta(self, path: str, default: Any = None) -> Dict[str, Any]:
        with self._lock:
            val = self.get(path, _SENTINEL)
            if val is _SENTINEL:
                return {"exists": False, "value": default, "type": None, "path": path}
            return {"exists": True, "value": val, "type": type(val).__name__, "path": path}

    def _record_history(self):
        if self._in_transaction or self._max_history <= 0:
            return
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(deepcopy(self._data))

    def _trigger_watchers(self, path: str, value: Any):
        watchers = []
        for p, callbacks in self._watchers.items():
            if p == path or path.startswith(p + ".") or p.startswith(path + ".") or p == "*":
                watchers.extend(callbacks)
        for cb in list(watchers):
            try:
                cb(path, deepcopy(value))
            except Exception:
                pass

    def write(self, path: str, value: Any):
        with self._lock:
            if path is None or path == "":
                if not isinstance(value, dict):
                    raise NDCAError("writing top-level requires an object")
                self._record_history()
                self._data = deepcopy(value)
                self._dirty = True
                if self.autosave and self.filename:
                    self.save()
                self._trigger_watchers("", self._data)
                return self
            tokens = self._resolve_path(path)
            if not tokens:
                raise NDCAError("invalid path")
            self._record_history()
            curr = self._data
            for i, tok in enumerate(tokens[:-1]):
                nxt = tokens[i + 1]
                if isinstance(tok, str):
                    if not isinstance(curr, dict):
                        raise NDCAError("path conflict: expected object")
                    if tok not in curr or not isinstance(curr[tok], (dict, list)):
                        curr[tok] = [] if isinstance(nxt, int) else {}
                    curr = curr[tok]
                elif isinstance(tok, int):
                    if not isinstance(curr, list):
                        raise NDCAError("path conflict: expected list")
                    while len(curr) <= tok:
                        curr.append(None)
                    if curr[tok] is None or not isinstance(curr[tok], (dict, list)):
                        curr[tok] = [] if isinstance(nxt, int) else {}
                    curr = curr[tok]
            last = tokens[-1]
            if isinstance(last, str):
                if not isinstance(curr, dict):
                    raise NDCAError("target parent is not an object")
                curr[last] = deepcopy(value)
            elif isinstance(last, int):
                if not isinstance(curr, list):
                    raise NDCAError("target parent is not a list")
                if last == -1:
                    curr.append(deepcopy(value))
                else:
                    if last < 0:
                        raise NDCAError("negative index not allowed")
                    while len(curr) <= last:
                        curr.append(None)
                    curr[last] = deepcopy(value)
            self._dirty = True
            if self.autosave and self.filename:
                self.save()
            self._trigger_watchers(path, value)
            return self

    def setdefault(self, path: str, default: Any):
        with self._lock:
            if self.exists(path):
                return self.get(path)
            self.write(path, default)
            return default

    def append(self, path: str, value: Any):
        with self._lock:
            target = self.get(path, _SENTINEL)
            if target is _SENTINEL:
                self.write(path, [deepcopy(value)])
                return self
            if not isinstance(target, list):
                raise NDCAError("append target is not a list")
            tokens = self._resolve_path(path)
            curr = self._data
            for tok in tokens:
                if isinstance(tok, str) and isinstance(curr, dict):
                    curr = curr[tok]
                elif isinstance(tok, int) and isinstance(curr, list):
                    curr = curr[tok]
            curr.append(deepcopy(value))
            self._record_history()
            self._dirty = True
            if self.autosave and self.filename:
                self.save()
            self._trigger_watchers(path, value)
            return self

    def remove_from_list(self, path: str, value: Any):
        with self._lock:
            tokens = self._resolve_path(path)
            if not tokens:
                return self
            curr = self._data
            for tok in tokens[:-1]:
                if isinstance(tok, str) and isinstance(curr, dict) and tok in curr:
                    curr = curr[tok]
                elif isinstance(tok, int) and isinstance(curr, list) and 0 <= tok < len(curr):
                    curr = curr[tok]
                else:
                    return self
            last = tokens[-1]
            target = curr.get(last) if isinstance(last, str) and isinstance(curr, dict) else None
            if isinstance(target, list):
                try:
                    target.remove(value)
                    self._record_history()
                    self._dirty = True
                    if self.autosave and self.filename:
                        self.save()
                    self._trigger_watchers(path, value)
                except ValueError:
                    pass
            return self

    def delete(self, path: str):
        with self._lock:
            if path is None or path == "":
                self._record_history()
                self._data = {}
                self._dirty = True
                if self.autosave and self.filename:
                    self.save()
                self._trigger_watchers("", {})
                return self
            tokens = self._resolve_path(path)
            if not tokens:
                return self
            curr = self._data
            for tok in tokens[:-1]:
                if isinstance(tok, str) and isinstance(curr, dict) and tok in curr:
                    curr = curr[tok]
                elif isinstance(tok, int) and isinstance(curr, list) and 0 <= tok < len(curr):
                    curr = curr[tok]
                else:
                    return self
            last = tokens[-1]
            removed = None
            if isinstance(last, str) and isinstance(curr, dict) and last in curr:
                self._record_history()
                removed = curr.pop(last)
                self._dirty = True
            elif isinstance(last, int) and isinstance(curr, list) and 0 <= last < len(curr):
                self._record_history()
                removed = curr.pop(last)
                self._dirty = True
            if self._dirty:
                if self.autosave and self.filename:
                    self.save()
                self._trigger_watchers(path, removed)
            return self

    def wipe(self):
        with self._lock:
            self._record_history()
            self._data = {}
            self._dirty = True
            if self.autosave and self.filename:
                self.save()
            self._trigger_watchers("", {})
            return self

    def keys(self) -> List[str]:
        with self._lock:
            return list(self._data.keys())

    def keys_at(self, path: str) -> List[str]:
        with self._lock:
            v = self.get(path, _SENTINEL)
            if v is _SENTINEL or not isinstance(v, dict):
                return []
            return list(v.keys())

    def paths(self) -> List[str]:
        with self._lock:
            out: List[str] = []

            def walk(prefix: str, node: Any):
                if isinstance(node, dict):
                    for k, v in node.items():
                        if k in ("_comments", "_parent"):
                            continue
                        p = f"{prefix}.{k}" if prefix else str(k)
                        out.append(p)
                        walk(p, v)
                elif isinstance(node, list):
                    for i, v in enumerate(node):
                        p = f"{prefix}[{i}]" if prefix else f"[{i}]"
                        out.append(p)
                        walk(p, v)

            walk("", self._data)
            return out

    def exists(self, path: str) -> bool:
        with self._lock:
            tokens = self._resolve_path(path)
            ok, _ = self._navigate_get(tokens)
            return ok

    def dump(self) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._data)

    def load_from_text(self, text: str):
        with self._lock:
            parsed = self.loads(text)
            if not isinstance(parsed, dict):
                raise NDCAError("loaded content must be an object")
            self._data = parsed
            self._dirty = True
            if self.autosave and self.filename:
                self.save()
            return self

    def merge(self, other: Union[dict, "NDCA"]):
        with self._lock:
            src = other._data if isinstance(other, NDCA) else other
            if not isinstance(src, dict):
                raise NDCAError("merge source must be an object")
            self._record_history()
            self._data = merge_dicts(self._data, src)
            self._dirty = True
            if self.autosave and self.filename:
                self.save()
            return self

    def pop(self, path: str, default: Any = None):
        with self._lock:
            tokens = self._resolve_path(path)
            if not tokens:
                return default
            curr = self._data
            for tok in tokens[:-1]:
                if isinstance(tok, str) and isinstance(curr, dict) and tok in curr:
                    curr = curr[tok]
                elif isinstance(tok, int) and isinstance(curr, list) and 0 <= tok < len(curr):
                    curr = curr[tok]
                else:
                    return default
            last = tokens[-1]
            if isinstance(last, str) and isinstance(curr, dict) and last in curr:
                self._record_history()
                val = curr.pop(last)
                self._dirty = True
                if self.autosave and self.filename:
                    self.save()
                return val
            if isinstance(last, int) and isinstance(curr, list) and 0 <= last < len(curr):
                self._record_history()
                val = curr.pop(last)
                self._dirty = True
                if self.autosave and self.filename:
                    self.save()
                return val
            return default

    def update(self, path: str, func: Callable[[Any], Any]):
        with self._lock:
            current = self.get(path, _SENTINEL)
            if current is _SENTINEL:
                raise NDCAError("path not found")
            new_val = func(deepcopy(current))
            self.write(path, new_val)
            return self

    def incr(self, path: str, delta: Union[int, float] = 1):
        with self._lock:
            cur = self.get(path, 0)
            if not isinstance(cur, (int, float)):
                raise NDCAError("target is not numeric")
            res = cur + delta
            self.write(path, res)
            return res

    def toggle(self, path: str):
        with self._lock:
            cur = self.get(path, _SENTINEL)
            if cur is _SENTINEL:
                self.write(path, True)
                return True
            if not isinstance(cur, bool):
                raise NDCAError("target is not boolean")
            new_val = not cur
            self.write(path, new_val)
            return new_val

    def rename(self, old_path: str, new_path: str):
        with self._lock:
            val = self.get(old_path, _SENTINEL)
            if val is _SENTINEL:
                raise NDCAError("old path not found")
            self.write(new_path, val)
            self.delete(old_path)
            return self

    def clear_path(self, path: str):
        with self._lock:
            val = self.get(path, _SENTINEL)
            if val is _SENTINEL:
                raise NDCAError("path not found")
            self.write(path, {} if isinstance(val, dict) else ([] if isinstance(val, list) else None))
            return self

    def count(self, path: str) -> int:
        with self._lock:
            v = self.get(path, _SENTINEL)
            if v is _SENTINEL:
                return 0
            if isinstance(v, (list, dict, set, tuple)):
                return len(v)
            return 1

    def table_create(self, path: str, columns: Optional[List[str]] = None):
        with self._lock:
            self.write(path, {"__columns": list(columns or []), "__rows": []})
            return self

    def table_insert(self, path: str, row: Dict[str, Any]):
        with self._lock:
            if not isinstance(row, dict):
                raise NDCAError("row must be an object")
            tbl = self.get(path, _SENTINEL)
            if tbl is _SENTINEL:
                self.table_create(path, list(row.keys()))
                tbl = self.get(path)
            if not isinstance(tbl, dict) or "__rows" not in tbl:
                raise NDCAError("target is not a table")
            cols = tbl.get("__columns") or []
            row_copy = deepcopy(row)
            for c in list(row_copy.keys()):
                if c not in cols:
                    cols.append(c)
            tbl["__columns"] = cols
            tbl["__rows"].append(row_copy)
            self.write(path, tbl)
            return self

    def table_get_row(self, path: str, index: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            tbl = self.get(path, _SENTINEL)
            if tbl is _SENTINEL or not isinstance(tbl, dict):
                return None
            rows = tbl.get("__rows", [])
            if 0 <= index < len(rows):
                return deepcopy(rows[index])
            return None

    def table_find(
        self,
        path: str,
        criteria: Union[Dict[str, Any], Callable[[Dict[str, Any]], bool]],
    ) -> List[Dict[str, Any]]:
        with self._lock:
            tbl = self.get(path, _SENTINEL)
            if tbl is _SENTINEL or not isinstance(tbl, dict):
                return []
            rows = tbl.get("__rows", [])
            out: List[Dict[str, Any]] = []
            if callable(criteria):
                for r in rows:
                    if criteria(deepcopy(r)):
                        out.append(deepcopy(r))
            else:
                for r in rows:
                    match = True
                    for k, v in criteria.items():
                        if r.get(k) != v:
                            match = False
                            break
                    if match:
                        out.append(deepcopy(r))
            return out

    def table_find_one(
        self,
        path: str,
        criteria: Union[Dict[str, Any], Callable[[Dict[str, Any]], bool]],
    ) -> Optional[Dict[str, Any]]:
        res = self.table_find(path, criteria)
        return res[0] if res else None

    def table_update_row(self, path: str, index: int, updates: Dict[str, Any]):
        with self._lock:
            tbl = self.get(path, _SENTINEL)
            if tbl is _SENTINEL or not isinstance(tbl, dict):
                raise NDCAError("target is not a table")
            rows = tbl.get("__rows", [])
            if not (0 <= index < len(rows)):
                raise NDCAError("row index out of range")
            for k, v in updates.items():
                rows[index][k] = deepcopy(v)
                if k not in tbl.get("__columns", []):
                    tbl["__columns"].append(k)
            tbl["__rows"] = rows
            self.write(path, tbl)
            return self

    def table_delete_row(self, path: str, index: int):
        with self._lock:
            tbl = self.get(path, _SENTINEL)
            if tbl is _SENTINEL or not isinstance(tbl, dict):
                raise NDCAError("target is not a table")
            rows = tbl.get("__rows", [])
            if not (0 <= index < len(rows)):
                raise NDCAError("row index out of range")
            rows.pop(index)
            tbl["__rows"] = rows
            self.write(path, tbl)
            return self

    def table_index(self, path: str, key: str, unique: bool = False) -> Dict[Any, Any]:
        with self._lock:
            tbl = self.get(path, _SENTINEL)
            if tbl is _SENTINEL or not isinstance(tbl, dict):
                return {}
            rows = tbl.get("__rows", [])
            idx: Dict[Any, Any] = {}
            for r in rows:
                k = r.get(key)
                if unique:
                    if k in idx:
                        raise NDCAError("duplicate key for unique index")
                    idx[k] = deepcopy(r)
                else:
                    idx.setdefault(k, []).append(deepcopy(r))
            return idx

    def table_sort(
        self,
        path: str,
        key: Union[str, Callable[[Dict[str, Any]], Any]],
        reverse: bool = False,
    ):
        with self._lock:
            tbl = self.get(path, _SENTINEL)
            if tbl is _SENTINEL or not isinstance(tbl, dict):
                raise NDCAError("target is not a table")
            rows = tbl.get("__rows", [])
            if callable(key):
                rows.sort(key=lambda r: key(deepcopy(r)), reverse=reverse)
            else:
                rows.sort(key=lambda r: r.get(key), reverse=reverse)
            tbl["__rows"] = rows
            self.write(path, tbl)
            return self

    def table_join(
        self,
        path_a: str,
        path_b: str,
        on_key: str,
        out_path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self._lock:
            rows_a = self.get(f"{path_a}.__rows", [])
            rows_b = self.get(f"{path_b}.__rows", [])
            if not isinstance(rows_a, list) or not isinstance(rows_b, list):
                raise NDCAError("join target must be tables")
            joined: List[Dict[str, Any]] = []
            for ra in rows_a:
                for rb in rows_b:
                    if ra.get(on_key) == rb.get(on_key):
                        merged = deepcopy(ra)
                        for k, v in rb.items():
                            if k not in merged:
                                merged[k] = deepcopy(v)
                        joined.append(merged)
            if out_path:
                self.table_create(out_path)
                for j in joined:
                    self.table_insert(out_path, j)
            return joined

    def table_to_csv(self, path: str, filename: str, include_header: bool = True):
        with self._lock:
            tbl = self.get(path, _SENTINEL)
            if tbl is _SENTINEL or not isinstance(tbl, dict):
                raise NDCAError("target is not a table")
            cols = tbl.get("__columns", [])
            rows = tbl.get("__rows", [])
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=cols, extrasaction="ignore")
            if include_header:
                writer.writeheader()
            for r in rows:
                writer.writerow(r)
            atomic_write(filename, output.getvalue())
            return filename

    def table_from_csv(
        self, path: str, filename: str, columns: Optional[List[str]] = None
    ):
        with self._lock:
            if not os.path.exists(filename):
                raise NDCAError("file not found")
            with open(filename, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                cols = columns or reader.fieldnames or []
                self.table_create(path, cols)
                for row in reader:
                    self.table_insert(path, dict(row))
            return self

    def paginate(self, path: str, page: int, per_page: int) -> Dict[str, Any]:
        with self._lock:
            tbl = self.get(path, _SENTINEL)
            if tbl is _SENTINEL:
                v = self.get(path, [])
                if not isinstance(v, list):
                    raise NDCAError("target is not a list")
                total = len(v)
                start = (page - 1) * per_page
                end = start + per_page
                return {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "items": deepcopy(v[start:end]),
                }
            if not isinstance(tbl, dict) or "__rows" not in tbl:
                raise NDCAError("target is not a table")
            rows = tbl.get("__rows", [])
            total = len(rows)
            start = (page - 1) * per_page
            end = start + per_page
            return {
                "page": page,
                "per_page": per_page,
                "total": total,
                "items": deepcopy(rows[start:end]),
            }

    def count_rows(self, path: str) -> int:
        with self._lock:
            tbl = self.get(path, _SENTINEL)
            if tbl is _SENTINEL:
                v = self.get(path, [])
                return len(v) if isinstance(v, list) else 0
            if not isinstance(tbl, dict) or "__rows" not in tbl:
                return 0
            return len(tbl.get("__rows", []))

    def dumps(self, data: Optional[Dict[str, Any]] = None, pretty: bool = False) -> str:
        with self._lock:
            d = self._data if data is None else data
            if not isinstance(d, dict):
                raise NDCAError("dumps expects an object")
            return serialize_object(d, pretty=pretty)

    def loads(self, text: str) -> Dict[str, Any]:
        if not isinstance(text, str):
            raise NDCAError("loads expects a string")
        parser = NDCAParser(text)
        res = parser.parse()
        if not isinstance(res, dict):
            raise NDCAError("parsed content must be an object")
        return res

    def watch(self, path: str, callback: Callable[[str, Any], None]):
        with self._lock:
            self._watchers.setdefault(path, []).append(callback)
            return self

    def unwatch(self, path: str, callback: Optional[Callable[[str, Any], None]] = None):
        with self._lock:
            if path not in self._watchers:
                return self
            if callback is None:
                self._watchers.pop(path, None)
                return self
            try:
                self._watchers[path].remove(callback)
                if not self._watchers[path]:
                    self._watchers.pop(path, None)
            except ValueError:
                pass
            return self

    def history(self) -> List[Dict[str, Any]]:
        with self._lock:
            return deepcopy(self._history)

    def rollback(self, version_index: int):
        with self._lock:
            if version_index < 0 or version_index >= len(self._history):
                raise NDCAError("invalid version index")
            self._record_history()
            self._data = deepcopy(self._history[version_index])
            self._dirty = True
            if self.autosave and self.filename:
                self.save()
            return self

    def query(self, path: str, condition: str) -> List[Any]:
        with self._lock:
            target = self.get(path, _SENTINEL)
            if target is _SENTINEL:
                return []
            if isinstance(target, dict) and "__rows" in target:
                items = target.get("__rows", [])
            elif isinstance(target, list):
                items = target
            else:
                return []
            results: List[Any] = []
            for item in items:
                ctx = deepcopy(item) if isinstance(item, dict) else {"value": item}
                try:
                    val = self._safe_eval(condition, ctx)
                    if bool(val):
                        results.append(deepcopy(item))
                except Exception:
                    continue
            return results

    def where(self, path: str, predicate: Callable[[Any], bool]) -> List[Any]:
        with self._lock:
            target = self.get(path, _SENTINEL)
            if target is _SENTINEL:
                return []
            items = target.get("__rows", []) if isinstance(target, dict) and "__rows" in target else (target if isinstance(target, list) else [])
            return [deepcopy(item) for item in items if predicate(deepcopy(item))]

    def find_one(self, path: str, condition: str) -> Optional[Any]:
        res = self.query(path, condition)
        return res[0] if res else None

    def inherit(self, child_path: str, parent_path: str):
        with self._lock:
            parent = self.get(parent_path, {})
            child = self.get(child_path, {})
            if not isinstance(parent, dict) or not isinstance(child, dict):
                raise NDCAError("inherit requires object targets")
            merged = merge_dicts(parent, child)
            self.write(child_path, merged)
            return self

    def add_comment(self, path: str, comment: str):
        with self._lock:
            if not isinstance(path, str) or path == "":
                raise NDCAError("invalid path for comment")
            self._comments[path] = comment
            return self

    def get_comment(self, path: str) -> Optional[str]:
        with self._lock:
            return deepcopy(self._comments.get(path))

    def diff(self, other: Union[dict, "NDCA"]) -> Dict[str, Any]:
        with self._lock:
            other_data = other._data if isinstance(other, NDCA) else other
            if not isinstance(other_data, dict):
                raise NDCAError("diff comparison expects a dict or NDCA")
            return diff_dicts(self._data, other_data)

    def patch(self, diff_data: dict):
        with self._lock:
            self._record_history()
            self._data = patch_dict(self._data, diff_data)
            self._dirty = True
            if self.autosave and self.filename:
                self.save()
            return self

    def validate(self, schema: dict) -> Tuple[bool, List[str]]:
        with self._lock:
            return validate_schema(self._data, schema)

    def transaction(self) -> Transaction:
        return Transaction(self)


_DEFAULT = NDCA()


def file(filename: str, autosave: bool = False):
    global _DEFAULT
    _DEFAULT = NDCA(filename, autosave=bool(autosave))
    return _DEFAULT


def get(path: str, default: Any = None):
    return _DEFAULT.get(path, default)


def get_with_meta(path: str, default: Any = None):
    return _DEFAULT.get_with_meta(path, default)


def write(path: str, value: Any):
    return _DEFAULT.write(path, value)


def delete(path: str):
    return _DEFAULT.delete(path)


def wipe():
    return _DEFAULT.wipe()


def load(filename: str, autosave: bool = False):
    return file(filename, autosave=autosave)


def save():
    return _DEFAULT.save()


def dump():
    return _DEFAULT.dump()


def keys():
    return _DEFAULT.keys()


def keys_at(path: str):
    return _DEFAULT.keys_at(path)


def paths():
    return _DEFAULT.paths()


def exists(path: str) -> bool:
    return _DEFAULT.exists(path)


def merge(other: Union[dict, NDCA]):
    return _DEFAULT.merge(other)


def append(path: str, value: Any):
    return _DEFAULT.append(path, value)


def remove_from_list(path: str, value: Any):
    return _DEFAULT.remove_from_list(path, value)


def loads(text: str) -> Dict[str, Any]:
    return NDCA().loads(text)


def dumps(data: Dict[str, Any], pretty: bool = False) -> str:
    return NDCA().dumps(data, pretty=pretty)


def export(
    path: Optional[str] = None, filename: Optional[str] = None, merge: bool = False
):
    return _DEFAULT.export(path=path, filename=filename, merge=merge)


def import_file(filename: str, merge: bool = True):
    return _DEFAULT.import_file(filename, merge=merge)


def hash_write(filename: Optional[str] = None, data: Optional[str] = None):
    return _DEFAULT.hash_write(filename=filename, data=data)


def verify_hash(filename: Optional[str] = None) -> bool:
    return _DEFAULT.verify_hash(filename=filename)


def setdefault(path: str, default: Any):
    return _DEFAULT.setdefault(path, default)


def incr(path: str, delta: Union[int, float] = 1):
    return _DEFAULT.incr(path, delta)


def toggle(path: str):
    return _DEFAULT.toggle(path)


def rename(old_path: str, new_path: str):
    return _DEFAULT.rename(old_path, new_path)


def clear_path(path: str):
    return _DEFAULT.clear_path(path)


def pop(path: str, default: Any = None):
    return _DEFAULT.pop(path, default)


def update(path: str, func: Callable[[Any], Any]):
    return _DEFAULT.update(path, func)


def table_create(path: str, columns: Optional[List[str]] = None):
    return _DEFAULT.table_create(path, columns)


def table_insert(path: str, row: Dict[str, Any]):
    return _DEFAULT.table_insert(path, row)


def table_get_row(path: str, index: int):
    return _DEFAULT.table_get_row(path, index)


def table_find(
    path: str, criteria: Union[Dict[str, Any], Callable[[Dict[str, Any]], bool]]
):
    return _DEFAULT.table_find(path, criteria)


def table_find_one(
    path: str, criteria: Union[Dict[str, Any], Callable[[Dict[str, Any]], bool]]
):
    return _DEFAULT.table_find_one(path, criteria)


def table_update_row(path: str, index: int, updates: Dict[str, Any]):
    return _DEFAULT.table_update_row(path, index, updates)


def table_delete_row(path: str, index: int):
    return _DEFAULT.table_delete_row(path, index)


def table_index(path: str, key: str, unique: bool = False):
    return _DEFAULT.table_index(path, key, unique)


def table_sort(
    path: str,
    key: Union[str, Callable[[Dict[str, Any]], Any]],
    reverse: bool = False,
):
    return _DEFAULT.table_sort(path, key, reverse)


def table_join(
    path_a: str, path_b: str, on_key: str, out_path: Optional[str] = None
):
    return _DEFAULT.table_join(path_a, path_b, on_key, out_path)


def table_to_csv(path: str, filename: str, include_header: bool = True):
    return _DEFAULT.table_to_csv(path, filename, include_header)


def table_from_csv(path: str, filename: str, columns: Optional[List[str]] = None):
    return _DEFAULT.table_from_csv(path, filename, columns)


def paginate(path: str, page: int, per_page: int):
    return _DEFAULT.paginate(path, page, per_page)


def count_rows(path: str):
    return _DEFAULT.count_rows(path)


def watch(path: str, callback: Callable[[str, Any], None]):
    return _DEFAULT.watch(path, callback)


def unwatch(path: str, callback: Optional[Callable[[str, Any], None]] = None):
    return _DEFAULT.unwatch(path, callback)


def history():
    return _DEFAULT.history()


def rollback(version_index: int):
    return _DEFAULT.rollback(version_index)


def query(path: str, condition: str):
    return _DEFAULT.query(path, condition)


def where(path: str, predicate: Callable[[Any], bool]):
    return _DEFAULT.where(path, predicate)


def find_one(path: str, condition: str):
    return _DEFAULT.find_one(path, condition)


def inherit(child_path: str, parent_path: str):
    return _DEFAULT.inherit(child_path, parent_path)


def add_comment(path: str, comment: str):
    return _DEFAULT.add_comment(path, comment)


def get_comment(path: str):
    return _DEFAULT.get_comment(path)


def diff(other: Union[dict, NDCA]):
    return _DEFAULT.diff(other)


def patch(diff_data: dict):
    return _DEFAULT.patch(diff_data)


def validate(schema: dict):
    return _DEFAULT.validate(schema)


def backup(backup_path: str):
    return _DEFAULT.backup(backup_path)


def transaction() -> Transaction:
    return _DEFAULT.transaction()
