# Overview

NDCA is a structured document system designed for local use. It is centered around a nested object model and a custom text format that can be read and written by humans.

The library is organized into four main layers:

- `utils`
- `serializer`
- `parser`
- `core`

## Design Goals

NDCA aims to be:

- readable
- deterministic
- easy to edit manually
- safe for local file persistence
- small enough to embed in applications
- useful for both simple config data and richer local document storage

## Core Ideas

NDCA documents are built from:

- objects, stored as dictionaries
- lists, stored as arrays
- scalar values such as strings, numbers, booleans, null, and binary data

Data is accessed through paths such as:

```python
db.write("user.profile.name", "Alice")
db.write("items[0].id", 123)
```

## Why NDCA

NDCA is useful when you want something more expressive than plain JSON but lighter and more application-oriented than a full database server.

It supports:

- local files
- nested reads and writes
- comment metadata
- transactions
- table abstractions
- diff and patch workflows
- schema validation
- automatic persistence

## Package Structure

```text
ndca/
├── __init__.py
├── core.py
├── parser.py
├── serializer.py
└── utils.py
```
