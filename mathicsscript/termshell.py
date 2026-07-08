# -*- coding: utf-8 -*-
#   Copyright (C) 2020-2022, 2024, 2025-2026 Rocky Bernstein <rb@dustyfeet.com>

import locale
import os
import os.path as osp
import pathlib
import re
import sys
from typing import Any, Union

import mathics_scanner.location

from columnize import columnize
from mathics.core.atoms import String
from mathics.core.attributes import attribute_string_to_number
from mathics.core.expression import Expression, from_python  # strip_context,
from mathics.core.parser import MathicsLineFeeder
from mathics.core.rules import Rule
from mathics.core.symbols import Symbol, SymbolNull
from mathics.core.systemsymbols import SymbolMessageName
from mathics_scanner.location import ContainerKind
from mathics.session import (
    SessionShell,
    autoload_files,
    get_settings_value,
    set_settings_value,
)
from mathics_pygments.lexer import MathematicaLexer, MToken
from pygments import format, highlight, lex
from pygments.formatters import Terminal256Formatter
from pygments.formatters.terminal import TERMINAL_COLORS
from pygments.styles import get_all_styles
from pygments.util import ClassNotFound

# FIXME: __main__ shouldn't be needed. Fix term_background
from term_background.__main__ import is_dark_background


mma_lexer = MathematicaLexer()

ALL_PYGMENTS_STYLES = list(get_all_styles()) + ["None"]

color_scheme = TERMINAL_COLORS.copy()
color_scheme[MToken.SYMBOL] = ("yellow", "ansibrightyellow")
color_scheme[MToken.BUILTIN] = ("ansigreen", "ansibrightgreen")
color_scheme[MToken.OPERATOR] = ("magenta", "ansibrightmagenta")
color_scheme[MToken.NUMBER] = ("ansiblue", "ansibrightblue")

# Set up mathicsscript configuration directory
CONFIGHOME = os.environ.get("XDG_CONFIG_HOME", osp.expanduser("~/.config"))
CONFIGDIR = osp.join(CONFIGHOME, "Mathics3")
os.makedirs(CONFIGDIR, exist_ok=True)

try:
    HISTSIZE = int(os.environ.get("MATHICSSCRIPT_HISTSIZE", 50))
except Exception:
    HISTSIZE = 50

HISTFILE = os.environ.get("MATHICS3_HISTFILE", osp.join(CONFIGDIR, "history"))
USER_INPUTRC = os.environ.get("MATHICS3_INPUTRC", osp.join(CONFIGDIR, "inputrc"))

# Create HISTFILE if it doesn't exist already
if not osp.isfile(HISTFILE):
    pathlib.Path(HISTFILE).touch()

SymbolPygmentsStylesAvailable = Symbol("Settings`PygmentsStylesAvailable")


def get_srcdir():
    filename = osp.normcase(osp.dirname(osp.abspath(__file__)))
    return osp.realpath(filename)


def is_pygments_style(style: str) -> bool:
    if style not in ALL_PYGMENTS_STYLES:
        print(f"Pygments style name '{style}' not found.")
        print(f"Style names are:\n{columnize(ALL_PYGMENTS_STYLES)}")
        return False
    return True


class ShellEscapeException(Exception):
    def __init__(self, line):
        self.line = line


