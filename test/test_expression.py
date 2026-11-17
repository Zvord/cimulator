"""
GitLab CI expressions (rules:if), checked against GitLab.

Every expression of CASES and UNSUPPORTED was run through GitLab's pipeline
dry run, as the `if` of a job, with VARIABLES as the configuration's
variables: True if the job was created, False if not, "invalid" if GitLab
rejected the expression ("rules:rule if invalid expression syntax").
"""
import pytest

from cimulator.expression import ExpressionError, UnsupportedExpression, evaluate_expression
from cimulator.workflow import evaluate_condition

VARIABLES = {
    'A': 'abc',
    'A2': 'abc',
    'E': '',
    'Q': 'x" or "a',
    'B': 'a\\x41',
    'P': '/^ab/',
    'PI': '/^AB/i',
    'PS': '^ab',
    'R': '$A',
    'N': 'null',
    'SL': 'a/b',
    'DQ': 'say "hi"',
    'PL': 'bc',
    'ML': 'a\nb',
    'NL': 'abc\n',
    'U8': 'é',
    'AR': '٣',
    'BR': 'a{,3}',
    'BIG': '/a{99999999999}/',
    'WS': ' ',
    'NUM': '10',
    'AV': 'abc',
    'PU': '/^AB/',
    'PX': '/(/',
    'PD': 'a.c',
    'DEPLOY': {'value': 'prod', 'description': 'where to deploy'},
    'PDESC': {'description': 'no value'},
    'P1': '/a/',
    'REL': 'release/x',
    'PSL': '/^release/.*/',
    'PE': '//',
    'PG': '/a/g',
    'PTR': '/a/ ',
    'PONE': '/',
    'AB': 'xa/bx',
    'PSL2': '/a/b/',
    'PRAW': '/q\\n|a/',
    'PNLV': '/q\n|a/',
    'AW': 'aé',
    'BR01': 'a{01}',
    'FOO': None,
    'BAR': None,
}

