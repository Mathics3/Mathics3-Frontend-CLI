# -*- coding: utf-8 -*-

from mathics.core.definitions import Definitions
from mathicsscript.termshell_gnu import TerminalShellGNUReadline

try:
    __import__("readline")
except ImportError:
    have_readline = False
else:
    have_readline = True


def test_completion_gnu():
    definitions = Definitions(add_builtin=True, extension_modules=[])
    term = TerminalShellGNUReadline(
        definitions=definitions,
        want_completion=True,
        use_unicode=False,
        prompt="",
    )

    for prefix, completions in (("Fibonac", "Fibonacci"), ("Adfafdsadfs", None)):
        assert term.complete_symbol_name(prefix, state=0) == completions

    if have_readline:
        for prefix, completions in (("\\[Alph", "\\[Alpha]"), ("\\[Adfafdsadfs", None)):
            assert term.complete_symbol_name(prefix, state=0) == completions

    # TODO: multiple completion items


if __name__ == "__main__":
    test_completion_gnu()
