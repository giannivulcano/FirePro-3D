"""
length_expr.py
==============
The length-input grammar behind :meth:`ScaleManager.parse_dimension`.

Owned by ``docs/specs/units-and-formatting.md`` §3.1 (numbers) and §3.2
(length literals and expressions).  Text is tokenized into length literals,
bare numbers and operators, then evaluated by a small recursive-descent
parser over typed values — never ``eval()``.  Anything it cannot read in
full returns ``None`` so ``DimensionEdit`` reverts to the last valid value
instead of committing a truncated one.
"""

from __future__ import annotations

import math
import re

# The unsigned-number grammar every length literal shares (§3.1).
#
# Accepts a leading dot (".5") and a trailing one ("12."), because both are
# ordinary ways to type a decimal and ``parse_angle`` has always taken them.
# "." is one of ``Model_Space.ENGAGE_CHARS``, so pressing it opens the
# dynamic-input HUD and seeds the field with "." — the keystroke that starts
# a decimal must produce text this grammar accepts.
#
# Deliberately excludes scientific notation and the decimal comma: "1e3" is
# far more likely a typo than 1000, and "1,5" is ambiguous against a
# thousands separator.  Both route to revert-to-last-valid instead.
NUM_PATTERN: str = r"(?:\d+\.?\d*|\.\d+)"

# Longer input is refused outright: it bounds the parser's recursion depth.
_MAX_LEN: int = 200

_INT = r"\d+"
# A number that may carry a fraction: "5 3/8", "3/8", "5.5".  Unsigned — a
# sign is the unary minus operator.
_MIXED = rf"(?:{_INT}\s+{_INT}\s*/\s*{_INT}|{_INT}/{_INT}|{NUM_PATTERN})"
# Inch values also take the drafting hyphen form "6-1/2" (no spaces).
_MIXED_INCH = rf"(?:{_INT}-{_INT}/{_INT}|{_MIXED})"
_FT_MARK = r"(?:'|ft(?![a-z]))"
_IN_MARK = r'(?:"|inches(?![a-z])|inch(?![a-z])|in(?![a-z]))'

# Tried in order at each token start; the first match wins.
_FEET_RE = re.compile(
    rf"({_MIXED})\s*{_FT_MARK}"
    # Optional inch part: "-" directly after the mark is the ft-in
    # separator (drafting rule); " - " with a space before is subtraction.
    rf"(?:(?:-\s*|\s*)({_MIXED_INCH})(?:\s*{_IN_MARK})?)?",
    re.IGNORECASE)
_INCH_RE = re.compile(rf"({_MIXED_INCH})\s*{_IN_MARK}", re.IGNORECASE)
_METRIC_RE = re.compile(rf"({_MIXED})\s*(mm|m)(?![a-z])", re.IGNORECASE)
# A bare "a/b" is left to the "/" operator (same value as the fraction), so
# "10'/2/5" divides left to right instead of reading "2/5" as one literal.
_BARE_RE = re.compile(rf"({_INT}\s+{_INT}\s*/\s*{_INT}|{NUM_PATTERN})")
# Right after a "/" token a bare value is a plain number, whatever the
# spacing: "1/2 3/4" and "1/ 2 3/4" are two fractions side by side (refused),
# never 1 / (2 3/4).  Dividing by a mixed number takes brackets:
# "10' / (2 1/2)" (ratified 2026-10-30, units spec §3.2).
_BARE_AFTER_SLASH_RE = re.compile(rf"({NUM_PATTERN})")

_FRACTION_RE = re.compile(r"(?:(\d+)[\s-]+)?(\d+)\s*/\s*(\d+)")

_OPERATORS = {
    "+": "+", "-": "-", "\u2212": "-",
    "*": "*", "\u00d7": "*",
    "/": "/", "\u00f7": "/",
    "(": "(", ")": ")",
}


class _Reject(Exception):
    """Raised anywhere in tokenizing/evaluation; becomes ``None``."""


def _mixed_value(s: str) -> float:
    """Return the value of a ``_MIXED`` / ``_MIXED_INCH`` match."""
    m = _FRACTION_RE.fullmatch(s.strip())
    if m is None:
        value = float(s)
    else:
        whole, num, den = m.groups()
        if int(den) == 0:
            raise _Reject
        value = (float(whole) if whole else 0.0) + int(num) / int(den)
    if not math.isfinite(value):
        raise _Reject
    return value


