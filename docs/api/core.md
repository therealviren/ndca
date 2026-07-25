# Core API Reference

## `class NDCA`

The main user-facing document class.

### Constructor

```python
NDCA(filename: Optional[str] = None, autosave: bool = False)
```

### Parameters

- `filename`
  - Optional path to a backing NDCA file.
- `autosave`
  - When enabled, changes are saved automatically in supported workflows.

## File and Persistence Methods

### `file(filename, autosave=None, create=True)`

Attach the instance to a file path.

### `load(filename=None)`

Load a file into memory.

### `save(filename=None, pretty=False)`

Serialize the current document and save it atomically.

### `backup(backup_path)`

Write a backup copy of the current document.

### `hash_write(filename=None, data=None)`

Write a file and a SHA-256 hash sidecar file.

### `verify_hash(filename=None) -> bool`

Verify the file against its `.sha256` hash file.

### `export(path=None, filename=None, merge=False)`

Export the whole document or a sub-object.

### `import_file(filename, merge=True)`

Import an NDCA file and merge or replace the current data.

## Data Access Methods

### `get(path, default=None)`

Read a value by path.

### `get_with_meta(path, default=None)`

Return lookup metadata.

Return format:

```python
{
    "exists": bool,
    "value": Any,
    "type": str | None,
    "path": str
}
```

### `write(path, value)`

Write a value to a path.

### `setdefault(path, default)`

Write a value only if the path does not exist.

### `append(path, value)`

Append a value to a list.

### `remove_from_list(path, value)`

Remove a value from a list.

### `delete(path)`

Delete a value or clear the full document.

### `wipe()`

Clear the entire document.

### `pop(path, default=None)`

Remove and return a value.

### `rename(old_path, new_path)`

Move a value from one path to another.

### `clear_path(path)`

Clear a path using a type-aware reset.

### `update(path, func)`

Transform the current value at a path.

### `incr(path, delta=1)`

Increment a numeric value.

### `toggle(path)`

Toggle a boolean value or create `True` if missing.

### `merge(other)`

Merge another dictionary or `NDCA` object.

### `inherit(child_path, parent_path)`

Merge parent data into child data.

### `exists(path) -> bool`

Check whether a path exists.

### `dump() -> dict`

Return a deep copy of the in-memory document.

### `loads(text) -> dict`

Parse NDCA text into a Python dictionary.

### `dumps(data=None, pretty=False) -> str`

Serialize a Python dictionary into NDCA text.

### `keys() -> list[str]`

Return top-level keys.

### `keys_at(path) -> list[str]`

Return keys from an object at a path.

### `paths() -> list[str]`

Return all reachable paths in the document.

### `count(path) -> int`

Return the length of a list, object, set, or tuple, or `1` for scalar values.

## Miscellaneous Methods

### `add_comment(path, comment)`

Store a comment string for a path.

### `get_comment(path)`

Retrieve a stored comment.

### `diff(other)`

Compare the current data against another dictionary or `NDCA` instance.

### `patch(diff_data)`

Apply a diff structure to the current document.

### `validate(schema)`

Validate the document against a schema.

Return format:

```python
(valid: bool, errors: list[str])
```

### `transaction()`

Create a transaction context manager.

## `Transaction`

Transaction object for grouped changes.

### Usage

```python
with db.transaction():
    db.write("a", 1)
    db.write("b", 2)
```

If an exception is raised inside the transaction, changes are rolled back.
