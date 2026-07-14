#!/usr/bin/env python3
#   Copyright (C) 2025-2026 Rocky Bernstein <rb@dustyfeet.com>
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

import os
import os.path as osp
import sys
from pathlib import Path

import click
from mathics import license_string, settings, version_info
from mathics.core.attributes import attribute_string_to_number
from mathics.core.expression import from_python
from mathics.core.evaluation import Evaluation
from mathics.core.parser import MathicsFileLineFeeder
from mathics.core.symbols import Symbol, SymbolNull, SymbolFalse, SymbolTrue
from mathicsscript.repl import TerminalOutput, interactive_eval_loop, readline_choices
from mathics.session import autoload_files

from mathicsscript.asymptote import asymptote_version
from mathicsscript.settings import definitions
from mathicsscript.termshell import TerminalShellCommon
from mathicsscript.version import __version__

from mathicsscript.format import format_output, matplotlib_version

try:
    import readline

    have_readline = True
except ImportError:
    have_readline = False


version_string = """Mathics3 {mathics}
on {python}

Using:
SymPy {sympy}, mpmath {mpmath}, numpy {numpy}
""".format(
    **version_info
)

if "cython" in version_info:
    version_string += f"cython {version_info['cython']}, "

if matplotlib_version is None:
    version_string += "\nNo matplotlib installed,"
else:
    version_string += f"matplotlib {matplotlib_version},"

if asymptote_version is None:
    version_string += "\nNo asymptote installed,"
else:
    version_string += f"\n{asymptote_version}"


def get_srcdir():
    filename = osp.normcase(osp.dirname(osp.abspath(__file__)))
    return osp.realpath(filename)


def ensure_settings():
    home = Path.home()
    base_config_dir = home / ".config"
    if not base_config_dir.is_dir():
        os.mkdir(str(base_config_dir))
    config_dir = base_config_dir / "mathicsscript"
    if not config_dir.is_dir():
        os.mkdir(str(config_dir))

    settings_file = config_dir / "settings.m"
    if not settings_file.is_file():
        import mathicsscript

        srcfn = Path(mathicsscript.__file__).parent / "user-settings.m"
        try:
            with open(srcfn, "r") as src:
                buffer = src.readlines()
        except IOError:
            print(f"'{srcfn}' was not found.")
            return ""
        try:
            with open(settings_file, "w") as dst:
                for c in buffer:
                    dst.write(c)
        except IOError:
            print(f" '{settings_file}'  cannot be written.")
            return ""
    return settings_file


def load_settings_file(shell):
    """
    Read in or "autoload" Mathics3 code to initialize some settings.
    """
    autoload_files(shell.definitions, get_srcdir(), "autoload")
    settings_file = ensure_settings()
    if settings_file == "":
        return
    with open(settings_file, "r") as src:
        feeder = MathicsFileLineFeeder(src)
        try:
            while not feeder.empty():
                evaluation = Evaluation(
                    shell.definitions,
                    output=TerminalOutput(shell),
                    catch_interrupt=False,
                    format="text",
                )
                query = evaluation.parse_feeder(feeder)
                if query is None:
                    continue
                evaluation.evaluate(query)
        except KeyboardInterrupt:
            shell.errmsg("\nKeyboardInterrupt")
    return True


Evaluation.format_output = format_output


case_sensitive = {"case_sensitive": False}


