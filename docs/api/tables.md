# Tables, Queries, Transactions, and Validation

## Transactions

Transactions are used when several changes must succeed or fail together.

```python
with db.transaction():
    db.write("user.name", "Alice")
    db.write("user.age", 30)
```

If an exception occurs, the document is restored to its previous state.

## History

NDCA maintains a bounded history of document snapshots.

### `history()`

Return a deep copy of stored snapshots.

### `rollback(version_index)`

Restore a previous snapshot by index.

## Querying

NDCA supports expression-based querying over lists and tables.

### `query(path, condition)`

Evaluate an expression against each item in a collection.

Examples:

```python
db.query("users", "age >= 18")
db.query("users", "status == 'active'")
```

If the path refers to a table, the query operates on `__rows`.

### `where(path, predicate)`

Filter items using a Python callable.

```python
db.where("users", lambda row: row["age"] >= 18)
```

### `find_one(path, condition)`

Return the first item matching the query expression.

## Validation

### `validate(schema)`

Validate the document against a schema definition.

Example:

```python
schema = {
    "user": {
        "required": True,
        "type": "dict"
    },
    "items": {
        "required": False,
        "type": "list"
    }
}

valid, errors = db.validate(schema)
```

Supported schema fields:

- `required`
- `type`

Supported type names:

- `str`
- `int`
- `float`
- `bool`
- `dict`
- `list`

## Notes

- Validation is shallow.
- Nested checks should be performed on sub-objects separately.
- Query expressions should only be used with trusted input.
