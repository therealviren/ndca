# Parser Reference

## `NDCAParseError`

Raised when NDCA text cannot be parsed.

### Properties

- `message`
- `line`
- `col`

Example:

```text
unexpected EOF (line 4, col 12)
```

## `NDCAParser`

Parses NDCA text into Python data structures.

### Constructor

```python
NDCAParser(
    text: str,
    allow_duplicate_keys: bool = False,
    bool_case_insensitive: bool = True,
)
```

### Parameters

- `text`
  - The NDCA source text to parse.
- `allow_duplicate_keys`
  - Allow repeated keys in the same object.
- `bool_case_insensitive`
  - Treat boolean and null-like tokens as case-insensitive.

### Main Method

#### `parse() -> dict`

Parse the document and return the root object.

## Syntax Supported by the Parser

### Objects

```ndca
<[name]="Alice";[age]=30;>
```

### Lists

```ndca
(1;2;3)
```

### Strings

Double-quoted strings are supported with escape sequences.

### Multiline Strings

Triple-quoted multiline strings are supported.

### Comments

The parser supports:

- `//`
- `#`
- `/* ... */`
- `<!-- ... -->`

### Numbers

The parser recognizes:

- decimal integers
- hexadecimal integers
- binary integers
- octal integers
- floating-point values

### Booleans and Null

Recognized tokens:

- `true`
- `false`
- `null`
- `none`

### Parent Markers

If a colon marker is provided before the value, a `_parent` field is attached to the nested object.

### Metadata Comments

Keys may carry metadata after `#`, which is stored under `_comments`.

## Error Handling

The parser reports:

- unterminated objects
- unterminated lists
- unterminated strings
- unterminated comments
- invalid tokens
- duplicate keys
- extra trailing data after the document

Each parse error includes line and column information.