@click.command(context_settings=dict(help_option_names=["-h", "-help", "--help"]))
@click.option(
    "--edit-mode",
    "-e",
    type=click.Choice(["emacs", "vi"], **case_sensitive),
    help="Set initial edit mode (when using prompt toolkit only)",
)
@click.version_option(version=__version__)
@click.option(
    "--full-form/--no-full-form",
    "-F",
    default=False,
    required=False,
    show_default=True,
    is_flag=True,
    help="If true, show how input was parsed to FullForm",
)
@click.option(
    "--persist",
    default=False,
    required=False,
    is_flag=True,
    help="go to interactive shell after evaluating FILE or -e",
)
@click.option(
    "--quiet",
    "-q",
    default=False,
    is_flag=True,
    required=False,
    help="don't print message at startup",
)
@click.option(
    "--readline",
    type=click.Choice(readline_choices, case_sensitive=False),
    default="Prompt",
    show_default=True,
    help="""Readline method. "Prompt" is usually best. None is generally available and """
    """have the fewest features.""",
)
@click.option(
    "--completion/--no-completion",
    default=True,
    show_default=True,
    help=(
        "GNU Readline line editing. enable tab completion; "
        "you need a working GNU Readline for this option."
    ),
)
@click.option(
    "-charset",
    metavar="ENCODING",
    default=sys.getdefaultencoding() == "utf-8",
    show_default=True,
    help="Use encoding for output. Encodings can be any entry in $CharacterEncodings.",
)
@click.option(
    "--post-mortem/--no-post-mortem",
    show_default=True,
    help="go to post-mortem debug on a terminating system exception (needs trepan3k)",
)
@click.option(
    "--prompt/--no-prompt",
    default=True,
    show_default=True,
    help="Do not prompt In[] or Out[].",
)
@click.option(
    "--pyextensions",
    "-l",
    required=False,
    multiple=True,
    help="directory to load extensions in Python",
)
@click.option(
    "-c",
    "-code",
    "--code",
    help="Give Mathics3 source code to execute. This may be given "
    "multiple times. Sets --quiet and --no-completion",
    multiple=True,
    required=False,
)
@click.option(
    "-f",
    "-file",
    "--file",
    type=click.Path(readable=True),
    help=("Give a file containing Mathics3 source code to execute."),
)
@click.option(
    "-s",
    "--style",
    metavar="PYGMENTS-STYLE",
    type=str,
    help=("Set pygments style. Use 'None' if you do not want any pygments styling."),
    required=False,
)
@click.option(
    "--pygments-tokens/--no-pygments-tokens",
    default=False,
    help=("Show pygments tokenization of output."),
    required=False,
)
@click.option(
    "--strict-wl-output/--no-strict-wl-output",
    default=False,
    help=("Most WL-output compatible (at the expense of usability)."),
    required=False,
)
@click.option(
    "--asymptote/--no-asymptote",
    default=True,
    show_default=True,
    help=(
        "Use asymptote for 2D and 3D Graphics; "
        "you need a working asymptote for this option."
    ),
)
@click.option(
    "--matplotlib/--no-matplotlib",
    default=True,
    show_default=True,
    help=(
        "Use matplotlib for 2D Graphics; "
        "you need a working matplotlib for this option. "
        "If set, this will take precedence over asymptote for 2D Graphics."
    ),
)
@click.argument("file", nargs=1, type=click.Path(readable=True), required=False)
def main(
    edit_mode,
    full_form,
    persist,
    quiet,
    readline,
    completion,
    charset,
    post_mortem,
    prompt,
    pyextensions,
    code,
    file,
    style,
    pygments_tokens,
    strict_wl_output,
    asymptote,
    matplotlib,
) -> int:
    """A command-line interface to Mathics.

    Mathics3 is a general-purpose computer algebra system.
    """

    exit_rc = 0
    quit_command = "CTRL-BREAK" if sys.platform == "win32" else "CONTROL-D"

    extension_modules = []
    if pyextensions:
        for ext in pyextensions:
            extension_modules.append(ext)

    definitions.set_line_no(1)
    # Set a default value for $ShowFullFormInput to False.
    # Then, it can be changed by the settings file (in WL)
    # and overwritten by the command line parameter.
    for setting_name, setting_value in (
        ("$ShowFullFormInput", full_form),
        ("$UseAsymptote", asymptote),
        ("$UseMatplotlib", matplotlib),
    ):
        definitions.set_ownvalue(
            f"Settings`{setting_name}", from_python(True if setting_value else False)
        )

    if os.environ.get("NO_COLOR", False) and style not in (None, "None"):
        print('Environment variable NO_COLOR set when "style" option given.')
        print("NO_COLOR setting ignored.")

    if post_mortem:
        try:
            from trepan.post_mortem import post_mortem_excepthook
        except ImportError:
            print(
                "trepan3k is needed for post-mortem debugging --post-mortem option ignored."
            )
            print("And you may want also trepan3k-mathics3-plugin as well.")
        else:
            sys.excepthook = post_mortem_excepthook

    readline = "none" if (code or file and not persist) else readline.lower()
    if readline == "prompt":
        from mathicsscript.termshell_prompt import TerminalShellPromptToolKit

        shell = TerminalShellPromptToolKit(
            definitions, completion, charset, prompt, edit_mode
        )
    elif readline == "gnu":
        from mathicsscript.termshell_gnu import TerminalShellGNUReadline

        shell = TerminalShellGNUReadline(definitions, completion, charset, prompt)
    else:
        shell = TerminalShellCommon(definitions, False, charset, prompt)

    load_settings_file(shell)
    style_from_settings_file = definitions.get_ownvalue("Settings`$PygmentsStyle")
    if style_from_settings_file is not SymbolNull and style is None:
        style = style_from_settings_file
    shell.setup_pygments_style(style)

    if file:
        if not os.path.exists(file):
            print(f"\nFile {file} does not exist; skipping reading.")
            file = None
        elif os.path.isdir(file):
            print(f"\nFile {file} does is a directory; skipping reading.")
            file = None
        else:
            try:
                with open(file, "r") as ifile:
                    feeder = MathicsFileLineFeeder(ifile)
                    try:
                        while not feeder.empty():
                            evaluation = Evaluation(
                                shell.definitions,
                                output=TerminalOutput(shell),
                                catch_interrupt=False,
                                format="text",
                            )
                            query = evaluation.parse_feeder(feeder)
                            if query is None:
                                continue
                            evaluation.evaluate(query, timeout=settings.TIMEOUT)
                    except KeyboardInterrupt:
                        print("\nKeyboardInterrupt")
            except Exception as e:
                print(f"\nError reading {file}: {e}; skipping reading.")
                file = None
            else:
                definitions.set_line_no(1)

    if code:
        for expr in code:
            evaluation = Evaluation(
                shell.definitions, output=TerminalOutput(shell), format="text"
            )
            shell.terminal_formatter = None
            result = evaluation.parse_evaluate(expr, timeout=settings.TIMEOUT)
            shell.print_result(result, prompt, "text", strict_wl_output)

            # After the next release, we can remove the hasattr test.
            if hasattr(evaluation, "exc_result"):
                if evaluation.exc_result == Symbol("Null"):
                    exit_rc = 0
                elif evaluation.exc_result == Symbol("$Aborted"):
                    exit_rc = -1
                elif evaluation.exc_result == Symbol("Overflow"):
                    exit_rc = -2
                else:
                    exit_rc = -3

        if not persist:
            return exit_rc

    if file is not None:
        with open(file, "r") as ifile:
            feeder = MathicsFileLineFeeder(ifile)
            try:
                while not feeder.empty():
                    evaluation = Evaluation(
                        shell.definitions,
                        output=TerminalOutput(shell),
                        catch_interrupt=False,
                        format="text",
                    )
                    query = evaluation.parse_feeder(feeder)
                    if query is None:
                        continue
                    evaluation.evaluate(query, timeout=settings.TIMEOUT)
            except KeyboardInterrupt:
                print("\nKeyboardInterrupt")

        if not persist:
            return exit_rc

    if not quiet and prompt:
        print(f"\nMathicscript: {__version__}, {version_string}\n")
        print(license_string + "\n")
        print(f"Quit by evaluating Quit[] or by pressing {quit_command}.\n")
    # If defined, full_form and style overwrite the predefined values.
    definitions.set_ownvalue(
        "Settings`$ShowFullFormInput", SymbolTrue if full_form else SymbolFalse
    )

    definitions.set_ownvalue(
        "Settings`$PygmentsShowTokens", from_python(pygments_tokens)
    )
    definitions.set_ownvalue("Settings`MathicsScriptVersion", from_python(__version__))
    definitions.set_attribute(
        "Settings`MathicsScriptVersion", attribute_string_to_number["System`Protected"]
    )
    definitions.set_attribute(
        "Settings`MathicsScriptVersion", attribute_string_to_number["System`Locked"]
    )

    definitions.set_line_no(1)
    interactive_eval_loop(shell, charset, prompt, strict_wl_output)
    return exit_rc


if __name__ == "__main__":
    sys.exit(main())
