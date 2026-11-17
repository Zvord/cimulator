"""
Evaluation of GitLab CI expressions, as in `rules:if`.

The expression is parsed, never pasted into Python code, with the semantics
of GitLab (checked against GitLab's pipeline dry run):

- `$VAR` is the value of a variable, or null if it is not defined: an
  undefined variable differs from an empty one. `${VAR}` is invalid.
- `"text"` and `'text'` are strings, taken as written: there are no escapes.
  `null` is null. Any other word, or a number, is invalid.
- `/regex/flags` is a regular expression of at least two characters, with
  the flags `i`, `m`, `s` and `U`, in GitLab's syntax (RE2), translated to
  Python's: `$` without `m` is only the end of the text, `\\d`, `\\w`, `\\s`
  and `\\b` are ASCII, `a{,3}` and `a{01}` are text, `\\12` is octal,
  `\\Q...\\E`, `\\x{...}`, `(?<name>...)` and POSIX classes work.
  Lookarounds, backreferences, atomic groups, possessive quantifiers and
  repetitions over 1000 are invalid.
- `==` and `!=` compare values exactly.
- `=~` and `!~` match the left value (an undefined one is "") against the
  right one: a regex, or a string whose whole value is `/regex/flags`
  (e.g. a variable holding the pattern), where any text without a newline,
  even empty or with slashes, can be the regex; any other string must be equal, and null
  matches nothing.
- `!` negates, and binds tighter than the comparisons, which bind tighter
  than `&&`, which binds tighter than `||`. Parentheses group.
- `&&` and `||` return one of their operands, as in Ruby: only null and
  false are false there, so `"" || $A` is "". The right operand is not
  evaluated when the left one decides.
- A match that cannot be evaluated here (see UnsupportedExpression) only
  makes the expression unsupported if its result depends on the match:
  `$A =~ /\\p{L}/ || $B == "x"` is true when `$B` is "x".
- A variable defined without a value (`FOO:`) is empty, not null. A
  variable written as a mapping has its `value`, or is empty without one.
- The expression is true if its value is not null, false or blank text.
"""
import re
from dataclasses import dataclass
from functools import partial
from typing import Any, List, Optional, Tuple

from cimulator.types import VariablesDict
from cimulator.variable_expander import variable_value


class ExpressionError(ValueError):
    """An expression that GitLab would reject: invalid syntax or regex."""


class UnsupportedExpression(ValueError):
    """A valid expression that cannot be evaluated here."""


@dataclass(frozen=True)
class Regex:
    """A regular expression, as written in an expression."""
    source: str
    flags: str


TOKEN = re.compile(r"""
    (?P<space>\s+)
  | (?P<operator>&&|\|\||==|!=|=~|!~|!|\(|\))
  | (?P<variable>\$\w+)
  | (?P<string>"[^"]*"|'[^']*')
  | (?P<null>null\b)
  | (?P<regex>/(?:\\.|[^/\\])*/[A-Za-z]*)
""", re.VERBOSE)

REGEX = re.compile(r"/(?P<source>(?:\\.|[^/\\])*)/(?P<flags>[A-Za-z]*)\Z", re.DOTALL)
# A string used as a pattern: any text between the slashes, but no newline
PATTERN = re.compile(r"/(?P<source>.*)/(?P<flags>[ismU]*)")

# RE2's classes are ASCII, Python's Unicode: they are written out
ASCII_CLASSES = {"d": "0-9", "w": "0-9A-Za-z_", "s": r"\t\n\f\r "}
WORD = "[0-9A-Za-z_]"
WORD_BOUNDARY = {
    "b": f"(?:(?<={WORD})(?!{WORD})|(?<!{WORD})(?={WORD}))",
    "B": f"(?:(?<={WORD})(?={WORD})|(?<!{WORD})(?!{WORD}))",
}
POSIX_CLASSES = {
    "alpha": "A-Za-z", "digit": "0-9", "alnum": "0-9A-Za-z", "upper": "A-Z",
    "lower": "a-z", "space": r"\t\n\v\f\r ", "word": "0-9A-Za-z_",
    "xdigit": "0-9A-Fa-f", "punct": r"!-/:-@\[-`{-~", "blank": r"\t ",
    "cntrl": r"\x00-\x1f\x7f", "print": " -~", "graph": "!-~", "ascii": r"\x00-\x7f",
}
POSIX_CLASS = re.compile(r"\[:(\^?)(\w+):\]")
REPETITION = re.compile(r"\{(\d*)(?:(,)(\d*))?\}")
# RE2 does not read a repetition count of 100000000 or more: the braces are text
MAX_COUNT_DIGITS = 8
MAX_REPETITION = 1000
FLAG_GROUP = re.compile(r"\(\?([A-Za-z-]*)([:)])")


