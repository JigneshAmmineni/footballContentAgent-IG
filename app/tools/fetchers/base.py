from abc import ABC, abstractmethod

from app.models.raw_idea import RawIdea


class BaseFetcher(ABC):
    """All data fetchers implement this interface.
    Adding a new source = subclass BaseFetcher, implement fetch().
    NewsIngestAgent receives list[BaseFetcher] from Config and calls fetch() on each.
    """

    @abstractmethod
    def fetch(self) -> list[RawIdea]:
        ...

    @property
    def source_name(self) -> str:
        return self.__class__.__name__
