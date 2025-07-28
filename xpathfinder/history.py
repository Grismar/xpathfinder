from lxml import etree
from copy import deepcopy
from typing import Optional

# noinspection PyProtectedMember
type State = str | etree._ElementTree


class HistoryManager:
    """
    Manages a simple linear history of text or document states, with undo/redo support.

    Usage:
        hist = HistoryManager()
        hist.add("state1")
        hist.add("state2")
        prev = hist.undo()  # returns "state1"
        next = hist.redo()  # returns "state2"
    """
    def __init__(self, max_size: int = None):
        # List of stored states
        self._history = []
        # Current pointer (index into _history)
        self._index = -1
        self._max_size = max_size

    @property
    def index(self) -> int:
        return self._index

    def add(self, state: str):
        """
        Add a new state. Any states ahead of the current position are discarded.
        """
        # Trim any future history
        if self._index < len(self._history) - 1:
            self._history = self._history[: self._index + 1]
        if not isinstance(state, str):
            state = deepcopy(state)
        self._history.append(state)
        if self._max_size is not None and len(self._history) > self._max_size:
            self._history.pop(0)
        else:
            self._index += 1

    def undo(self) -> Optional[str]:
        """
        Move one step back in history. Returns the previous state, or None if at oldest.
        """
        if self._index > 0:
            self._index -= 1
            return self._history[self._index]
        return None

    @property
    def can_redo(self):
        return self._index < len(self._history) - 1

    def redo(self) -> Optional[str]:
        """
        Move one step forward in history. Returns the next state, or None if at latest.
        """
        if self._index < len(self._history) - 1:
            self._index += 1
            return self._history[self._index]
        return None

    def current(self) -> Optional[str]:
        """
        Return the current state, or None if history is empty.
        """
        if 0 <= self._index < len(self._history):
            return self._history[self._index]
        return None

    def clear(self):
        """
        Clear all history states.
        """
        self._history.clear()
        self._index = -1

    def all(self) -> list:
        """
        Return a copy of the full history list.
        """
        return list(self._history)