def parse_regex(text: str) -> Optional[Regex]:
    """The regex written as `text` (`/source/flags`), or None if it is not one."""
    match = REGEX.match(text)
    if not match or len(match["source"]) < 2 or set(match["flags"]) - set("ismU"):
        return None
    return Regex(match["source"], match["flags"])


def parse_pattern(text: str) -> Optional[Regex]:
    """The regex a string used as a pattern is written as, or None if it is not one."""
    match = PATTERN.fullmatch(text)
    return Regex(match["source"], match["flags"]) if match else None


def hex_escape(source: str, i: int) -> tuple:
    """The character of the escape `\\x{...}` at `i`, and the index after it."""
    end = source.find("}", i)
    digits = source[i + 3:end]
    if end < 0 or not re.fullmatch(r"[0-9A-Fa-f]+", digits) or int(digits, 16) > 0x10FFFF:
        raise re.error(f"invalid escape {source[i:end + 1 if end >= 0 else len(source)]}")
    return chr(int(digits, 16)), end + 1


def octal_escape(source: str, i: int) -> tuple:
    """
    The character of the octal escape at `i` (`\\0`, or `\\1` to `\\7` followed
    by an octal digit, of up to three digits), and the index after it.
    A backreference (`\\1` alone) or `\\8` is invalid, as in RE2.
    """
    digits = re.match(r"[0-7]{1,3}", source[i + 1:])
    if not digits or digits[0][0] != "0" and len(digits[0]) == 1:
        raise re.error(f"\\{source[i + 1]} is not supported by GitLab")
    return chr(int(digits[0], 8)), i + 1 + len(digits[0])


def repetition_at(source: str, i: int) -> "Optional[re.Match[str]]":
    """
    The repetition `{n}`, `{n,}` or `{n,m}` at source[i], or None if RE2
    reads the brace as text (e.g. a{,3}, a{01} or a count of 9 digits).
    """
    repetition = REPETITION.match(source, i)
    if not repetition or not repetition[1]:
        return None
    numbers = [n for n in repetition.group(1, 3) if n]
    if any(len(n) > MAX_COUNT_DIGITS or len(n) > 1 and n[0] == "0" for n in numbers):
        return None
    return repetition


def check_nested_repetitions(source: str) -> None:
    """
    Raise re.error, as RE2 rejects the regex, if nested repetitions multiply
    past 1000, e.g. (a{11}){100}. `{n,m}` counts m and `{n,}` n, while `*`,
    `+` and `?` do not count; repetitions side by side do not multiply.
    """
    frames = [1]  # the largest product inside each open group
    last = 1      # the product of the last atom
    i = 0
    while i < len(source):
        char = source[i]
        if char == "\\":
            if source.startswith("Q", i + 1):
                end = source.find("\\E", i + 2)
                i = len(source) if end < 0 else end + 2
            elif source.startswith("{", i + 2) and source[i + 1] in "xpP":
                end = source.find("}", i)
                i = len(source) if end < 0 else end + 1
            else:
                i += 2
            last = 1
            continue
        if char == "[":
            i = class_end(source, i)
            last = 1
            continue
        if char == "(":
            frames.append(1)
            last = 1
        elif char == ")":
            inner = frames.pop() if len(frames) > 1 else 1
            frames[-1] = max(frames[-1], inner)
            last = inner
        elif char == "{" and (repetition := repetition_at(source, i)) is not None:
            product = last * max(int(n) for n in repetition.group(1, 3) if n)
            if product > MAX_REPETITION:
                raise re.error(f"nested repetitions up to {repetition[0]} are over {MAX_REPETITION}")
            frames[-1] = max(frames[-1], product)
            last = product
            i = repetition.end()
            continue
        elif char not in "*+?":
            last = 1
        i += 1


