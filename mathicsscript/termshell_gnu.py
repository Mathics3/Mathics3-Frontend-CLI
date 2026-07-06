# -*- coding: utf-8 -*-
#   Copyright (C) 2020-2022, 2025-2026 Rocky Bernstein <rb@dustyfeet.com>

import atexit
import os
import os.path as osp
import sys
import re

try:
    from readline import read_init_file
except (ImportError, ModuleNotFoundError):
    # Not sure what to do here: nothing is probably safe.
    def read_init_file(_: str):
        return


from typing import Final
from mathicsscript.bindkeys import read_inputrc
from mathicsscript.termshell import (
    CONFIGDIR,
    HISTSIZE,
    TerminalShellCommon,
    USER_INPUTRC,
)
from mathics.core.symbols import strip_context
from mathicsscript.settings import NAMED_CHARACTERS

try:
    from readline import (
        parse_and_bind,
        read_history_file,
        set_completer,
        set_completer_delims,
        set_history_length,
        write_history_file,
    )

    have_full_readline = True
except (ImportError, ModuleNotFoundError):
    have_full_readline = False

    def null_fn(*_):
        return

    def write_history_file(_: str):
        return

    parse_and_bind = read_history_file = set_history_length = null_fn
    set_completer = set_completer_delims = null_fn
except Exception:
    # Catch any other exceptions (like access violation on Windows)
    # when readline module is present but broken/unusable
    have_full_readline = False

    def null_fn(*_):
        return

    def write_history_file(_: str):
        return

    parse_and_bind = read_history_file = set_history_length = null_fn
    set_completer = set_completer_delims = null_fn


RL_COMPLETER_DELIMS_WITH_BRACE: Final[str] = " \t\n_~!@#%^&*()-=+{]}|;:'\",<>/?"
RL_COMPLETER_DELIMS: Final[str] = " \t\n_~!@#%^&*()-=+[{]}\\|;:'\",<>/?"

HISTFILE: Final[str] = osp.join(CONFIGDIR, "history-gnu")


class TerminalShellGNUReadline(TerminalShellCommon):
    def __init__(
        self,
        definitions,
        want_readline: bool,
        want_completion: bool,
        use_unicode: bool,
        prompt: bool,
    ):
        super().__init__(definitions, want_completion, use_unicode, prompt)

        # Try importing readline to enable arrow keys support etc.
        self.using_readline = False
        self.history_length = definitions.get_config_value("$HistoryLength", HISTSIZE)
        if have_full_readline and want_readline:
            self.using_readline = sys.stdin.isatty() and sys.stdout.isatty()
            self.ansi_color_re = re.compile("\033\\[[0-9;]+m")
            if want_completion:
                set_completer(
                    lambda text, state: self.complete_symbol_name(text, state)
                )

                self.named_character_names = set(
                    NAMED_CHARACTERS["named-characters"].keys()
                )

                # Make _ a delimiter, but not $ or `
                # set_completer_delims(RL_COMPLETER_DELIMS)
                set_completer_delims(RL_COMPLETER_DELIMS_WITH_BRACE)

                # GNU Readling inputrc $include's paths are relative to itself,
                # so chdir to its directory before reading the file.
                read_inputrc(read_init_file, use_unicode)
                if osp.isfile(USER_INPUTRC):
                    if os.access(USER_INPUTRC, os.R_OK):
                        read_init_file(USER_INPUTRC)
                    else:
                        sys.stderr.write(
                            f"Can't read user inputrc file {USER_INPUTRC}; skipping\n"
                        )

                parse_and_bind("tab: complete")
                self.completion_candidates = []

            # History
            try:
                read_history_file(HISTFILE)
            except FileNotFoundError:
                # Create an empty history file.
                with open(HISTFILE, "w"):
                    pass
            except IOError:
                pass
            except:  # noqa
                # PyPy read_history_file fails
                pass

            set_history_length(self.history_length)
            atexit.register(self.user_write_history_file)

    def complete_interrupt_command(self, text, state):
        # Only complete from this fixed set
        completions = [
            w
            for w in ["abort", "continue", "debugger", "exit", "inspect", "show"]
            if w.startswith(text)
        ]
        try:
            return completions[state]
        except IndexError:
            return None

    def complete_symbol_name(self, text, state):
        try:
            match = re.match(r"^(.*\\\[)([A-Z][a-z]*)$", text)
            if match:
                return self._complete_named_characters(
                    match.group(1), match.group(2), state
                )
            return self._complete_symbol_name(text, state)

        except Exception:
            # any exception thrown inside the completer gets silently
            # thrown away otherwise
            print("Unhandled error in readline completion")
        except:  # noqa
            raise

    def _complete_named_characters(self, prefix, text, state):
        r"""prefix is the text after \[. Return a list of named character names."""
        if state == 0:
            self.completion_candidates = [
                prefix + name + "]"
                for name in self.named_character_names
                if name.startswith(text)
            ]
            # self.completion_candidates = self.get_completion_symbol_candidates(prefix, text)
        try:
            return self.completion_candidates[state]
        except IndexError:
            return None

    def _complete_symbol_name(self, text, state):
        # The readline module calls this function repeatedly,
        # increasing 'state' each time and expecting one string to be
        # returned per call.
        if state == 0:
            self.completion_candidates = self.get_completion_candidates(text)
        try:
            return self.completion_candidates[state]
        except IndexError:
            return None

    def get_completion_candidates(self, text: str):

        brace_pos = text.rfind("[")
        if brace_pos >= 0:
            suffix = text[brace_pos + 1 :]
            prefix = text[: brace_pos + 1]
        else:
            prefix = ""
            suffix = text
        try:
            matches = self.definitions.get_matching_names(suffix + "*")
        except Exception:
            return []
        if "`" not in text:
            matches = [strip_context(m) for m in matches]
        return [prefix + m for m in matches]

    def user_write_history_file(self):
        try:
            set_history_length(self.history_length)
            # print(f"Writing {HISTFILE}")
            write_history_file(HISTFILE)
        except:  # noqa
            pass
