"""Small per-process cache of query vectors; never caches search results."""

from collections import OrderedDict
from collections.abc import Callable
from threading import Lock


class EmbeddingCache:
    def __init__(self, capacity: int = 256) -> None:
        self.capacity = capacity
        self.entries: OrderedDict[tuple[str, str], list[float]] = OrderedDict()
        self.lock = Lock()

    def get(self, model: str, query: str, embed: Callable[[str], list[float]]) -> list[float]:
        key = (model, query)
        with self.lock:
            if key in self.entries:
                self.entries.move_to_end(key)
                return self.entries[key]
        # Do not serialize unrelated embeddings behind a global lock.
        vector = embed(query)
        with self.lock:
            self.entries[key] = vector
            self.entries.move_to_end(key)
            while len(self.entries) > self.capacity:
                self.entries.popitem(last=False)
        return vector