CASES = [
    ('', 'invalid'),
    (' ', 'invalid'),
    ('$A', True),
    ('$E', False),
    ('$U', False),
    ('$A == "abc"', True),
    ('"abc" == $A', True),
    ("$A == 'abc'", True),
    ('$U == null', True),
    ('$E == null', False),
    ('$A != null', True),
    ('$U != null', False),
    ('null == $U', True),
    ('$U == ""', False),
    ('$E == ""', True),
    ('$A == $A2', True),
    ('$U == $U2', True),
    ('$E == $U', False),
    ('$Q == "nope"', False),
    ('$Q == \'x" or "a\'', True),
    ('$B == "aA"', False),
    ('$B == "a\\x41"', True),
    ('$A =~ /^ab/', True),
    ('$A =~ /^AB/i', True),
    ('$A =~ /^AB/', False),
    ('$U =~ /.*/', True),
    ('$U !~ /x/', 'invalid'),
    ('$E =~ /^$/', True),
    ('$A =~ $P', True),
    ('$A =~ $PI', True),
    ('$A !~ $P', False),
    ('$A =~ $PS', False),
    ('$A || $A && $E', True),
    ('$E && $A || $A', True),
    ('($A || $A) && $E', False),
    ('${A} == "abc"', 'invalid'),
    ('$R == "abc"', False),
    ('$R == "$A"', True),
    ('$N == null', False),
    ('$SL =~ /a\\/b/', True),
    ('$DQ == \'say "hi"\'', True),
    ('$A =~ /^AB/im', True),
    ('$A == "ABC"', False),
    ('$A =~ /b/', 'invalid'),
    ('$A =~ /^b/', False),
    ('$A =~ /bc/', True),
    ('$A =~ /xy/', False),
    ('$A =~ /^x/', False),
    ('$A =~ /c$/', True),
    ('$A =~ /[b]/', True),
    ('$A =~ /./', 'invalid'),
    ('$U !~ /xy/', True),
    ('$U =~ /^$/', True),
    ('$U =~ /^.+$/', False),
    ('$A =~ $PL', False),
    ('$A =~ $PD', False),
    ('$A =~ "abc"', True),
    ('$A =~ "/abc/"', True),
    ('$A =~ $PX', False),
    ('$A =~ /AB/s', False),
    ('$A =~ /AB/x', 'invalid'),
    ('$A =~ /AB/g', 'invalid'),
    ('$A =~ //', 'invalid'),
    ('$A != "abc"', False),
    ('$U != "x"', True),
    ('"abc" =~ /b./', True),
    ('$A=="abc"', True),
    ('$A == "abc" && ($E || $A)', False),
    ('$A and $E', 'invalid'),
    ('!$A', False),
    ('$A < "b"', 'invalid'),
    ('$A == null && $U', False),
    ('$A =~ null', False),
    ('$A == "abc" &&', 'invalid'),
    ('$A ==', 'invalid'),
    ('"abc"', True),
    ('null', False),
    ('(($A))', True),
    ('$A == "abc" || $U == null && $E', True),
    ('$PL == "bc" && $A =~ /a(b|x)c/', True),
    ('($E || $A)', False),
    ('$A == "abc" && ($A)', True),
    ('($E || $A) && $A == "abc"', True),
    ('$A == "abc" && ($A || $E)', True),
    ('$A && ($E || $A)', False),
    ('$A && $E || $A', False),
    ('$E || $A', False),
    ('$A && ($A)', True),
    ('$A == "abc" && $A', True),
    ('"x" && ($E || $A)', False),
    ('($A) && ($E || $A)', False),
    ('!$E', True),
    ('!$U', True),
    ('! $E', True),
    ('$A =~ "bc"', False),
    ('$A =~ $AV', True),
    ('$PL =~ "bc"', True),
    ('$A =~ "ab.*"', False),
    ('$A =~ "/^AB/i"', True),
    ('$A =~ $PU', False),
    ('$A !~ "abc"', False),
    ('$A == "abc" && ($E || $A == "abc")', False),
    ('$A == "abc" && ($U == null)', True),
    ('$A == "abc" && ($U == null || $E)', True),
    ('!$A == "x"', False),
    ('!!$A', True),
    ('!($E || $A)', True),
    ('$WS', False),
    ('$WS == " "', True),
    ('$A =~ /ab/ && $PL =~ /bc/', True),
    ('$A =~ /ab/ && $PL =~ /xx/', False),
    ('$A =~ /a.c/s', True),
    ('$NUM == "10"', True),
    ('$NUM == 10', 'invalid'),
    ('$A == abc', 'invalid'),
    ('$U || $A', True),
    ('$U && $A', False),
    ('$A =~ /^(a|x)+bc$/', True),
    ('$A =~ /ab\\/c/', False),
    ('"a" == "a" && "b"', True),
    ('$A == ""', False),
    ('($A == "abc")', True),
    ('$A =~ /a\\w+/', True),
    ('$A =~ /a(/', 'invalid'),
    ('$A !~ /a(/', 'invalid'),
    ('$A !~ $PX', True),
    ('$A !~ null', True),
    ('$U !~ $P', True),
    ('$A =~ /(?<=a)b/', 'invalid'),
    ('/ab/', True),
    ('$ML =~ /a.b/m', False),
    ('$ML =~ /^b/m', True),
    ('$ML =~ /^b/', False),
    ('$ML =~ /a.b/s', True),
    ('$ML =~ /a.b/', False),
    ('$A =~ /ab(?=c)/', 'invalid'),
    ('$A =~ /(a)\\1/', 'invalid'),
    ('$A =~ /c\\z/', True),
    ('$A =~ /c\\Z/', 'invalid'),
    ('$A =~ /\\Aab/', True),
    ('$A =~ /\\h/', 'invalid'),
    ('$A =~ /(?i)AB/', True),
    ('$A =~ /[[:alpha:]]+/', True),
    ('$A =~ /(?>ab)c/', 'invalid'),
    ('$A =~ /(?P<x>a)(?P=x)/', 'invalid'),
    ('$A =~ /ab++c/', 'invalid'),
    ('$A =~ /(?#c)ab/', 'invalid'),
    ('$A =~ /\\x61b/', True),
    ('$A =~ /a{1,2}/', True),
    ('$ML =~ /a$/m', True),
    ('$ML =~ /a$/', False),
    ('$NL =~ /c$/', False),
    ('$NL =~ /^abc$/', False),
    ('$NL =~ /c\\z/', False),
    ('$U8 =~ /^\\w$/', False),
    ('$AR =~ /^\\d$/', False),
    ('$U8 =~ /^\\W$/', True),
    ('$A =~ /^[[:^digit:]]+$/', True),
    ('$BR =~ /^a{,3}$/', True),
    ('$A =~ /^a}+/', False),
    ('$A =~ /\\Qab\\E/', True),
    ('$A =~ /\\x{61}b/', True),
    ('$A =~ /(?<n>a)b/', True),
    ('$A =~ /(?P<n>a)b/', True),
    ('$A =~ /(?x)a b/', 'invalid'),
    ('$A =~ /a{1001}/', 'invalid'),
    ('$A =~ /a{1000}/', False),
    ('$A =~ /a{99999999999}/', False),
    ('$A =~ $BIG', False),
    ('$U8 =~ /^É$/i', True),
    ('$ML =~ /(?m)^b/', True),
    ('$ML =~ /(?s)a.b/', True),
    ('$A =~ /(?i:AB)c/', True),
    ('$A =~ /(?-i:ab)C/i', True),
    ('$NL =~ /c$/m', True),
    ('$A =~ /[\\w]+/', True),
    ('$A =~ /a{2,1}/', 'invalid'),
    ('$A =~ /a{1000,}/', False),
    ('$A =~ /a{}/', False),
    ('$DEPLOY == "prod"', True),
    ('$DEPLOY =~ /^prod$/', True),
    ('$PDESC == ""', True),
    ('$PDESC == null', False),
    ('$A =~ $P1', True),
    ('$A !~ $P1', False),
    ('$REL =~ $PSL', True),
    ('$A =~ $PE', True),
    ('$A =~ $PG', False),
    ('$A !~ $PG', True),
    ('$A =~ $PTR', False),
    ('$A =~ $PONE', False),
    ('$PONE =~ $PONE', True),
    ('$AB =~ $PSL2', True),
    ('$A =~ $PSL2', False),
    ('$A =~ $PRAW', True),
    ('$A =~ $PNLV', False),
    ('$A =~ "//"', True),
    ('$A =~ "/a/"', True),
    ('$A =~ "/A/i"', True),
    ('$A == "abc" || $A =~ /\\pL/', True),
    ('$A == "x" && $A =~ /\\pL/', False),
    ('$A =~ /\\x{110000}/', 'invalid'),
    ('$A =~ /\\x{10FFFF}/', False),
    ('$A =~ /\\x{61/', 'invalid'),
    ('$A =~ /\\x{zz}/', 'invalid'),
    ('$A =~ /\\x{}/', 'invalid'),
    ('$A =~ /[\\x{61}]b/', True),
    ('$A =~ /[\\x{61]/', 'invalid'),
    ('$A =~ /[\\x{zz}]/', 'invalid'),
    ('$NL =~ /c\\12/', True),
    ('$NL =~ /c\\012/', True),
    ('$NL =~ /c[\\12]/', True),
    ('$A =~ /\\141/', True),
    ('$A =~ /a\\1/', 'invalid'),
    ('$A =~ /a\\8/', 'invalid'),
    ('$A =~ /[\\8]/', 'invalid'),
    ('$A =~ /[\\1]/', 'invalid'),
    ('$A =~ /a\\0/', False),
    ('$U8 =~ /\\bé/', False),
    ('$AW =~ /a\\b/', True),
    ('$AW =~ /a\\B/', False),
    ('$A =~ /\\Bb/', True),
    ('$A =~ /\\bab/', True),
    ('$BR01 =~ /^a{01}$/', True),
    ('$A =~ /^a{01}/', False),
    ('$A =~ /^ab{1,02}/', False),
    ('$A =~ /^ab{0}c/', False),
    ('!""', True),
    ('!" "', True),
    ('!$WS', True),
    ('!"" || $U', True),
    ('"" && $A', True),
    ('$A =~ /\\pL/ || $A == "abc"', True),
    ('$A =~ /\\pN/ || $A == "abc"', True),
    ('$A =~ /\\pL/ && $A == "x"', False),
    ('!($A =~ /\\pL/ && $A == "x")', True),
    ('$A =~ /\\pL/ == $A', False),
    ('$A =~ /\\pL/ && $A =~ /\\pN/ || "x"', True),
    ('$FOO == ""', True),
    ('$FOO == null', False),
    ('$BAR == ""', True),
    ('$BAR == null', False),
    ('$FOO', False),
    ('$FOO =~ /^$/', True),
    ('$FOO || $A', False),
    ('/xy/ =~ /xy/', False),
    ('/xy/ =~ /^xy$/', False),
    ('/xy/ =~ /^\\/xy\\/$/', False),
    ('/xy/ =~ /\\(\\?/', False),
    ('/xy/ =~ /.*/', True),
    ('/xy/ !~ /.*/', False),
    ('/xy/ =~ /^$/', False),
    ('/xy/ =~ /flags/', False),
    ('/xy/ =~ /mix/', False),
    ('/xy/ =~ /\\//', False),
    ('/xy/ =~ /xy/ || /xy/ !~ /xy/', True),
    ('/xy/ =~ /Gitlab/', True),
    ('/xy/ =~ /RE2/', False),
    ('/xy/ =~ /^.+$/', True),
    ('/xy/ =~ /[0-9]/', True),
    ('/xy/ =~ /^#<Gitlab::UntrustedRegexp/', True),
    ('/xy/ =~ /./', 'invalid'),
    ('/xy/i =~ /i/', 'invalid'),
    ('$A =~ /a\\Cc/', True),
    ('$A =~ /^\\C\\C\\C$/', True),
    ('$A =~ /^\\C\\C$/', False),
    ('$ML =~ /a\\Cb/', True),
    ('$A =~ /(a{10}){100}/', False),
    ('$A =~ /(a{11}){100}/', 'invalid'),
    ('$A =~ /((a{10}){10}){10}/', False),
    ('$A =~ /((a{11}){10}){10}/', 'invalid'),
    ('$A =~ /(a{2,10}){100}/', False),
    ('$A =~ /(a{2,11}){100}/', 'invalid'),
    ('$A =~ /(a{1000})/', False),
    ('$A =~ /(a{10}){100}b{1000}/', False),
    ('$A =~ /(a{10})(b{100}){10}/', False),
    ('$A =~ /(?:a{10}){101}/', 'invalid'),
    ('$A =~ /(a*){1000}/', True),
    ('$A =~ /(a{10,}){100}/', False),
    ('$A =~ /(a{11,}){100}/', 'invalid'),
    ('$A =~ /(a{0}){1000}/', True),
]