def python_regex(source: str, multiline: bool, notes: Optional[set] = None) -> str:
    """
    Translate a regex from GitLab's syntax (RE2) to Python's, for a match
    with or without the `m` flag. Raises re.error for what RE2 rejects, and
    UnsupportedExpression for what cannot be matched as RE2 does. `notes`,
    if given, gets "any byte" if the regex uses \\C (not as text, e.g. in
    \\Q...\\E): see uses_any_byte().
    """
    check_nested_repetitions(source)
    result = []
    i = 0
    while i < len(source):
        char = source[i]
        if char == "\\" and i + 1 < len(source):
            escaped = source[i + 1]
            if escaped == "Q":
                end = source.find("\\E", i + 2)
                end = len(source) if end < 0 else end
                result.append(re.escape(source[i + 2:end]))
                i = end + 2
                continue
            if source.startswith("x{", i + 1):
                char, i = hex_escape(source, i)
                result.append(re.escape(char))
                continue
            if escaped.isdigit():
                char, i = octal_escape(source, i)
                result.append(re.escape(char))
                continue
            if escaped in ASCII_CLASSES:
                result.append(f"[{ASCII_CLASSES[escaped]}]")
            elif escaped.lower() in ASCII_CLASSES:
                result.append(f"[^{ASCII_CLASSES[escaped.lower()]}]")
            elif escaped == "z":
                result.append(r"\Z")
            elif escaped in WORD_BOUNDARY:
                result.append(WORD_BOUNDARY[escaped])
            elif escaped == "Z":
                raise re.error(f"\\{escaped} is not supported by GitLab")
            elif escaped == "C":
                # Any byte: any character on ASCII text (see matches())
                result.append(r"[\s\S]")
                if notes is not None:
                    notes.add("any byte")
            elif escaped in "pP":
                raise UnsupportedExpression(f"the Unicode class \\{escaped} in /{source}/")
            else:
                result.append(source[i:i + 2])
            i += 2
            continue
        if char == "[":
            end = class_end(source, i)
            result.append(python_class(source[i:end]))
            i = end
            continue
        if char == "$":
            # Without m, $ is only the end of the text; Python's also matches
            # before a final newline
            result.append("$" if multiline else r"\Z")
            i += 1
            continue
        if char == "{":
            repetition = repetition_at(source, i)
            counts = [int(n) for n in (repetition.group(1, 3) if repetition else ()) if n]
            if not repetition:
                # Not a repetition in RE2 (e.g. a{,3} or a{01}): text
                result.append(r"\{")
                i += 1
                continue
            if any(n > MAX_REPETITION for n in counts):
                raise re.error(f"repetition {repetition[0]} is over {MAX_REPETITION}")
            if source.startswith("+", repetition.end()):
                raise re.error("possessive quantifiers are not supported by GitLab")
            result.append(repetition[0])
            i = repetition.end()
            continue
        if source.startswith("(?", i):
            if source.startswith(("(?=", "(?!", "(?<=", "(?<!"), i):
                raise re.error("lookarounds are not supported by GitLab")
            if source.startswith(("(?>", "(?P=", "(?#"), i):
                raise re.error(f"{source[i:i + 3]} is not supported by GitLab")
            named = re.match(r"\(\?P?<(\w+)>", source[i:])
            if named:
                result.append(f"(?P<{named[1]}>")
                i += named.end()
                continue
            flags = FLAG_GROUP.match(source, i)
            if flags and flags[1]:
                letters = flags[1].replace("-", "")
                if set(letters) - set("imsU"):
                    raise re.error(f"unknown flags (?{flags[1]})")
                leading = i == 0 and flags[2] == ")" and "-" not in flags[1]
                # Python has no U flag, and only global flags, at the start;
                # m changes how $ is translated, so only a leading one is known
                if "U" in letters or not leading and (flags[2] == ")" or "m" in letters):
                    raise UnsupportedExpression(f"the flags (?{flags[1]}) in /{source}/")
        if char in "*+?" and source.startswith("+", i + 1) and not (i and source[i - 1] == "("):
            raise re.error("possessive quantifiers are not supported by GitLab")
        result.append(char)
        i += 1
    return "".join(result)


