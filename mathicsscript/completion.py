# -*- coding: utf-8 -*-

# Copyright (C) 2021-2022, 2024-2026 Rocky Bernstein <rb@dustyfeet.com>
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

from enum import Enum
import os.path as osp
import re

from typing import Iterable, List, NamedTuple, Tuple

from mathics.core.symbols import strip_context
from mathics_pygments.lexer import Regex
from mathicsscript.settings import NAMED_CHARACTERS

from prompt_toolkit.completion import (
    CompleteEvent,
    Completer,
    Completion,
    WordCompleter,
)
from prompt_toolkit.document import Document

SYMBOLS = rf"[`]?({Regex.IDENTIFIER}|{Regex.NAMED_CHARACTER})(`({Regex.IDENTIFIER}|{Regex.NAMED_CHARACTER}))+[`]?"

# # The below is a more precise definition for a Mathics3 "word" or
# # "identifier", but it is wrong somehow.  NAMED_CHARACTER_START =
# rf"\\\[{Regex.IDENTIFIER}" FIND_MATHICS_WORD_RE = re.compile(
# rf"({NAMED_CHARACTER_START})|(?:.*[\[\(])?({SYMBOLS}$)" )
FIND_MATHICS_WORD_RE = re.compile(r"((?:\[)?[^\s\[\(\{]+)")

CHARGROUP_START = frozenset(["(", "[", "{", ","])


class TokenKind(Enum):
    Null = "Null"
    NamedCharacter = "NamedCharacter"
    Symbol = "Symbol"
    ASCII_Operator = "ASCII_Operator"
    EscapeSequence = "EscapeSequence"  # Not working yet


# TODO: "kind" could be an enumeration: of "Null", "Symbol", "NamedCharacter"
WordToken = NamedTuple("WordToken", [("text", str), ("kind", TokenKind)])


def get_datadir():
    datadir = osp.normcase(osp.join(osp.dirname(osp.abspath(__file__)), "data"))
    return osp.realpath(datadir)


class InterruptCompleter(Completer):
    """
    Completer for the simple command set: 'continue', 'abort', 'exit', 'show'.
    """

    COMMANDS = [
        "abort",
        "continue",
        "debugger",
        "exit",
        "inspect",
        "show",
    ]

    def get_completions(
        self, document: Document, complete_event
    ) -> Iterable[Completion]:
        word = document.get_word_before_cursor()
        for cmd in self.COMMANDS:
            if cmd.startswith(word):
                yield Completion(cmd, -len(word))


class Mathics3Completer(WordCompleter):
    def __init__(self, definitions):
        self.definitions = definitions
        self.completer = WordCompleter([])
        self.named_characters = sorted(NAMED_CHARACTERS["named-characters"].keys())

        # From WordCompleter, adjusted with default values
        self.ignore_case = True
        self.display_dict = {}
        self.meta_dict = {}
        self.WORD = False
        self.sentence = False
        self.match_middle = False
        self.pattern = None

        try:
            import ujson
        except ImportError:
            import json as ujson
        # Load tables from disk
        with open(osp.join(get_datadir(), "mma-tables.json"), "r") as f:
            _data = ujson.load(f)

        # @ is not really an operator
        self.ascii_operators = frozenset(_data["ascii-operators"])
        from mathics_scanner.characters import ALIASED_CHARACTERS

        self.escape_sequences = ALIASED_CHARACTERS.keys()

    def _is_space_before_cursor(self, text_before_cursor: str) -> bool:
        """Space before or no text before cursor."""
        return text_before_cursor == "" or text_before_cursor[-1:].isspace()

    def get_completions(
        self, document: Document, complete_event: CompleteEvent
    ) -> Iterable[Completion]:
        # Get word/text before cursor.
        word_before_cursor, kind = self.get_word_before_cursor_with_kind(document)
        if kind == TokenKind.Symbol:
            words = self.word_names
        elif kind == TokenKind.NamedCharacter:
            words = self.named_characters
        elif kind == TokenKind.ASCII_Operator:
            words = self.ascii_operators
        elif kind == TokenKind.EscapeSequence:
            words = self.escape_sequences
        else:
            words = []

        def word_matches(word: str) -> bool:
            """True when the word before the cursor matches."""

            if self.match_middle:
                return word_before_cursor in word
            else:
                return word.startswith(word_before_cursor)

        for a in words:
            if word_matches(a):
                display = self.display_dict.get(a, a)
                display_meta = self.meta_dict.get(a, "")
                yield Completion(
                    a,
                    -len(word_before_cursor),
                    display=display,
                    display_meta=display_meta,
                )

    def get_word_before_cursor_with_kind(
        self, document: Document
    ) -> Tuple[str, TokenKind]:
        """
        Get the word before the cursor and classify it into one of the kinds
        of tokens: NamedCharacter, AsciiOperator, Symbol, etc.


        If we have whitespace before the cursor this returns an empty string.
        """

        text_before_cursor = document.text_before_cursor

        if self._is_space_before_cursor(text_before_cursor=text_before_cursor):
            return WordToken("", TokenKind.Null)

        start = (
            document.find_start_of_previous_word(
                WORD=False, pattern=FIND_MATHICS_WORD_RE
            )
            or 0
        )

        word_before_cursor = text_before_cursor[len(text_before_cursor) + start :]
        text_before_word = text_before_cursor[: len(word_before_cursor)]
        if word_before_cursor.startswith(r"\["):
            return WordToken(word_before_cursor[2:], TokenKind.NamedCharacter)
        elif text_before_word.endswith(r"\["):
            return WordToken(word_before_cursor, TokenKind.NamedCharacter)
        elif text_before_word[-1:] in CHARGROUP_START:
            word_before_cursor = word_before_cursor
        elif word_before_cursor[1:] in CHARGROUP_START:
            word_before_cursor = word_before_cursor[1:]

        if word_before_cursor.isnumeric():
            return WordToken(word_before_cursor, TokenKind.Null)
        elif word_before_cursor in self.ascii_operators:
            return WordToken(word_before_cursor, TokenKind.ASCII_Operator)
        elif word_before_cursor.startswith("\1xb"):
            return WordToken(word_before_cursor, TokenKind.EscapeSequence)

        return word_before_cursor, TokenKind.Symbol

    @property
    def word_names(self) -> List[str]:
        names = self.definitions.get_names()
        short_names = [strip_context(m) for m in names]
        return list(names) + short_names
