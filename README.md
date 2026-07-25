# NDCA

NDCA is a lightweight document format and Python library for structured local data storage, retrieval, transformation, and persistence.

It combines a human-readable text format with a path-based API, atomic file writing, transactions, history tracking, tables, query support, diff and patch utilities, validation helpers, and comment metadata support.

## Version

NDCA 5.0.1

## Highlights

- Human-readable nested document format
- Path-based read and write access
- Atomic saves
- Transaction support
- Snapshot history and rollback
- Watchers for change notifications
- Table operations and CSV import/export
- Query and filtering support
- Diff and patch support
- Schema validation
- Comment metadata support
- File-backed persistence

## Quick Example

```python
from ndca import NDCA

db = NDCA("data.ndca", autosave=True)
db.write("user.name", "Alice")
db.write("user.age", 30)

print(db.get("user.name"))
print(db.dumps(pretty=True))
```

## Installation

```bash
pip install ndca
```

## Typical Use Cases

- Local application state
- Configuration storage
- Lightweight document databases
- Table-oriented local data
- Structured file persistence

## Public Entry Points

- `NDCA`
- `Transaction`
- `file`
- `load`
- `save`
- `get`
- `write`
- `merge`
- `query`
- `where`
- `validate`
- `diff`
- `patch`
- `backup`
- `transaction`

## Basic Workflow

1. Create or open a document.
2. Read and write values by path.
3. Save atomically.
4. Use transactions for grouped changes.
5. Use tables, queries, and validation when needed.
