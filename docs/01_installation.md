# Installation

## Using pip

```bash
pip install ndca
```

## Importing NDCA

```python
from ndca import NDCA
```

## Opening a File

```python
db = NDCA("app.ndca")
```

If the file exists, NDCA loads it. If it does not exist, the file can be created when the document is attached with `file()` or `NDCA.file()`.

## Creating a New Document

```python
db = NDCA()
db.write("project.name", "NDCA")
db.write("project.version", "5.0.3")
```

## Saving Changes

```python
db.save()
```

## Recommended Environment

NDCA is intended for standard Python 3 applications with local filesystem access.

## Notes

- NDCA is designed for local persistence, not a remote database server.
- The document is saved atomically when using the built-in save methods.
- Autosave can be enabled for convenience in interactive or desktop applications.
