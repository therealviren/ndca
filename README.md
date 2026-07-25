# NDCA
## Nested Data Collection API

NDCA is a modern, lightweight, and reliable Python library for storing, managing, and manipulating nested structured data.

It provides a simple human-readable data format combined with a powerful API for working with objects, lists, files, tables, and structured collections.

Built with safety, performance, and simplicity in mind, NDCA is suitable for scripts, automation tools, applications, and production environments.

---

# Features

- Human-readable structured data format
- Nested object and list support
- Simple path-based data access
- Safe data manipulation
- Atomic file persistence
- Automatic saving support
- Import and export functionality
- Dictionary merging utilities
- List management helpers
- Increment and toggle operations
- Data hashing and integrity checks
- Table-style data management
- CSV support
- Pagination utilities
- Lightweight and dependency-friendly design

---

# Installation

Install NDCA using pip:

    pip install ndca

---

# NDCA Format

NDCA uses a compact structured format designed to be easy to read, write, and process.

Example:

    <[name]="Viren";[age]=12;[active]=true;>

Nested data:

    <[user]=<[name]="Viren";[skills]=("Python";"Bash";)>;>

Supported values:

- Objects
- Lists
- Strings
- Numbers
- Booleans
- Null values
- Nested structures

---

# Basic Usage

    from ndca import NDCA

    db = NDCA()

    db.write(
        "user",
        '<[name]="Viren";[age]=12;>'
    )

    print(db.get("user"))

---

# File Storage

NDCA supports persistent storage through file-based databases.

    from ndca import file

    db = file(
        "database.ndca",
        autosave=True
    )

    db.write("user.name", "Viren")

    print(db.get("user.name"))

---

# Data Operations

NDCA provides a simple API for working with structured data.

## Reading

    get()
    get_with_meta()
    exists()
    keys()
    keys_at()
    paths()

## Writing

    write()
    setdefault()
    update()
    rename()

## Removing

    delete()
    clear_path()
    pop()
    wipe()

---

# Utilities

Built-in helpers for common operations:

    append()
    remove_from_list()
    merge()
    incr()
    toggle()
    count_rows()

---

# Import & Export

NDCA supports saving and loading data in different ways.

    export()
    import_file()

    dump()
    dumps()

    load()
    loads()

    save()

---

# Data Integrity

NDCA includes optional hash verification for safer file handling.

    hash_write()

This helps detect corrupted or modified data files.

---

# Tables

NDCA includes lightweight table utilities for structured row-based data.

Supported features:

- Create tables
- Insert rows
- Find rows
- Update rows
- Delete rows
- Sort data
- Create indexes
- Import CSV files
- Export CSV files

---

# Pagination

Large collections can be handled using built-in pagination support.

Example response:

    {
        "page": 1,
        "per_page": 10,
        "total": 100,
        "items": []
    }

---

# Design Goals

NDCA focuses on:

- Simplicity
- Reliability
- Safe data handling
- Human readability
- Fast operations
- Easy integration

---

# License

See the included license file for usage and distribution terms.