class TerminalShellCommon(MathicsLineFeeder, SessionShell):
    def __init__(
        self,
        definitions,
        want_completion: bool,
        autoload=False,
        prompt: str | None = None,
        use_unicode: bool = False,
        in_prefix: str = "In",
        out_prefix: str = "Out",
    ):
        super().__init__([], ContainerKind.STREAM)
        self.input_encoding = locale.getpreferredencoding()

        # is_inside_interrupt is set True when shell has been
        # interrupted via an interrupt handler.
        self.is_inside_interrupt = False

        self.lineno = 0
        self.in_prefix = in_prefix
        self.out_prefix = out_prefix

        self.terminal_formatter = None
        self.prompt = prompt
        self.using_readline = False
        self.want_completion = want_completion

        self.definitions = definitions
        self.definitions.set_ownvalue(
            "Settings`$PygmentsShowTokens", from_python(False)
        )
        self.definitions.set_ownvalue("Settings`$UseUnicode", from_python(use_unicode))
        self.definitions.set_ownvalue(
            "Settings`PygmentsStylesAvailable",
            from_python(ALL_PYGMENTS_STYLES),
        )

        self.definitions.add_message(
            "Settings`PygmentsStylesAvailable",
            Rule(
                Expression(
                    SymbolMessageName,
                    SymbolPygmentsStylesAvailable,
                    from_python("usage"),
                ),
                from_python(
                    "A list of Pygments style that are valid in Settings`$PygmentsStyle."
                ),
            ),
        )
        self.definitions.set_attribute(
            "Settings`PygmentsStylesAvailable",
            attribute_string_to_number["System`Protected"],
        )
        self.definitions.set_attribute(
            "Settings`PygmentsStylesAvailable",
            attribute_string_to_number["System`Locked"],
        )

        self.definitions.set_attribute(
            "Settings`$UseUnicode", attribute_string_to_number["System`Locked"]
        )

        if autoload:
            autoload_files(definitions, get_srcdir(), "autoload-cli")

    def change_pygments_style(self, style: str):
        if not style or style == self.pygments_style:
            return False
        if style == "None":
            self.terminal_formatter = None
            self.pygments_style = style
            self.incolors = self.outcolors = ["", "", "", ""]
            return True
        if is_pygments_style(style):
            self.incolors = ["\033[32m", "\033[1m", "\033[22m", "\033[39m"]
            self.outcolors = ["\033[31m", "\033[1m", "\033[22m", "\033[39m"]
            self.terminal_formatter = Terminal256Formatter(style=style)
            self.pygments_style = style
            return True

        print("Pygments style not changed")
        return False

    def empty(self):
        return False

    def errmsg(self, message: str):
        print(f"{self.outcolors[0]}{message}{self.outcolors[3]}")
        return

    def feed(self):
        prompt_str = self.in_prompt if self.prompt else ""
        result = self.read_line(prompt_str) + "\n"
        if mathics_scanner.location.TRACK_LOCATIONS and self.source_text is not None:
            self.container.append(self.source_text)
        if result == "\n":
            return ""  # end of input
        self.lineno += 1
        return result

    @property
    def in_prompt(self) -> Union[str, Any]:
        """
        Return the prompt string to be shown before reading input.
        """
        next_line_number = self.last_line_number + 1
        if self.lineno > 1:
            # We have a multi-line input and need to prompt for the next line.
            # After the first "In[]"-prompted line, we do not repeat
            # "In[]", but instead are indented with the
            # corresponding spaces.
            return " " * len(f"{self.in_prefix}[{next_line_number}]:= ")
        elif self.is_styled:
            return "{2}{0}[{3}{1}{4}]:= {5}".format(
                self.in_prefix, next_line_number, *self.incolors
            )
        else:
            return f"In[{next_line_number}]:= "

    # prompt-toolkit returns a HTML object. Therefore, we include Any
    # to cover that.
    def get_out_prompt(self, form: str) -> Union[str, Any]:
        """
        Return a formatted "Out" string prefix. ``form`` is either the empty string if the
        default form, or the name of the Form which was used in output preceded by "//"
        """
        line_number = self.last_line_number
        if self.is_styled:
            return "{3}{0}[{4}{1}{5}]{6}{2}= ".format(
                self.out_prefix, line_number, form, *self.outcolors
            )
        else:
            return f"Out[{line_number}]= "

    @property
    def is_styled(self):
        """
        Returns True if a Pygments style (other than SymbolNull or "None" has been set.
        """
        style = self.definitions.get_ownvalue("Settings`$PygmentsStyle")
        return not (style is SymbolNull or style.value == "None")

    @property
    def last_line_number(self) -> int:
        """
        Return the next Out[] line number
        """
        return self.definitions.get_line_no()

    def out_callback(self, out):
        print(self.to_output(str(out), form=""))

    # noinspection PyUnusedLocal
    def read_line(self, prompt, _completer=None, _use_html: bool = False):
        if self.using_readline:
            line = self.rl_read_line(prompt)
        else:
            line = input(prompt)
        if line.startswith("!") and self.lineno == 0:
            raise ShellEscapeException(line)
        return line
        # return replace_unicode_with_wl(line)

    def print_result(
        self,
        result,
        no_out_prompt: bool = False,
        output_style="",
        strict_wl_output=False,
    ):
        if result is None or result.last_eval is SymbolNull:
            # Following WMA CLI, if the result is `SymbolNull`, just print an empty line.
            print("")
            return

        last_eval = result.last_eval

        if last_eval is not None:
            try:
                eval_type = last_eval.get_head_name()
            except Exception:
                print(sys.exc_info()[1])
                return

            out_str = str(result.result)
            use_highlight = True
            if eval_type == "System`String":
                # Use exact-wl-compatibility?
                if strict_wl_output:
                    out_str = (
                        format(
                            [(MToken.STRING, out_str.rstrip())], self.terminal_formatter
                        )
                        + "\n"
                    )
                    use_highlight = False
                else:
                    out_str = '"' + out_str.replace('"', r"\"") + '"'

            show_pygments_tokens = self.definitions.get_ownvalue(
                "Settings`$PygmentsShowTokens"
            ).to_python()
            pygments_style = self.definitions.get_ownvalue(
                "Settings`$PygmentsStyle"
            ).get_string_value()
            if pygments_style != self.pygments_style:
                if not self.change_pygments_style(pygments_style):
                    self.definitions.set_ownvalue(
                        "Settings`$PygmentsStyle", String(self.pygments_style)
                    )

            if eval_type == "System`Graph":
                out_str = "-Graph-"

            elif self.terminal_formatter:  # pygmentize
                show_pygments_tokens = get_settings_value(
                    self.definitions, "Settings`$PygmentsShowTokens"
                )
                pygments_style = get_settings_value(
                    self.definitions, "Settings`$PygmentsStyle"
                )
                if pygments_style != self.pygments_style:
                    if not self.change_pygments_style(pygments_style):
                        set_settings_value(
                            self.definitions,
                            "Settings`$PygmentsStyle",
                            String(self.pygments_style),
                        )

                if show_pygments_tokens:
                    print(list(lex(out_str, mma_lexer)))
                if use_highlight:
                    if self.terminal_formatter is not None:
                        out_str = highlight(out_str, mma_lexer, self.terminal_formatter)
            form = (
                ""
                if not hasattr(result, "form") or result.form is None
                else f"//{result.form}"
            )
            output = self.to_output(out_str, form)
            if output_style == "text" or not no_out_prompt:
                print(output)
            else:
                form = "" if result.form is None else f"//{result.form}"
                print(self.get_out_prompt(form) + output + "\n")

    def rl_read_line(self, prompt):
        # Wrap ANSI color sequences in \001 and \002, so readline
        # knows that they're nonprinting.
        prompt = self.ansi_color_re.sub(lambda m: "\001" + m.group(0) + "\002", prompt)

        return input(prompt)

    def reset_lineno(self):
        self.lineno = 0

    def setup_pygments_style(self, style):
        """Goes through what we need to do to setup or change a
        Pygments style.
        """
        if (
            isinstance(style, str)
            and style.lower() == "none"
            or style is None
            and os.environ.get("NO_COLOR", False)
        ):
            style = "None"  # Canonicalize spelling
            self.terminal_formatter = None
            self.incolors = self.outcolors = ["", "", "", ""]
        else:
            # self.incolors = ["\033[34m", "\033[1m", "\033[22m", "\033[39m"]
            self.incolors = ["\033[32m", "\033[1m", "\033[22m", "\033[39m"]
            self.outcolors = ["\033[31m", "\033[1m", "\033[22m", "\033[39m"]
            if style is not None and not is_pygments_style(style):
                style = None

            # If no style given, choose one based on the background.
            if style is None:
                dark_background = is_dark_background()
                if dark_background:
                    style = "inkpot"
                else:
                    style = "colorful"
            try:
                self.terminal_formatter = Terminal256Formatter(style=style)
            except ClassNotFound:
                print(f"Pygments style name '{style}' not found; No pygments style set")
                style = "None"

        self.definitions.set_ownvalue("Settings`$PygmentsStyle", from_python(style))
        self.pygments_style = style

    def to_output(self, text: str, form: str) -> str:
        """
        Format an 'Out=' line that it lines after the first one indent properly.
        """
        line_number = self.last_line_number
        if self.is_styled:
            newline = "\n" + " " * len(f"Out[{line_number}]{form}= ")
        else:
            newline = "\n" + " " * len(f"Out[{line_number}]= ")
        return newline.join(text.splitlines())