# Valid in GitLab (with its result), but not evaluated here: Python's re has
# no ungreedy flag, no Unicode classes, no flags in the middle of a pattern
# and no negated POSIX class within a class. Such a match is only a problem
# when it is evaluated: not on the right of && or || when the left decides
UNSUPPORTED = [
    ('$A =~ /AB/U', False),
    ('$A =~ /\\p{L}/', True),
    ('$A =~ /(?U)ab/', True),
    ('$A =~ /a(?i)B/', True),
    ('$A =~ /[[:^digit:]x]/', True),
    ('$A == "x" || $A =~ /\\pL/', True),
    ('$A =~ /\\pL/ || $A == "x"', True),
    ('$A =~ /\\pN/ || $A == "x"', False),
    ('$A =~ /\\pN/ && $A == "abc"', False),
    ('$A =~ /\\pL/ || $E', True),
    ('$A =~ /\\pN/ || $E', False),
    ('$U8 =~ /^\\C$/', False),
    ('$U8 =~ /^\\C\\C$/', True),
]


@pytest.mark.parametrize("expression, expected", CASES)
def test_as_in_gitlab(expression, expected):
    if expected == "invalid":
        with pytest.raises(ExpressionError):
            evaluate_expression(expression, VARIABLES)
    else:
        assert evaluate_expression(expression, VARIABLES) is expected


