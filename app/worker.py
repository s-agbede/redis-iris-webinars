"""Run indexing in its own process; app.runtime restarts it after process failure."""

import logging
import signal
from types import FrameType

from redis import Redis
from redisvl.index import SearchIndex

from app.embeddings import build_vectorizer
from app.product_store import ProductStore
from app.settings import get_settings
from app.sync import SyncWorker


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    with Redis.from_url(settings.redis_url, socket_connect_timeout=3, socket_timeout=15) as client:
        store = ProductStore(client, settings)
        encoder = build_vectorizer(settings)
        index = SearchIndex.from_existing(settings.products_index, redis_client=client)
        worker = SyncWorker(store, encoder, index)

        def stop(signum: int, frame: FrameType | None) -> None:
            worker.stopping.set()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        worker.run()


if __name__ == "__main__":
    main()
