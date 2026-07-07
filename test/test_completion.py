# -*- coding: utf-8 -*-

import pytest
from mathics.core.definitions import Definitions

pytest.importorskip("readline")

from mathicsscript.termshell_gnu import TerminalShellGNUReadline


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

    for prefix, completions in (("\\[Alph", "\\[Alpha]"), ("\\[Adfafdsadfs", None)):
        assert term.complete_symbol_name(prefix, state=0) == completions

    # TODO: multiple completion items
