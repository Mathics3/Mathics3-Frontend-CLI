#   Copyright (C) 2026 Rocky Bernstein <rb@dustyfeet.com>
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Terminal handling for command-line REPL. Also used by Dialog[] in mathics-core,
but not used by other front-ends.

"""

import subprocess
import sys
from typing import Any
import mathics.core as mathics_core
from mathics import settings
from mathics.core.evaluation import Evaluation, Output
from mathics.core.systemsymbols import SymbolTeXForm
from mathicsscript.settings import definitions
from mathicsscript.termshell import TerminalShellCommon

from mathics_scanner import replace_wl_with_plain_text
from pygments import highlight

from mathicsscript.termshell import ShellEscapeException, mma_lexer
from mathicsscript.interrupt import setup_signal_handler

try:
    __import__("readline")
except ImportError:
    have_readline = False
    readline_choices = ["Prompt", "None"]
else:
    readline_choices = ["GNU", "Prompt", "None"]
    have_readline = True


class TerminalOutput(Output):
    def max_stored_size(self, settings):
        return None

    def __init__(self, shell):
        self.shell = shell

    def out(self, out):
        return self.shell.out_callback(out)


def interactive_eval_loop(
    shell: TerminalShellCommon,
    unicode,
    prompt,
    strict_wl_output: bool,
    init_signal_handler: bool = True,
):

    if init_signal_handler:
        setup_signal_handler()

    def identity(x: Any) -> Any:
        return x

    def fmt_fun(query: Any) -> Any:
        return highlight(str(query), mma_lexer, shell.terminal_formatter)

    if init_signal_handler:
        setup_signal_handler()

    shell.fmt_fn = fmt_fun
    while True:
        try:
            if shell.using_readline:
                import readline as GNU_readline

                last_pos = GNU_readline.get_current_history_length()

            full_form = definitions.get_ownvalue(
                "Settings`$ShowFullFormInput"
            ).to_python()
            style = definitions.get_ownvalue("Settings`$PygmentsStyle")
            fmt = identity
            if style:
                style = style.get_string_value()
                if shell.terminal_formatter:
                    fmt = fmt_fun
            shell.pygments_style = style or "None"

            evaluation = Evaluation(shell.definitions, output=TerminalOutput(shell))

            # Store shell into the evaluation so that an interrupt handler
            # has access to this.
            evaluation.shell = shell

            query, source_code = evaluation.parse_feeder_returning_code(shell)
            if mathics_core.PRE_EVALUATION_HOOK is not None:
                mathics_core.PRE_EVALUATION_HOOK(query, evaluation)

            if (
                have_readline
                and shell.using_readline
                and hasattr(GNU_readline, "remove_history_item")
            ):
                current_pos = GNU_readline.get_current_history_length()
                for pos in range(last_pos, current_pos - 1):
                    try:
                        GNU_readline.remove_history_item(pos)
                    except ValueError:
                        pass
                wl_input = source_code.rstrip()
                if unicode:
                    wl_input = replace_wl_with_plain_text(wl_input)
                GNU_readline.add_history(wl_input)

            if query is None:
                continue

            if hasattr(query, "head") and query.head == SymbolTeXForm:
                output_style = "//TeXForm"
            else:
                output_style = ""

            if full_form:
                print(fmt(query))
            result = evaluation.evaluate(
                query, timeout=settings.TIMEOUT, format="unformatted"
            )
            if result is not None:
                shell.print_result(
                    result, prompt, output_style, strict_wl_output=strict_wl_output
                )

        except ShellEscapeException as e:
            source_code = e.line
            if not settings.ENABLE_SYSTEM_COMMANDS:
                shell.errmsg("System commands are disabled in sandboxed mode.")
                continue
            if len(source_code) and source_code[1] == "!":
                try:
                    print(open(source_code[2:], "r").read())
                except Exception:
                    shell.errmsg(str(sys.exc_info()[1]))
            else:
                subprocess.run(source_code[1:], shell=True)

                # Should we test exit code for adding to history?
                GNU_readline.add_history(source_code.rstrip())
                # FIXME add this... when in Mathics3 core updated
                shell.definitions.increment_line(1)

        except KeyboardInterrupt:
            shell.errmsg("\nKeyboardInterrupt")
        except EOFError:
            if prompt:
                shell.errmsg("\n\nGoodbye!\n")
            break
        except SystemExit:
            shell.errmsg("\n\nGoodbye!\n")
            # raise to pass the error code on, e.g. Quit[1]
            raise
        finally:
            # Reset the input line that would be shown in a parse error.
            # This is not to be confused with the number of complete
            # inputs that have been seen, i.e. In[]
            shell.reset_lineno()