def class_end(source: str, start: int) -> int:
    """The index after the character class starting at `start`."""
    i = start + 1
    if source.startswith("^", i):
        i += 1
    if source.startswith("]", i):
        i += 1
    while i < len(source):
        if source[i] == "\\":
            i += 2
            continue
        posix = POSIX_CLASS.match(source, i)
        if posix:
            i = posix.end()
            continue
        if source[i] == "]":
            return i + 1
        i += 1
    raise re.error("missing ]")


def python_class(text: str) -> str:
    """Translate a character class, `[...]`, from RE2 to Python."""
    negated_posix = re.fullmatch(r"\[\[:\^(\w+):\]\]", text)
    if negated_posix:
        return f"[^{posix_class(negated_posix[1])}]"
    result = []
    i = 1
    while i < len(text) - 1:
        if text[i] == "\\":
            escaped = text[i + 1]
            if escaped in ASCII_CLASSES:
                result.append(ASCII_CLASSES[escaped])
            elif escaped.lower() in ASCII_CLASSES or escaped in "pPQ":
                raise UnsupportedExpression(f"\\{escaped} in the class {text}")
            elif escaped == "x" and text.startswith("{", i + 2):
                char, i = hex_escape(text, i)
                result.append(re.escape(char))
                continue
            elif escaped.isdigit():
                char, i = octal_escape(text, i)
                result.append(re.escape(char))
                continue
            else:
                result.append(text[i:i + 2])
            i += 2
            continue
        posix = POSIX_CLASS.match(text, i)
        if posix:
            if posix[1]:
                raise UnsupportedExpression(f"[:^{posix[2]}:] in the class {text}")
            result.append(posix_class(posix[2]))
            i = posix.end()
            continue
        # A [ in a class is text in RE2
        result.append("\\[" if text[i] == "[" else text[i])
        i += 1
    return "[" + "".join(result) + "]"


def posix_class(name: str) -> str:
    if name not in POSIX_CLASSES:
        raise re.error(f"unknown class [:{name}:]")
    return POSIX_CLASSES[name]


def compile_regex(regex: Regex) -> "re.Pattern[str]":
    """
    Compile a regex for Python. Raises re.error if GitLab rejects it, and
    UnsupportedExpression if Python cannot match it as GitLab does.
    """
    flags = regex.flags
    leading = FLAG_GROUP.match(regex.source)
    if leading and leading[2] == ")":
        flags += leading[1]
    if "U" in flags:
        raise UnsupportedExpression(f"the U (ungreedy) flag of /{regex.source}/{regex.flags}")
    python_flags = 0
    for flag, python_flag in (("i", re.IGNORECASE), ("m", re.MULTILINE), ("s", re.DOTALL)):
        if flag in regex.flags:
            python_flags |= python_flag
    try:
        return re.compile(python_regex(regex.source, "m" in flags), python_flags)
    except OverflowError as e:
        raise re.error(str(e)) from e


def uses_any_byte(regex: Regex) -> bool:
    """
    Whether a regex, already compiled, uses \\C, which RE2 matches as any
    byte: one byte of a character written with several in UTF-8.
    """
    notes: set = set()
    python_regex(regex.source, False, notes)
    return "any byte" in notes


