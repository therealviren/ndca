# Serializer Reference

## `serialize_object(d, pretty=False, indent=2)`

Serialize a Python dictionary into NDCA text.

### Parameters

- `d`
  - Dictionary to serialize.
- `pretty`
  - Enable formatted output.
- `indent`
  - Number of spaces per indentation level when pretty output is enabled.

### Example

```python
from ndca.serializer import serialize_object

text = serialize_object({
    "name": "Alice",
    "age": 30,
    "tags": ["a", "b"]
})
```

### Output

```ndca
<[age]=30; [name]="Alice"; [tags]=("a"; "b");>
```

## Supported Value Types

The serializer supports:

- `None`
- `bool`
- `int`
- `float`
- `str`
- `bytes`
- `bytearray`
- `dict`
- `list`
- `tuple`
- `set`

## Binary Values

Bytes and bytearrays are serialized as Base64 strings with the `@b64:` prefix.

## Deterministic Ordering

Object keys are sorted before serialization.

This helps with:

- stable file output
- predictable diffs
- hash consistency

## Notes

- Circular references raise `TypeError`
- Invalid keys raise `TypeError`
- Metadata keys such as `_comments` and `_parent` are excluded from normal data serialization
