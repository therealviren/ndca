from typing import Any, Dict, List, Optional, Tuple, Union, Callable, Generator
import os
import hashlib
import csv
import io
import base64
import ast
import threading
import contextlib
from .parser import NDCAParser, NDCAParseError
from .serializer import serialize_object
from .utils import atomic_write, normalize_path, deepcopy, merge_dicts

version = "4.0.0"

_SENTINEL = object()

class NDCAError(Exception):
    pass

class Transaction:
    def __init__(self, ndca: "NDCA"):
        self._ndca = ndca
        self._backup = None
        self._active = False

    def __enter__(self):
        self._backup = deepcopy(self._ndca._data)
        self._ndca._in_transaction = True
        self._active = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self._ndca._in_transaction = False
        if exc_type is not None:
            self._ndca._data = deepcopy(self._backup)
            self._ndca._dirty = True
        self._active = False
        return False

class NDCA:
    def __init__(self, filename: Optional[str] = None, autosave: bool = False):
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
        if self.autosave and self._dirty and self.filename:
            try:
                self.save()
            except Exception:
                pass

    def __repr__(self) -> str:
        return f"<NDCA keys={len(self._data)} dirty={self._dirty} file={self.filename!r}>"

    def file(self, filename: str, autosave: Optional[bool] = None, create: bool = True):
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
        self.autosave = bool(autosave)
        return self

    def load(self, filename: Optional[str] = None):
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

    def save(self, filename: Optional[str] = None):
        path = filename or self.filename
        if not path:
            raise NDCAError("no filename provided")
        text = self.dumps(self._data)
        atomic_write(path, text)
        self._dirty = False
        return self

    def hash_write(self, filename: Optional[str] = None, data: Optional[str] = None) -> Tuple[str, str]:
        path = filename or self.filename
        if not path:
            raise NDCAError("no filename provided")
        text = (self.dumps(self._data) if data is None else data)
        atomic_write(path, text)
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()
        atomic_write(f"{path}.sha256", h)
        self._dirty = False
        return path, h

    def export(self, path: Optional[str] = None, filename: Optional[str] = None, merge: bool = False):
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

    def _resolve_path(self, path: str) -> Tuple[List[str], List[int]]:
        return normalize_path(path)

    def _navigate_for_get(self, keys: List[str], idxs: List[int]) -> Tuple[bool, Any]:
        node: Any = self._data
        try:
            for k in keys:
                if not isinstance(node, dict):
                    return False, _SENTINEL
                if k not in node:
                    return False, _SENTINEL
                node = node[k]
            if not idxs:
                return True, deepcopy(node)
            if len(idxs) == len(keys):
                node2 = self._data
                for i, k in enumerate(keys):
                    node2 = node2[k]
                    idx = idxs[i]
                    if not isinstance(node2, list):
                        return False, _SENTINEL
                    if idx < 0 or idx >= len(node2):
                        return False, _SENTINEL
                    node2 = node2[idx]
                return True, deepcopy(node2)
            node_final = node
            for idx in idxs:
                if not isinstance(node_final, list):
                    return False, _SENTINEL
                if idx < 0 or idx >= len(node_final):
                    return False, _SENTINEL
                node_final = node_final[idx]
            return True, deepcopy(node_final)
        except Exception:
            return False, _SENTINEL

    def _expr_context(self) -> Dict[str, Any]:
        ctx: Dict[str, Any] = {}
        for k, v in self._data.items():
            if isinstance(k, str) and k.isidentifier():
                ctx[k] = deepcopy(v)
        ctx["get"] = lambda p, d=None: self.get(p, d)
        ctx["query"] = lambda p, c: self.query(p, c)
        return ctx

    def _safe_eval(self, expr: str) -> Any:
        try:
            tree = ast.parse(expr, mode="eval")
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id in ("get", "query"):
                        continue
                    raise NDCAError("function calls are restricted in expressions")
            return eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, self._expr_context())
        except NDCAError:
            raise
        except Exception:
            return expr

    def _resolve_reference(self, value: Any) -> Any:
        if isinstance(value, str) and value.startswith("->"):
            path = value[2:]
            return self.get(path, None)
        return value

    def _resolve_expression(self, value: Any) -> Any:
        if isinstance(value, str) and value.startswith("="):
            expr = value[1:]
            return self._safe_eval(expr)
        if isinstance(value, str) and value.startswith("@expr(") and value.endswith(")"):
            inner = value[6:-1].strip().strip('"').strip("'")
            return self._safe_eval(inner)
        return value

    def _resolve_lazy(self, value: Any) -> Any:
        if isinstance(value, str) and value.startswith("@file(") and value.endswith(")"):
            path = value[6:-1].strip().strip('"').strip("'")
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    try:
                        return self.loads(f.read())
                    except Exception:
                        return f.read()
        return value

    def _resolve_binary(self, value: Any) -> Any:
        if isinstance(value, str) and value.startswith("@binary(") and value.endswith(")"):
            path = value[8:-1].strip().strip('"').strip("'")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    return base64.b64encode(f.read()).decode()
        return value

    def _resolve_embedded_script(self, value: Any) -> Any:
        if isinstance(value, str) and value.startswith("@py(") and value.endswith(")"):
            code = value[4:-1].strip().strip('"').strip("'")
            try:
                return eval(code, {"__builtins__": {}}, self._expr_context())
            except Exception:
                return value
        return value

    def _resolve_value(self, value: Any) -> Any:
        v = deepcopy(value)
        v = self._resolve_reference(v)
        v = self._resolve_lazy(v)
        v = self._resolve_binary(v)
        v = self._resolve_expression(v)
        v = self._resolve_embedded_script(v)
        return deepcopy(v)

    def get(self, path: str, default: Any = None):
        if path is None or path == "":
            return deepcopy(self._data)
        keys, idxs = self._resolve_path(path)
        ok, val = self._navigate_for_get(keys, idxs)
        if not ok:
            return default
        return self._resolve_value(val)

    def get_with_meta(self, path: str, default: Any = None) -> Dict[str, Any]:
        value = self.get(path, _SENTINEL)
        if value is _SENTINEL:
            return {"exists": False, "value": default, "type": None, "path": path}
        return {"exists": True, "value": value, "type": type(value).__name__, "path": path}

    def _ensure_parent_for_write(self, keys: List[str]) -> Tuple[Dict[str, Any], str]:
        if not keys:
            raise NDCAError("invalid path")
        node = self._data
        for k in keys[:-1]:
            if not isinstance(node, dict):
                raise NDCAError("path conflict: not a dict")
            if k not in node:
                node[k] = {}
            elif not isinstance(node[k], dict):
                raise NDCAError("path conflict: existing non-dict")
            node = node[k]
        return node, keys[-1]

    def _record_history(self):
        if self._in_transaction:
            return
        if self._max_history <= 0:
            return
        if len(self._history) >= self._max_history:
            self._history.pop(0)
        self._history.append(deepcopy(self._data))

    def _trigger_watchers(self, path: str, value: Any):
        watchers = []
        for p, callbacks in self._watchers.items():
            if p == path or path.startswith(p + ".") or p.startswith(path + "."):
                watchers.extend(callbacks)
        for cb in list(watchers):
            try:
                cb(path, deepcopy(value))
            except Exception:
                pass

    def write(self, path: str, value: Any):
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
        keys, idxs = self._resolve_path(path)
        if not keys:
            raise NDCAError("invalid path")
        self._record_history()
        node, last_key = self._ensure_parent_for_write(keys)
        if idxs:
            if last_key not in node:
                node[last_key] = []
            if not isinstance(node[last_key], list):
                raise NDCAError("path conflict: target is not a list")
            lst = node[last_key]
            if len(idxs) == len(keys):
                for j, idx in enumerate(idxs):
                    if j == len(idxs) - 1:
                        if idx == -1:
                            lst.append(deepcopy(value))
                        else:
                            if idx < 0:
                                raise NDCAError("negative index not allowed")
                            while idx >= len(lst):
                                lst.append(None)
                            lst[idx] = deepcopy(value)
                    else:
                        while idx >= len(lst):
                            lst.append([])
                        if not isinstance(lst[idx], list):
                            lst[idx] = []
                        lst = lst[idx]
            else:
                for i, idx in enumerate(idxs):
                    if i == len(idxs) - 1:
                        if idx == -1:
                            lst.append(deepcopy(value))
                        else:
                            if idx < 0:
                                raise NDCAError("negative index not allowed")
                            while idx >= len(lst):
                                lst.append(None)
                            lst[idx] = deepcopy(value)
                    else:
                        while idx >= len(lst):
                            lst.append([])
                        if not isinstance(lst[idx], list):
                            lst[idx] = []
                        lst = lst[idx]
        else:
            node[last_key] = deepcopy(value)
        self._dirty = True
        if self.autosave and self.filename:
            self.save()
        self._trigger_watchers(path, value)
        return self

    def setdefault(self, path: str, default: Any):
        if self.exists(path):
            return self.get(path)
        self.write(path, default)
        return default

    def append(self, path: str, value: Any):
        keys, idxs = self._resolve_path(path)
        if not keys:
            raise NDCAError("invalid path for append")
        node, last_key = self._ensure_parent_for_write(keys)
        if last_key not in node:
            node[last_key] = []
        if not isinstance(node[last_key], list):
            raise NDCAError("append target is not a list")
        node[last_key].append(deepcopy(value))
        self._record_history()
        self._dirty = True
        if self.autosave and self.filename:
            self.save()
        self._trigger_watchers(path, value)
        return self

    def remove_from_list(self, path: str, value: Any):
        keys, idxs = self._resolve_path(path)
        if idxs:
            raise NDCAError("remove_from_list expects a list path without index specifiers")
        node = self._data
        for k in keys[:-1]:
            if not isinstance(node, dict) or k not in node:
                return self
            node = node[k]
        last_key = keys[-1]
        if last_key not in node or not isinstance(node[last_key], list):
            return self
        lst = node[last_key]
        try:
            lst.remove(value)
            self._record_history()
            self._dirty = True
            if self.autosave and self.filename:
                self.save()
            self._trigger_watchers(path, value)
        except ValueError:
            pass
        return self

    def delete(self, path: str):
        keys, idxs = self._resolve_path(path)
        if not keys:
            self._record_history()
            self._data = {}
            self._dirty = True
            if self.autosave and self.filename:
                self.save()
            self._trigger_watchers("", {})
            return self
        node = self._data
        for k in keys[:-1]:
            if not isinstance(node, dict) or k not in node:
                return self
            node = node[k]
        last_key = keys[-1]
        if last_key not in node:
            return self
        self._record_history()
        if idxs:
            target = node[last_key]
            if not isinstance(target, list):
                return self
            parent = target
            if len(idxs) == len(keys):
                for i, idx in enumerate(idxs):
                    if not isinstance(parent, list):
                        return self
                    if i == len(idxs) - 1:
                        if 0 <= idx < len(parent):
                            val = parent.pop(idx)
                            self._dirty = True
                            if self.autosave and self.filename:
                                self.save()
                            self._trigger_watchers(path, val)
                    else:
                        if 0 <= idx < len(parent):
                            if not isinstance(parent[idx], list):
                                return self
                            parent = parent[idx]
                        else:
                            return self
            else:
                for i, idx in enumerate(idxs):
                    if not isinstance(parent, list):
                        return self
                    if i == len(idxs) - 1:
                        if 0 <= idx < len(parent):
                            val = parent.pop(idx)
                            self._dirty = True
                            if self.autosave and self.filename:
                                self.save()
                            self._trigger_watchers(path, val)
                    else:
                        if 0 <= idx < len(parent):
                            if not isinstance(parent[idx], list):
                                return self
                            parent = parent[idx]
                        else:
                            return self
        else:
            val = node.pop(last_key, None)
            self._dirty = True
            if self.autosave and self.filename:
                self.save()
            self._trigger_watchers(path, val)
        return self

    def wipe(self):
        self._record_history()
        self._data = {}
        self._dirty = True
        if self.autosave and self.filename:
            self.save()
        self._trigger_watchers("", {})
        return self

    def keys(self) -> List[str]:
        return list(self._data.keys())

    def keys_at(self, path: str) -> List[str]:
        v = self.get(path, _SENTINEL)
        if v is _SENTINEL or not isinstance(v, dict):
            return []
        return list(v.keys())

    def paths(self) -> List[str]:
        out: List[str] = []
        def walk(prefix: str, node: Any):
            if isinstance(node, dict):
                for k, v in node.items():
                    path = f"{prefix}.{k}" if prefix else k
                    out.append(path)
                    walk(path, v)
            elif isinstance(node, list):
                for i, v in enumerate(node):
                    path = f"{prefix}[{i}]" if prefix else f"[{i}]"
                    out.append(path)
                    walk(path, v)
            else:
                return
        walk("", self._data)
        return out

    def exists(self, path: str) -> bool:
        keys, idxs = self._resolve_path(path)
        ok, _ = self._navigate_for_get(keys, idxs)
        return ok

    def dump(self) -> Dict[str, Any]:
        return deepcopy(self._data)

    def load_from_text(self, text: str):
        self._data = self.loads(text)
        if not isinstance(self._data, dict):
            raise NDCAError("loaded content must be an object")
        self._dirty = True
        if self.autosave and self.filename:
            self.save()
        return self

    def merge(self, other: Union[dict, 'NDCA']):
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
        keys, idxs = self._resolve_path(path)
        if not keys:
            return default
        node = self._data
        for k in keys[:-1]:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        last_key = keys[-1]
        if last_key not in node:
            return default
        if idxs:
            target = node[last_key]
            if not isinstance(target, list):
                return default
            parent = target
            if len(idxs) == len(keys):
                for i, idx in enumerate(idxs):
                    if not isinstance(parent, list):
                        return default
                    if i == len(idxs) - 1:
                        if 0 <= idx < len(parent):
                            val = parent.pop(idx)
                            self._record_history()
                            self._dirty = True
                            if self.autosave and self.filename:
                                self.save()
                            return val
                        else:
                            return default
                    else:
                        if 0 <= idx < len(parent):
                            parent = parent[idx]
                        else:
                            return default
            else:
                for i, idx in enumerate(idxs):
                    if not isinstance(parent, list):
                        return default
                    if i == len(idxs) - 1:
                        if 0 <= idx < len(parent):
                            val = parent.pop(idx)
                            self._record_history()
                            self._dirty = True
                            if self.autosave and self.filename:
                                self.save()
                            return val
                        else:
                            return default
                    else:
                        if 0 <= idx < len(parent):
                            parent = parent[idx]
                        else:
                            return default
        else:
            val = node.pop(last_key, default)
            self._record_history()
            self._dirty = True
            if self.autosave and self.filename:
                self.save()
            return val

    def update(self, path: str, func: Callable[[Any], Any]):
        current = self.get(path, _SENTINEL)
        if current is _SENTINEL:
            raise NDCAError("path not found")
        new = func(deepcopy(current))
        self.write(path, new)
        return self

    def incr(self, path: str, delta: int = 1):
        cur = self.get(path, 0)
        if not isinstance(cur, (int, float)):
            raise NDCAError("target is not numeric")
        self.write(path, cur + delta)
        return self.get(path)

    def toggle(self, path: str):
        cur = self.get(path, _SENTINEL)
        if cur is _SENTINEL:
            self.write(path, True)
            return True
        if not isinstance(cur, bool):
            raise NDCAError("target is not boolean")
        self.write(path, not cur)
        return not cur

    def rename(self, old_path: str, new_path: str):
        val = self.get(old_path, _SENTINEL)
        if val is _SENTINEL:
            raise NDCAError("old path not found")
        self.write(new_path, val)
        self.delete(old_path)
        return self

    def clear_path(self, path: str):
        val = self.get(path, _SENTINEL)
        if val is _SENTINEL:
            raise NDCAError("path not found")
        self.write(path, {} if isinstance(val, dict) else None)
        return self

    def count(self, path: str) -> int:
        v = self.get(path, _SENTINEL)
        if v is _SENTINEL:
            return 0
        if isinstance(v, list):
            return len(v)
        if isinstance(v, dict):
            return len(v)
        return 1

    def table_create(self, path: str, columns: Optional[List[str]] = None):
        self.write(path, {"__columns": list(columns or []), "__rows": []})
        return self

    def table_insert(self, path: str, row: Dict[str, Any]):
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
        tbl = self.get(path, _SENTINEL)
        if tbl is _SENTINEL or not isinstance(tbl, dict):
            return None
        rows = tbl.get("__rows", [])
        if 0 <= index < len(rows):
            return deepcopy(rows[index])
        return None

    def table_find(self, path: str, criteria: Union[Dict[str, Any], Callable[[Dict[str, Any]], bool]]) -> List[Dict[str, Any]]:
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

    def table_update_row(self, path: str, index: int, updates: Dict[str, Any]):
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

    def table_sort(self, path: str, key: Union[str, Callable[[Dict[str, Any]], Any]], reverse: bool = False):
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

    def table_to_csv(self, path: str, filename: str, include_header: bool = True):
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

    def table_from_csv(self, path: str, filename: str, columns: Optional[List[str]] = None):
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
        tbl = self.get(path, _SENTINEL)
        if tbl is _SENTINEL:
            v = self.get(path, [])
            if not isinstance(v, list):
                raise NDCAError("target is not a list")
            total = len(v)
            start = (page - 1) * per_page
            end = start + per_page
            return {"page": page, "per_page": per_page, "total": total, "items": deepcopy(v[start:end])}
        if not isinstance(tbl, dict) or "__rows" not in tbl:
            raise NDCAError("target is not a table")
        rows = tbl.get("__rows", [])
        total = len(rows)
        start = (page - 1) * per_page
        end = start + per_page
        return {"page": page, "per_page": per_page, "total": total, "items": deepcopy(rows[start:end])}

    def count_rows(self, path: str) -> int:
        tbl = self.get(path, _SENTINEL)
        if tbl is _SENTINEL:
            v = self.get(path, [])
            return len(v) if isinstance(v, list) else 0
        if not isinstance(tbl, dict) or "__rows" not in tbl:
            return 0
        return len(tbl.get("__rows", []))

    def dumps(self, data: Optional[Dict[str, Any]] = None) -> str:
        d = self._data if data is None else data
        if not isinstance(d, dict):
            raise NDCAError("dumps expects an object")
        return serialize_object(d)

    def loads(self, text: str) -> Dict[str, Any]:
        if not isinstance(text, str):
            raise NDCAError("loads expects a string")
        parser = NDCAParser(text)
        result = parser.parse()
        if not isinstance(result, dict):
            raise NDCAError("parsed content must be an object")
        return result

    def watch(self, path: str, callback: Callable[[str, Any], None]):
        self._watchers.setdefault(path, []).append(callback)
        return self

    def unwatch(self, path: str, callback: Optional[Callable[[str, Any], None]] = None):
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
        return deepcopy(self._history)

    def rollback(self, version: int):
        if version < 0 or version >= len(self._history):
            raise NDCAError("invalid version")
        self._record_history()
        self._data = deepcopy(self._history[version])
        self._dirty = True
        return self

    def query(self, path: str, condition: str) -> List[Any]:
        target = self.get(path, _SENTINEL)
        if target is _SENTINEL:
            return []
        if isinstance(target, dict) and "__rows" in target:
            items = target.get("__rows", [])
        elif isinstance(target, list):
            items = target
        else:
            return []
        out: List[Any] = []
        for item in items:
            try:
                if self._safe_eval(condition if isinstance(condition, str) else str(condition)):
                    pass
            except Exception:
                pass
        results: List[Any] = []
        for item in items:
            ctx = deepcopy(item) if isinstance(item, dict) else {"value": item}
            try:
                tree = ast.parse(condition, mode="eval")
                for node in ast.walk(tree):
                    if isinstance(node, ast.Call):
                        raise NDCAError("function calls are restricted in queries")
                val = eval(compile(tree, "<query>", "eval"), {"__builtins__": {}}, ctx)
                if val:
                    results.append(deepcopy(item))
            except Exception:
                continue
        return results

    def inherit(self, child_path: str, parent_path: str):
        parent = self.get(parent_path, {})
        child = self.get(child_path, {})
        if not isinstance(parent, dict) or not isinstance(child, dict):
            raise NDCAError("inherit requires object targets")
        merged = merge_dicts(parent, child)
        self.write(child_path, merged)
        return self

    def add_comment(self, path: str, comment: str):
        if not isinstance(path, str) or path == "":
            raise NDCAError("invalid path for comment")
        self._comments[path] = comment
        return self

    def get_comment(self, path: str) -> Optional[str]:
        return deepcopy(self._comments.get(path))

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