def tokenize(expression: str) -> List[Tuple[str, Any]]:
    tokens: List[Tuple[str, Any]] = []
    position = 0
    while position < len(expression):
        match = TOKEN.match(expression, position)
        if not match:
            raise ExpressionError(f"unexpected '{expression[position:]}'")
        kind, text = match.lastgroup, match.group()
        if kind == "regex":
            regex = parse_regex(text)
            if regex is None:
                raise ExpressionError(f"invalid regex {text}")
            try:
                compile_regex(regex)
            except re.error as e:
                raise ExpressionError(f"invalid regex {text}: {e}") from e
            except UnsupportedExpression:
                # Valid: only an error if the match is evaluated
                pass
            tokens.append(("value", regex))
        elif kind == "variable":
            tokens.append(("variable", text[1:]))
        elif kind == "string":
            tokens.append(("value", text[1:-1]))
        elif kind == "null":
            tokens.append(("value", None))
        elif kind == "operator":
            tokens.append(("operator", text))
        position = match.end()
    return tokens


def ruby_truthy(value: Any) -> bool:
    return value is not None and value is not False


# The text GitLab matches a regex on the left of =~ against: not its source,
# but Ruby's description of the object, with its address (here a fixed one)
REGEX_OBJECT_TEXT = "#<Gitlab::UntrustedRegexp:0x0000000000000000>"


def matches(left: Any, right: Any) -> bool:
    """`left =~ right`."""
    if isinstance(left, Regex):
        text = REGEX_OBJECT_TEXT
    else:
        text = "" if left is None else left if isinstance(left, str) else str(left).lower()
    if isinstance(right, str):
        regex = parse_pattern(right)
        if regex is None:
            return text == right
        right = regex
    if not isinstance(right, Regex):
        return False
    try:
        pattern = compile_regex(right)
    except (re.error, OverflowError):
        # An invalid pattern in a variable matches nothing
        return False
    if not text.isascii() and uses_any_byte(right):
        # One byte of a character written with several in UTF-8
        raise UnsupportedExpression(f"\\C in /{right.source}/ on text that is not ASCII")
    return pattern.search(text) is not None


@dataclass(frozen=True)
class Unknown:
    """
    A value that depends on a match that cannot be evaluated here: one of
    `values`. The expression is still evaluated where the other operands
    decide, e.g. `unknown || "x"` is true.
    """
    values: tuple
    reason: str


def candidates(value: Any) -> tuple:
    return value.values if isinstance(value, Unknown) else (value,)


def combine(operation, *operands: Any) -> Any:
    """
    `operation` on the operands, for each value they can have: a value,
    or Unknown if the result depends on which.
    """
    reasons = [o.reason for o in operands if isinstance(o, Unknown)]
    results: list = []

    def add(result: Any) -> None:
        for value in candidates(result):
            if value not in results:
                results.append(value)

    def apply(chosen: tuple) -> None:
        if len(chosen) < len(operands):
            for value in candidates(operands[len(chosen)]):
                apply(chosen + (value,))
            return
        try:
            add(operation(*chosen))
        except UnsupportedExpression as e:
            reasons.append(str(e))
            add(Unknown((True, False), str(e)))

    apply(())
    return results[0] if len(results) == 1 else Unknown(tuple(results), reasons[0])


