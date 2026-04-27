from dataclasses import dataclass
from typing import Optional


@dataclass
class Shift:
    date: str        # YYYY-MM-DD
    start: str       # HH:MM
    end: str         # HH:MM
    type: Optional[str] = None

    @property
    def event_id(self) -> str:
        """Stable ID used as Google Calendar extendedProperty for deduplication."""
        return f"shift{self.date.replace('-', '')}{self.start.replace(':', '')}"

    @property
    def summary(self) -> str:
        label = f" – {self.type}" if self.type else ""
        return f"Dienst{label}"

    def __repr__(self) -> str:
        t = f" ({self.type})" if self.type else ""
        return f"Shift({self.date} {self.start}–{self.end}{t})"