def _literal(text: str, pos: int,
             after_slash: bool) -> tuple[tuple[float, bool], int]:
    """Read one literal at *pos*: ``((value, is_length), end)``.

    A length literal's value is in mm; a bare number's is unitless.
    *after_slash* is True when the previous token is ``/``.
    """
    m = _FEET_RE.match(text, pos)
    if m:
        inches = _mixed_value(m.group(1)) * 12.0
        if m.group(2):
            inches += _mixed_value(m.group(2))
        return (inches * 25.4, True), m.end()
    m = _INCH_RE.match(text, pos)
    if m:
        return (_mixed_value(m.group(1)) * 25.4, True), m.end()
    m = _METRIC_RE.match(text, pos)
    if m:
        factor = 1000.0 if m.group(2).lower() == "m" else 1.0
        return (_mixed_value(m.group(1)) * factor, True), m.end()
    m = (_BARE_AFTER_SLASH_RE if after_slash else _BARE_RE).match(text, pos)
    if m:
        return (_mixed_value(m.group(1)), False), m.end()
    raise _Reject


def _tokenize(text: str) -> list:
    """Split *text* into operator strings and ``(value, is_length)`` tuples."""
    tokens: list = []
    i = 0
    while i < len(text):
        c = text[i]
        if c.isspace():
            i += 1
        elif c in _OPERATORS:
            tokens.append(_OPERATORS[c])
            i += 1
        else:
            value, i = _literal(text, i, bool(tokens) and tokens[-1] == "/")
            tokens.append(value)
    return tokens


class _Evaluator:
    """Recursive descent over the token list.

    expr  := term (('+' | '-') term)*
    term  := unary (('*' | '/') unary)*
    unary := '-' unary | primary
    primary := literal | '(' expr ')'

    Values are ``(number, is_length)``.  A bare number meeting a length in
    ``+``/``-`` becomes a length in the default unit; in ``*``/``/`` it is a
    scalar (units spec §3.2).
    """

    def __init__(self, tokens: list, unit_mm: float | None):
        self._tokens = tokens
        self._pos = 0
        self._unit_mm = unit_mm

    def run(self) -> tuple[float, bool]:
        value = self._expr()
        if self._pos != len(self._tokens):
            raise _Reject          # juxtaposed literal or stray ")"
        return value

    def _peek(self):
        return self._tokens[self._pos] if self._pos < len(self._tokens) else None

    def _take(self):
        tok = self._peek()
        if tok is None:
            raise _Reject
        self._pos += 1
        return tok

    def as_length(self, v: tuple[float, bool]) -> float:
        """A value in mm; a bare number takes the default unit."""
        if v[1]:
            return v[0]
        if self._unit_mm is None:
            raise _Reject
        return v[0] * self._unit_mm

    def _expr(self) -> tuple[float, bool]:
        left = self._term()
        while self._peek() in ("+", "-"):
            op = self._take()
            right = self._term()
            if left[1] or right[1]:
                a, b, is_len = self.as_length(left), self.as_length(right), True
            else:
                a, b, is_len = left[0], right[0], False
            left = (a + b if op == "+" else a - b, is_len)
        return left

    def _term(self) -> tuple[float, bool]:
        left = self._unary()
        while self._peek() in ("*", "/"):
            op = self._take()
            right = self._unary()
            if op == "*":
                if left[1] and right[1]:
                    raise _Reject  # length x length is an area
                left = (left[0] * right[0], left[1] or right[1])
            else:
                if right[1] or right[0] == 0:
                    raise _Reject  # ratio, or divide by zero
                left = (left[0] / right[0], left[1])
        return left

    def _unary(self) -> tuple[float, bool]:
        if self._peek() == "-":
            self._take()
            value, is_len = self._unary()
            return (-value, is_len)
        return self._primary()

    def _primary(self) -> tuple[float, bool]:
        tok = self._take()
        if tok == "(":
            value = self._expr()
            if self._take() != ")":
                raise _Reject
            return value
        if isinstance(tok, tuple):
            return tok
        raise _Reject


def evaluate_length(text: str, unit_mm: float | None) -> float | None:
    """Evaluate a length literal or expression to mm.

    Args:
        text: What the user typed, e.g. ``5' 5.5"`` or ``(10' - 6") / 2``.
        unit_mm: mm per bare-number unit (the field's default unit), or
            None when that unit is unknown — then only text whose result
            carries a unit is accepted.

    Returns:
        The length in mm, or None when the text is not fully readable,
        breaks a §3.2 rule, or is not finite.
    """
    text = text.strip()
    if not text or len(text) > _MAX_LEN:
        return None
    try:
        evaluator = _Evaluator(_tokenize(text), unit_mm)
        mm = evaluator.as_length(evaluator.run())
    except _Reject:
        return None
    return mm if math.isfinite(mm) else None