class Parser:
    """
    Recursive descent over the tokens, evaluating as it goes, except the
    operands that GitLab does not evaluate (the right one of `&&` and `||`
    when the left one decides), or none at all to only check the syntax:

        or         := and ('||' and)*
        and        := comparison ('&&' comparison)*
        comparison := unary (('==' | '!=' | '=~' | '!~') unary)*
        unary      := '!' unary | operand
        operand    := value | variable | '(' or ')'
    """

    def __init__(self, tokens: List[tuple], variables: VariablesDict, evaluate: bool = True):
        self.tokens = tokens
        self.position = 0
        self.variables = variables
        self.evaluating = evaluate

    def skip(self, parse) -> None:
        """Parse an operand without evaluating it."""
        evaluating, self.evaluating = self.evaluating, False
        try:
            parse()
        finally:
            self.evaluating = evaluating

    def peek(self) -> Optional[str]:
        if self.position < len(self.tokens) and self.tokens[self.position][0] == "operator":
            return self.tokens[self.position][1]
        return None

    def parse(self) -> Any:
        if not self.tokens:
            raise ExpressionError("empty expression")
        value = self.parse_or()
        if self.position < len(self.tokens):
            raise ExpressionError(f"unexpected {self.describe(self.tokens[self.position])}")
        return value

    def parse_or(self) -> Any:
        value = self.parse_and()
        while self.peek() == "||":
            self.position += 1
            if self.evaluating and all(ruby_truthy(v) for v in candidates(value)):
                self.skip(self.parse_and)
            elif self.evaluating:
                value = combine(lambda left, right: left if ruby_truthy(left) else right,
                                value, self.parse_and())
            else:
                self.parse_and()
        return value

    def parse_and(self) -> Any:
        value = self.parse_comparison()
        while self.peek() == "&&":
            self.position += 1
            if self.evaluating and not any(ruby_truthy(v) for v in candidates(value)):
                self.skip(self.parse_comparison)
            elif self.evaluating:
                value = combine(lambda left, right: right if ruby_truthy(left) else left,
                                value, self.parse_comparison())
            else:
                self.parse_comparison()
        return value

    def parse_comparison(self) -> Any:
        value = self.parse_unary()
        operator = self.peek()
        while operator in ("==", "!=", "=~", "!~"):
            self.position += 1
            right = self.parse_unary()
            if self.evaluating:
                value = combine(partial(compare, operator), value, right)
            operator = self.peek()
        return value

    def parse_unary(self) -> Any:
        if self.peek() == "!":
            self.position += 1
            value = self.parse_unary()
            return combine(lambda v: not truthy(v), value) if self.evaluating else None
        return self.parse_operand()

    def parse_operand(self) -> Any:
        if self.position >= len(self.tokens):
            raise ExpressionError("unexpected end of expression")
        kind, token = self.tokens[self.position]
        self.position += 1
        if kind == "value":
            return token
        if kind == "variable":
            if not self.evaluating or token not in self.variables:
                return None
            return variable_value(self.variables[token])
        if token == "(":
            value = self.parse_or()
            if self.peek() != ")":
                raise ExpressionError("missing ')'")
            self.position += 1
            return value
        raise ExpressionError(f"unexpected {self.describe((kind, token))}")

    @staticmethod
    def describe(token: tuple) -> str:
        kind, value = token
        if kind == "variable":
            return f"${value}"
        return f"'{value}'" if kind == "operator" else repr(value)


def compare(operator: str, left: Any, right: Any) -> bool:
    if operator == "==":
        return left == right
    if operator == "!=":
        return left != right
    if operator == "=~":
        return matches(left, right)
    return not matches(left, right)


def truthy(value: Any) -> bool:
    """Whether the value of an expression makes it true."""
    if isinstance(value, str):
        return value.strip() != ""
    return ruby_truthy(value)


def evaluate_expression(expression: str, variables: VariablesDict) -> bool:
    """
    Evaluate a GitLab CI expression with the given variables.

    Raises ExpressionError if GitLab would reject the expression, and
    UnsupportedExpression if it is valid but cannot be evaluated here.
    """
    if not isinstance(expression, str):
        raise ExpressionError(f"an expression must be text, not {expression!r}")
    try:
        result = combine(truthy, Parser(tokenize(expression), variables).parse())
    except RecursionError as e:
        raise UnsupportedExpression("the expression is nested too deeply") from e
    if isinstance(result, Unknown):
        raise UnsupportedExpression(result.reason)
    return result


def uses_variables(expression: str) -> bool:
    """
    Whether a valid GitLab CI expression refers to any variable. If not, its
    value does not depend on them: variables are not expanded in quoted
    strings, e.g. '"$A" == ""' is always false.
    """
    return any(kind == "variable" for kind, _ in tokenize(expression))


def check_expression(expression: Any) -> None:
    """
    Check the syntax of a GitLab CI expression, without evaluating it, as
    GitLab does for every `rules:if`. Raises ExpressionError if GitLab would
    reject it. An expression nested too deeply to parse here is not checked.
    """
    if not isinstance(expression, str):
        raise ExpressionError(f"an expression must be text, not {expression!r}")
    try:
        Parser(tokenize(expression), {}, evaluate=False).parse()
    except RecursionError:
        pass
