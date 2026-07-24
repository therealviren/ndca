# NDCA
Nested Data Collection API  
Version 4.0.0

---

# INFO

NDCA (Nested Data Collection API) is a fast, secure, and production-ready Python library for storing, reading, and manipulating nested structured data using a compact human-readable format.

NDCA is designed for reliability, atomic persistence, safe in-memory operations, and a simple but powerful API suitable for scripts, services, tools, and applications.

Version **4.0.0** improves the stability of the format, adds more utilities, better serialization, table features, CSV support, pagination helpers, hashing utilities, and stronger internal safety.

---

# FEATURES

Human readable data format  
Nested object support  
List support  
Safe deep copy reads  
Atomic file writing  
Autosave file instances  
Path based nested operations  
Dictionary merging  
List append and removal helpers  
Increment and toggle helpers  
Hash verified writes  
Import and export helpers  
CSV import and export  
Table style data utilities  
Pagination helpers  
Production ready stability  

---

# INSTALLATION

Install with pip.

```
pip install ndca
```

Or include the NDCA module directly in your project.

---

# NDCA FORMAT

NDCA uses a compact structured syntax for storing nested data.

---

# OBJECT FORMAT

```
<[key]="value";[key2]=123;[key3]=true;>
```

---

# LIST FORMAT

```
(value1;value2;value3;)
```

---

# NESTED STRUCTURE

```
<[name]="Viren";[age]=12;[skills]=("Python";"Bash";"NDCA");[settings]=<[theme]="dark";[enabled]=true;>;>
```

---

# FORMAT RULES

Objects start with `<` and end with `>`  
Keys are wrapped in `[key]`  
Key value pairs are separated by `=`  
Each item ends with `;`  
Lists use `( )`  
Strings use `" "`  
Booleans are `true` and `false`  
Null values use `null`  
Nested structures are fully supported  

---

# BASIC USAGE

```python
from ndca import NDCA

store = NDCA()

store.write("user", '<[name]="Viren";[age]=12;>')
store.write("config", '<[enabled]=true;[theme]="dark";>')

print(store.get("user"))
```

Output

```
<[name]="Viren";[age]=12;>
```

---

# FILE STORAGE

```python
from ndca import file

db = file("data.ndca", autosave=True)

db.write("user.name", "Viren")
db.write("user.age", 12)

print(db.get("user.name"))
```

---

# CORE DATA API

## READ

```
get(path, default=None)
get_with_meta(path)
exists(path)
keys()
keys_at(path)
paths()
```

---

## WRITE

```
write(path, value)
setdefault(path, value)
update(path, dict_value)
rename(path, new_name)
```

---

## DELETE

```
delete(path)
clear_path(path)
pop(path)
wipe()
```

---

# LIST UTILITIES

```
append(path, value)
remove_from_list(path, value)
paginate(path, page, per_page)
```

---

# DATA UTILITIES

```
merge(other_dict)
incr(path, amount)
toggle(path)
count_rows(path)
```

---

# IMPORT AND EXPORT

```
export(filename)
import_file(filename)
dump()
dumps()
load(filename)
loads(text)
save(filename)
```

---

# HASH SAFE WRITES

```
hash_write(filename)
```

Writes the NDCA file with a verification hash to ensure integrity.

---

# TABLE UTILITIES

NDCA provides lightweight table features for structured row based data.

---

## CREATE TABLE

```
table_create(path, columns)
```

---

## INSERT ROW

```
table_insert(path, row)
```

---

## GET ROW

```
table_get_row(path, index)
```

---

## FIND ROWS

```
table_find(path, criteria)
```

Criteria can be a dictionary or callable.

---

## UPDATE ROW

```
table_update_row(path, index, updates)
```

---

## DELETE ROW

```
table_delete_row(path, index)
```

---

## TABLE INDEX

```
table_index(path, key, unique=False)
```

---

## SORT TABLE

```
table_sort(path, key, reverse=False)
```

---

## CSV EXPORT

```
table_to_csv(path, filename, include_header=True)
```

---

## CSV IMPORT

```
table_from_csv(path, filename, columns=None)
```

---

# PAGINATION

```python
page = store.paginate("items", page=1, per_page=10)

print(page["items"])
print(page["total"])
```

Pagination returns:

```
page
per_page
total
items
```

---

# VERSION

NDCA Version 4.0.0

---

# EXAMPLE DATA

```
<[user]=<[name]="Viren";[age]=12;>;[settings]=<[theme]="dark";[notifications]=true;>;[skills]=("Python";"Bash";"NDCA");>
```

---

# LICENSE

See the license included in this project.