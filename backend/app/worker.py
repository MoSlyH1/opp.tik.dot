"""Background ingester for Docker / any long-running host."""

import logging
import os
import time

from . import create_app
from .ingest import run
from .models import Item

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(message)s")
log = logging.getLogger("worker")

INTERVAL_HOURS = float(os.environ.get("INGEST_INTERVAL_HOURS", "6"))


def main():
    app = create_app()
    while True:
        with app.app_context():
            empty = Item.query.count() == 0
            log.info("ingest starting (%s)", "full, empty catalogue" if empty else "incremental")
            log.info("ingest done: %s", run(max_queries=None if empty else 12))
        time.sleep(INTERVAL_HOURS * 3600)


if __name__ == "__main__":
    main()
