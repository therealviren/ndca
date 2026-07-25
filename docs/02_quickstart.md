# Quick Start

## Create a Document

```python
from ndca import NDCA

db = NDCA()
db.write("app.name", "MyApp")
db.write("app.version", "1.0")
```

## Read a Value

```python
name = db.get("app.name")
print(name)
```

## Write Nested Data

```python
db.write("settings.theme", "dark")
db.write("settings.window.width", 1280)
db.write("settings.window.height", 720)
```

## Work with Lists

```python
db.write("users", [])
db.append("users", {"id": 1, "name": "Alice"})
db.append("users", {"id": 2, "name": "Bob"})
```

## Load from NDCA Text

```python
text = """
<
[title]="Example";
[count]=3;
[active]=true;
>
"""
db.load_from_text(text)
```

## Export to NDCA Text

```python
text = db.dumps(pretty=True)
print(text)
```

## Save to Disk

```python
db.save()
```

## Use a Transaction

```python
with db.transaction():
    db.write("user.name", "Alice")
    db.write("user.age", 30)
```

If an exception is raised in the block, the transaction is rolled back automatically.

## Basic Table Example

```python
db.table_create("users", ["id", "name"])
db.table_insert("users", {"id": 1, "name": "Alice"})
db.table_insert("users", {"id": 2, "name": "Bob"})