@pytest.mark.parametrize("expression, gitlab_result", UNSUPPORTED)
def test_valid_but_unsupported(expression, gitlab_result):
    with pytest.raises(UnsupportedExpression):
        evaluate_expression(expression, VARIABLES)


def test_invalid_pattern_in_a_variable_matches_nothing():
    for pattern in ["/a{99999999999}/", "/a{1001}/", "/(/"]:
        assert evaluate_expression("$A =~ $P", {"A": "a", "P": pattern}) is False
        assert evaluate_expression("$A !~ $P", {"A": "a", "P": pattern}) is True


def test_deep_nesting_is_unsupported_not_a_crash():
    with pytest.raises(UnsupportedExpression):
        evaluate_expression("(" * 2000 + "$A" + ")" * 2000, {})
    with pytest.raises(UnsupportedExpression):
        evaluate_expression("!" * 5000 + "$A", {})


@pytest.mark.parametrize("condition", [True, 1, None, ["$A"]])
def test_condition_that_is_not_text_is_invalid(condition):
    # GitLab: rules:rule if invalid expression syntax
    with pytest.raises(ExpressionError):
        evaluate_condition(condition, {})


def test_values_are_never_code():
    # A value is data, not part of the expression: before, X = 'x" or "a'
    # made $X == "nope" true, and a backslash in a value was an escape
    assert evaluate_condition('$X == "nope"', {"X": 'x" or "a'}) is False
    assert evaluate_condition('$X == "aA"', {"X": "a\\x41"}) is False
    assert evaluate_condition("$X == \"__import__('os')\"", {"X": "1"}) is False


