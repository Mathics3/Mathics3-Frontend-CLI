# -*- coding: utf-8 -*-
#   Copyright (C) 2021-2022, 2025-2026 Rocky Bernstein <rb@dustyfeet.com>

import os
import os.path as osp
import re
import sys
from typing import Optional, Union

from colorama import init as colorama_init
from mathics.core.atoms import String
from mathics.core.symbols import SymbolNull, SymbolFalse, SymbolTrue
from mathics_pygments.lexer import MathematicaLexer, MToken
from prompt_toolkit import HTML, PromptSession, print_formatted_text
from prompt_toolkit.application.current import get_app
from prompt_toolkit.enums import EditingMode
from prompt_toolkit.history import FileHistory
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles.pygments import style_from_pygments_cls
from pygments import format, highlight, lex
from pygments.styles import get_style_by_name

from mathicsscript.bindkeys import bindings, read_init_file, read_inputrc
from mathicsscript.completion import Mathics3Completer
from mathicsscript.termshell import (
    HISTFILE,
    HISTSIZE,
    USER_INPUTRC,
    ShellEscapeException,
    TerminalShellCommon,
    mma_lexer,
)
from mathicsscript.version import __version__


class TerminalShellPromptToolKit(TerminalShellCommon):
    def __init__(
        self,
        definitions,
        want_completion: bool,
        use_unicode: bool,
        prompt: bool,
        edit_mode: Optional[str],
    ):
        super().__init__(definitions, want_completion, use_unicode, prompt)

        colorama_init()
        self.mma_pygments_lexer = PygmentsLexer(MathematicaLexer)

        self.session = PromptSession(history=FileHistory(HISTFILE))
        if edit_mode is not None:
            self.session.editing_mode = (
                EditingMode.VI if edit_mode == "vi" else EditingMode.EMACS
            )

        # Try importing readline to enable arrow keys support etc.
        self.using_readline = False
        self.history_length = definitions.get_config_value("$HistoryLength", HISTSIZE)
        self.using_readline = sys.stdin.isatty() and sys.stdout.isatty()
        self.ansi_color_re = re.compile("\033\\[[0-9;]+m")

        read_inputrc(read_init_file, use_unicode=use_unicode)
        if osp.isfile(USER_INPUTRC):
            if os.access(USER_INPUTRC, os.R_OK):
                read_init_file(USER_INPUTRC)
            else:
                sys.stderr.write(
                    f"Can't read user inputrc file {USER_INPUTRC}; skipping\n"
                )

        self.completer = (
            Mathics3Completer(self.definitions) if want_completion else None
        )

    def bottom_toolbar(self):
        """Adds a mode-line toolbar at the bottom"""
        # TODO: Figure out how allow user-customization
        app = get_app()
        edit_mode = "Vi" if app.editing_mode == EditingMode.VI else "Emacs"
        if not hasattr(app, "help_mode"):
            app.help_mode = False

        if app.help_mode:
            return HTML("f1: help, f3: toggle autocomplete, f4: toggle edit mode")

        # The first time around, app.group_autocomplete has not been set,
        # so use the value from Settings`GroupAutocomplete.
        # However, after that we may have changed this value internally using
        # function key f3, so update Settings`GroupAutocomplete from that.
        if hasattr(app, "group_autocomplete"):
            self.definitions.set_ownvalue(
                "Settings`$GroupAutocomplete",
                SymbolTrue if app.group_autocomplete else SymbolFalse,
            )
        elif self.definitions.get_ownvalue("Settings`$GroupAutocomplete"):
            app.group_autocomplete = self.definitions.get_ownvalue(
                "Settings`$GroupAutocomplete"
            ).to_python()
        else:
            # First time around and there is no value set via
            # Settings`GroupAutocomplete.
            app.group_autocomplete = True
            self.definitions.set_ownvalue("Settings`$GroupAutocomplete", SymbolTrue)

        if self.definitions.get_ownvalue("Settings`$PygmentsStyle") is not SymbolNull:
            value = self.definitions.get_ownvalue(
                "Settings`$PygmentsStyle"
            ).get_string_value()
            if value is not None and len(value) and value[0] == value[-1] == '"':
                value = value[1:-1]
            pygments_style = value
        else:
            pygments_style = self.pygments_style

        edit_mode = "Vi" if app.editing_mode == EditingMode.VI else "Emacs"
        return HTML(
            f" mathicsscript: {__version__}, Style: {pygments_style}, Mode: {edit_mode}, Autobrace: {app.group_autocomplete}, f1: Help"
        )

    def errmsg(self, message: str):
        if self.is_styled:
            print_formatted_text(HTML(f"<ansired><b>{message}</b></ansired>"))
        else:
            print_formatted_text(HTML(f"<b>{message}</b>"))

    def get_out_prompt(self, form: str) -> Union[str, HTML]:
        """
        Return a formatted "Out" string prefix. ``form`` is either the empty string if the
        default form, or the name of the Form which was used in output if it wasn't then
        default form.
        """
        line_number = self.get_last_line_number()
        if self.is_styled:
            return HTML(
                f"<ansigreen>{self.out_prefix}[<b>{line_number}</b>]</ansigreen>{form}= "
            )
        else:
            return HTML(f"{self.out_prefix}[<b>{line_number}</b>]= ")

    def get_in_prompt(self) -> Union[str, HTML]:
        next_line_number = self.get_last_line_number() + 1
        if self.lineno > 1:
            # We have a multi-line input and need to prompt for the next line.
            # After the first "In[]"-prompted line, we do not repeat
            # "In[]", but instead are indented with the
            # corresponding spaces.
            return " " * len(f"{self.in_prefix}[{next_line_number}]:= ")
        else:
            if self.is_styled:
                return HTML(
                    f"<ansired>{self.in_prefix}[<b>{next_line_number}</b>]:=</ansired> "
                )
            else:
                return HTML(f"{self.in_prefix}[<b>{next_line_number}</b>]:= ")

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
                if show_pygments_tokens:
                    print(list(lex(out_str, mma_lexer)))
                if use_highlight:
                    if self.terminal_formatter is not None:
                        out_str = highlight(out_str, mma_lexer, self.terminal_formatter)

            output = self.to_output(out_str, form="")
            if output_style == "text" or not no_out_prompt:
                print(output)
            elif self.session:
                form = (
                    ""
                    if not hasattr(result, "form") or result.form is None
                    else f"//{result.form}"
                )
                print_formatted_text(self.get_out_prompt(form=form), end="")
                print(output + "\n")
            else:
                print(str(self.get_out_prompt(form="")) + output + "\n")

    def read_line(self, prompt, completer=None, use_html: bool = False):
        # FIXME set and update inside self.

        style = (
            style_from_pygments_cls(get_style_by_name(self.pygments_style))
            if self.pygments_style != "None"
            else None
        )

        if completer is None:
            completer = self.completer

        if use_html:
            prompt = HTML(prompt)

        line = self.session.prompt(
            prompt,
            bottom_toolbar=self.bottom_toolbar,
            completer=completer,
            key_bindings=bindings,
            lexer=self.mma_pygments_lexer,
            style=style,
        )
        # line = self.rl_read_line(prompt)
        if line.startswith("!") and self.lineno == 0:
            raise ShellEscapeException(line)
        return line
        # return replace_unicode_with_wl(line)
