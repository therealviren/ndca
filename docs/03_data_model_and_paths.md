# Data Model and Paths

## Data Model

NDCA stores data as a nested structure made from:

- dictionaries for objects
- lists for ordered collections
- scalar values for leaves

Supported values include:

- `None`
- `bool`
- `int`
- `float`
- `str`
- `bytes`
- `bytearray`
- nested dictionaries
- nested lists

## Paths

NDCA uses path strings to address nested values.

### Dot notation

```python
db.get("user.name")
db.write("settings.theme", "dark")
```

### List indexing

```python
db.get("users[0]")
db.write("users[1].name", "Bob")
```

### Mixed paths

```python
db.write("projects[0].tasks[2].title", "Review")
```

## Path Behavior

- Missing intermediate objects may be created automatically during writes.
- List indexes must be valid integers.
- A special index of `-1` may be used for append-like behavior in some write operations.
- Path lookup returns a deep copy of the stored value.

## Special Keys

Internal metadata keys may be used by NDCA:

- `_comments`
- `_parent`

These are used by the parser and runtime metadata handling.

## Common Access Patterns

```python
db.write("profile.name", "Alice")
db.write("profile.age", 30)
db.write("profile.tags", ["admin", "editor"])
print(db.get("profile.tags[0]"))
```

## Notes

Path strings are intended to be readable and easy to type. They are not JSON Pointers and they are not XPath.