def test_invalid_expression_fails_in_job_rules():
    # GitLab rejects the configuration
    with pytest.raises(ExpressionError, match="invalid expression '\\$A and \\$B'"):
        evaluate_condition("$A and $B", {})


def test_unsupported_expression_is_a_warning(caplog):
    assert evaluate_condition("$A =~ /a+/U", {"A": "aa"}) is False
    assert "Cannot evaluate condition" in caplog.text
    with pytest.raises(UnsupportedExpression):
        evaluate_condition("$A =~ /a+/U", {"A": "aa"}, strict=True)


def test_non_string_values_are_text():
    assert evaluate_condition('$FLAG == "true" && $N == "1"', {"FLAG": True, "N": 1}) is True


@pytest.mark.parametrize("expression, variables, expected", [
    # \C inside \Q...\E is text, so non-ASCII text is matched as usual
    (r"$A =~ /\Qa\Cb\E/", {"A": "é"}, False),
    (r"$A =~ /\Qa\Cb\E/", {"A": "xa\\Cb"}, True),
    # An invalid pattern in a variable matches nothing, even with \C
    (r"$A =~ $P", {"A": "é", "P": "/a(\\C/"}, False),
])
def test_any_byte_escape_as_text_or_in_an_invalid_pattern(expression, variables, expected):
    assert evaluate_expression(expression, variables) is expected


def test_any_byte_escape_on_text_that_is_not_ascii_is_unsupported():
    with pytest.raises(UnsupportedExpression):
        evaluate_expression(r"$A =~ /^\C$/", {"A": "é"})
