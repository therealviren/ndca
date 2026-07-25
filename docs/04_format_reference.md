# NDCA Format Reference

## Document Structure

An NDCA document is a top-level object enclosed in angle brackets.

```ndca
<
[key]="value";
[count]=42;
[items]=(1;2;3);
[nested]=<[child]=true;>;
>
```

## Objects

Objects are written as key/value pairs inside angle brackets.

```ndca
<[name]="Alice";[age]=30;>
```

This parses to:

```python
{
    "name": "Alice",
    "age": 30
}
```

## Lists

Lists are written using parentheses.

```ndca
(1;2;3)
```

Commas may also be accepted by the parser in many cases.

## Strings

Strings use double quotes.

```ndca
"hello"
```

Supported escapes include:

- `\n`
- `\r`
- `\t`
- `\\`
- `\"`
- `\uXXXX`

## Multiline Strings

Triple-quoted strings are supported.

```ndca
"""
Hello
World
"""
```

or:

```ndca
'''
Hello
World
'''
```

## Numbers

The parser supports:

- decimal integers
- floating-point values
- hexadecimal integers
- binary integers
- octal integers

Examples:

```ndca
42
3.14
0xFF
0b1010
0o755
```

## Booleans and Null

The parser recognizes:

- `true`
- `false`
- `null`
- `none`

Boolean matching is case-insensitive by default.

## Comments

Supported comment styles include:

```ndca
// line comment
# line comment
/* block comment */
/* nested /* block */ comment */
<!-- html comment -->
```

## Parent References

A key may include a parent marker before the value:

```ndca
<[child]:parent=<[x]=1;>;>
```

The parser stores the marker as `_parent` on the nested object.

## Metadata Comments

Keys may include inline metadata after `#`:

```ndca
<[name # display label]="Alice";>
```

The parser stores this in `_comments`.

## Binary Data

Binary values may be serialized as Base64 strings using the `@b64:` prefix.

```ndca
"@b64:SGVsbG8="
```