def dumps(data: Dict[str, Any]) -> str:
    return NDCA().dumps(data)

def export(path: Optional[str] = None, filename: Optional[str] = None, merge: bool = False):
    return _DEFAULT.export(path=path, filename=filename, merge=merge)

def import_file(filename: str, merge: bool = True):
    return _DEFAULT.import_file(filename, merge=merge)

def hash_write(filename: Optional[str] = None, data: Optional[str] = None):
    return _DEFAULT.hash_write(filename=filename, data=data)

def setdefault(path: str, default: Any):
    return _DEFAULT.setdefault(path, default)

def incr(path: str, delta: int = 1):
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

def table_find(path: str, criteria: Union[Dict[str, Any], Callable[[Dict[str, Any]], bool]]):
    return _DEFAULT.table_find(path, criteria)

def table_update_row(path: str, index: int, updates: Dict[str, Any]):
    return _DEFAULT.table_update_row(path, index, updates)

def table_delete_row(path: str, index: int):
    return _DEFAULT.table_delete_row(path, index)

def table_index(path: str, key: str, unique: bool = False):
    return _DEFAULT.table_index(path, key, unique)

def table_sort(path: str, key: Union[str, Callable[[Dict[str, Any]], Any]], reverse: bool = False):
    return _DEFAULT.table_sort(path, key, reverse)

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

def rollback(version: int):
    return _DEFAULT.rollback(version)

def query(path: str, condition: str):
    return _DEFAULT.query(path, condition)

def inherit(child_path: str, parent_path: str):
    return _DEFAULT.inherit(child_path, parent_path)

def add_comment(path: str, comment: str):
    return _DEFAULT.add_comment(path, comment)

def get_comment(path: str):
    return _DEFAULT.get_comment(path)

def transaction() -> Transaction:
    return _DEFAULT.transaction()