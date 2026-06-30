"""Pre-start DB readiness probe."""

import logging

from sqlmodel import select
from tenacity import after_log, before_log, retry, stop_after_attempt, wait_fixed

from promt_engine_service.core.deps import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_TRIES = 60 * 5
WAIT_SECONDS = 5


@retry(
    stop=stop_after_attempt(MAX_TRIES),
    wait=wait_fixed(WAIT_SECONDS),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.WARN),
)
def init() -> None:  # pragma: no cover
    """Probe the DB until it answers a trivial SELECT."""
    try:
        with engine.session() as session:
            session.exec(select(1))
    except Exception as exc:
        logger.error(exc)
        raise


def main() -> None:  # pragma: no cover
    """Run the pre-start probe."""
    logger.info("Initializing service")
    init()
    logger.info("Service finished initializing")


if __name__ == "__main__":  # pragma: no cover
    main()
