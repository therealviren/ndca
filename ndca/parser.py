from typing import Any, Dict, List, Optional, Tuple
import re


class NDCAParseError(Exception):
    def __init__(self, message: str, line: int = 1, col: int = 1):
        super().__init__(f"{message} (line {line}, col {col})")
        self.line = line
        self.col = col
        self.message = message


class NDCAParser:
    def __init__(self, text: str, allow_duplicate_keys: bool = False, bool_case_insensitive: bool = True):
        self.text = text or ""
        self.i = 0
        self.n = len(self.text)
        self.line = 1
        self.col = 1
        self.allow_duplicate_keys = allow_duplicate_keys
        self.bool_case_insensitive = bool(bool_case_insensitive)

    def _peek(self) -> str:
        if self.i < self.n:
            return self.text[self.i]
        return ""

    def _next(self) -> str:
        ch = self._peek()
        if ch:
            self.i += 1
            if ch == "\n":
                self.line += 1
                self.col = 1
            else:
                self.col += 1
        return ch

    def _error(self, msg: str) -> None:
        raise NDCAParseError(msg, line=self.line, col=self.col)

    def _match(self, expected: str) -> bool:
        if self.text.startswith(expected, self.i):
            for _ in expected:
                self._next()
            return True
        return False

    def _skip_whitespace_and_comments(self) -> None:
        while True:
            ch = self._peek()
            if ch == "":
                return
            if ch.isspace():
                self._next()
                continue
            if self._match("//"):
                self._skip_line_comment()
                continue
            if self._match("#"):
                self._skip_line_comment()
                continue
            if self._match("/*"):
                self._skip_block_comment("*/")
                continue
            if self._match("/*/"):
                self._skip_block_comment("*/")
                continue
            if ch == "*":
                self._next()
                self._skip_block_comment("*")
                continue
            if self._match("<!--"):
                self._skip_block_comment("-->")
                continue
            return

    def _skip_line_comment(self) -> None:
        while True:
            ch = self._peek()
            if ch == "" or ch == "\n":
                return
            self._next()

    def _skip_block_comment(self, terminator: str) -> None:
        depth = 1
        term_len = len(terminator)
        while True:
            if self.i >= self.n:
                self._error("unterminated comment")
            if self._match(terminator):
                depth -= 1
                if depth <= 0:
                    return
                continue
            if terminator == "*/" and self._match("/*"):
                depth += 1
                continue
            ch = self._next()
            if ch == "":
                self._error("unterminated comment")

    def parse(self) -> Dict[str, Any]:
        self._skip_whitespace_and_comments()
        if self._peek() != "<":
            self._error("document must start with '<'")
        result = self._parse_object(allow_root=True)
        self._skip_whitespace_and_comments()
        if self.i < self.n:
            rest = self.text[self.i:].strip()
            if rest != "":
                self._error("extra data after document")
        return result

    def _parse_object(self, allow_root: bool = False) -> Dict[str, Any]:
        if self._next() != "<":
            self._error("expected '<' to start object")
        obj: Dict[str, Any] = {}
        meta_comments: Dict[str, str] = {}
        self._skip_whitespace_and_comments()
        while True:
            self._skip_whitespace_and_comments()
            ch = self._peek()
            if ch == "":
                self._error("unterminated object (missing '>')")
            if ch == ">":
                self._next()
                break
            if ch == "[":
                key, key_meta = self._parse_key()
                if key == "":
                    self._error("empty key is not allowed")
                self._skip_whitespace_and_comments()
                parent_marker = None
                if self._match(":"):
                    self._skip_whitespace_and_comments()
                    parent_marker = self._parse_parent_reference()
                    self._skip_whitespace_and_comments()
                if self._next() != "=":
                    self._error("expected '=' after key")
                self._skip_whitespace_and_comments()
                value = self._parse_value()
                if not self.allow_duplicate_keys and key in obj:
                    self._error(f"duplicate key '{key}'")
                if parent_marker is not None:
                    if isinstance(value, dict):
                        value["_parent"] = parent_marker
                    else:
                        obj[key] = value
                obj[key] = value
                if key_meta:
                    meta_comments[key] = key_meta
                self._skip_whitespace_and_comments()
                if self._peek() == ";":
                    self._next()
                    self._skip_whitespace_and_comments()
                    continue
                if self._peek() == ",":
                    self._next()
                    self._skip_whitespace_and_comments()
                    continue
                continue
            else:
                if ch in ";,":
                    self._next()
                    self._skip_whitespace_and_comments()
                    continue
                self._error("expected '[' to start key")
        if meta_comments:
            obj["_comments"] = meta_comments
        return obj

    def _parse_key(self) -> Tuple[str, Optional[str]]:
        if self._next() != "[":
            self._error("expected '[' to start key")
        buf: List[str] = []
        comment_meta: Optional[str] = None
        while True:
            ch = self._peek()
            if ch == "":
                self._error("unterminated key")
            if ch == "]":
                self._next()
                break
            if ch == "\"":
                buf.append(self._parse_quoted_content())
                continue
            if ch == "\\":
                self._next()
                esc = self._next()
                if esc == "":
                    self._error("unterminated escape in key")
                buf.append(esc)
                continue
            if ch == "#":
                self._next()
                comment_meta = self._consume_until("]")
                continue
            buf.append(ch)
            self._next()
        key = "".join(buf).strip()
        return key, comment_meta

    def _consume_until(self, stop_char: str) -> str:
        out: List[str] = []
        while True:
            ch = self._peek()
            if ch == "":
                self._error("unexpected EOF in consume")
            if ch == stop_char:
                return "".join(out).strip()
            out.append(ch)
            self._next()

    def _parse_parent_reference(self) -> str:
        self._skip_whitespace_and_comments()
        ch = self._peek()
        if ch == "\"":
            return self._parse_string()
        return self._parse_token(allow_empty=False)

    def _parse_value(self) -> Any:
        self._skip_whitespace_and_comments()
        ch = self._peek()
        if ch == "":
            self._error("unexpected EOF when parsing value")
        if ch == "\"":
            return self._parse_string()
        if ch == "<":
            return self._parse_object()
        if ch == "(":
            return self._parse_list()
        if self.text.startswith("'''", self.i) or self.text.startswith('"""', self.i):
            return self._parse_multiline_string()
        token = self._parse_token(allow_empty=False)
        if token == "":
            self._error("expected token as value")
        token_for_bool = token
        if self.bool_case_insensitive:
            token_for_bool = token.lower()
        if token_for_bool in ("true", "false", "null"):
            if token_for_bool == "true":
                return True
            if token_for_bool == "false":
                return False
            return None
        num = self._try_parse_number(token)
        if num is not None:
            return num
        return token

    def _parse_quoted_content(self) -> str:
        if self._peek() == "\"":
            self._next()
        buf: List[str] = []
        while True:
            ch = self._next()
            if ch == "":
                self._error("unterminated quoted content")
            if ch == "\\":
                esc = self._next()
                if esc == "":
                    self._error("unterminated escape sequence")
                if esc == "n":
                    buf.append("\n")
                elif esc == "r":
                    buf.append("\r")
                elif esc == "t":
                    buf.append("\t")
                elif esc == "u":
                    hex_digits = ""
                    for _ in range(4):
                        d = self._next()
                        if d == "":
                            self._error("unterminated unicode escape")
                        hex_digits += d
                    try:
                        buf.append(chr(int(hex_digits, 16)))
                    except Exception:
                        buf.append("\\u" + hex_digits)
                elif esc == "x":
                    hex_digits = ""
                    for _ in range(2):
                        d = self._next()
                        if d == "":
                            self._error("unterminated hex escape")
                        hex_digits += d
                    try:
                        buf.append(chr(int(hex_digits, 16)))
                    except Exception:
                        buf.append("\\x" + hex_digits)
                else:
                    buf.append(esc)
                continue
            if ch == "\"":
                break
            buf.append(ch)
        return "".join(buf)

    def _parse_string(self) -> str:
        if self._next() != "\"":
            self._error("expected '\"' to start string")
        buf: List[str] = []
        while True:
            ch = self._next()
            if ch == "":
                self._error("unterminated string")
            if ch == "\\":
                esc = self._next()
                if esc == "":
                    self._error("unterminated escape sequence")
                if esc == "n":
                    buf.append("\n")
                elif esc == "r":
                    buf.append("\r")
                elif esc == "t":
                    buf.append("\t")
                elif esc == "\\":
                    buf.append("\\")
                elif esc == "\"":
                    buf.append("\"")
                elif esc == "u":
                    hex_digits = ""
                    for _ in range(4):
                        d = self._next()
                        if d == "":
                            self._error("unterminated unicode escape")
                        hex_digits += d
                    try:
                        buf.append(chr(int(hex_digits, 16)))
                    except Exception:
                        buf.append("\\u" + hex_digits)
                else:
                    buf.append(esc)
                continue
            if ch == "\"":
                break
            buf.append(ch)
        return "".join(buf)

    def _parse_multiline_string(self) -> str:
        delim = self.text[self.i : self.i + 3]
        for _ in range(3):
            self._next()
        buf: List[str] = []
        while True:
            if self.i >= self.n:
                self._error("unterminated multiline string")
            if self.text.startswith(delim, self.i):
                for _ in range(3):
                    self._next()
                break
            ch = self._next()
            buf.append(ch)
        if buf and buf[0] == "\n":
            return "".join(buf[1:])
        return "".join(buf)

    def _parse_list(self) -> List[Any]:
        if self._next() != "(":
            self._error("expected '(' to start list")
        arr: List[Any] = []
        self._skip_whitespace_and_comments()
        while True:
            self._skip_whitespace_and_comments()
            if self._peek() == "":
                self._error("unterminated list (missing ')')")
            if self._peek() == ")":
                self._next()
                break
            value = self._parse_value()
            arr.append(value)
            self._skip_whitespace_and_comments()
            ch = self._peek()
            if ch == ";":
                self._next()
                self._skip_whitespace_and_comments()
                continue
            if ch == ",":
                self._next()
                self._skip_whitespace_and_comments()
                continue
            if ch == ")":
                self._next()
                break
            continue
        return arr

    def _parse_token(self, allow_empty: bool = False) -> str:
        self._skip_whitespace_and_comments()
        start = self.i
        stop_chars = set(";()<>]=,\"[] \t\r\n")
        while True:
            ch = self._peek()
            if ch == "" or ch.isspace() or ch in stop_chars:
                break
            self._next()
        tok = self.text[start:self.i]
        if not allow_empty and tok == "":
            self._error("expected token")
        return tok

    def _try_parse_number(self, s: str) -> Optional[Any]:
        if s == "":
            return None
        s_strip = s.strip()
        try:
            if re.match(r"^[+-]?0[xX][0-9a-fA-F]+$", s_strip):
                return int(s_strip, 16)
            if re.match(r"^[+-]?0[bB][01]+$", s_strip):
                return int(s_strip, 2)
            if re.match(r"^[+-]?0[oO][0-7]+$", s_strip):
                return int(s_strip, 8)
            if re.match(r"^[+-]?\d+$", s_strip):
                return int(s_strip)
            if re.match(r"^[+-]?\d+\.\d*([eE][+-]?\d+)?$", s_strip) or re.match(
                r"^[+-]?\d+[eE][+-]?\d+$", s_strip
            ):
                return float(s_strip)
        except Exception:
            return None
        return None