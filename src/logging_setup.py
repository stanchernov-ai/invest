"""Single place to configure pipeline logging.

Each job entrypoint calls configure_logging() so the three split functions
(prepare / debate / deliver) all emit the same INFO-level stdout format that
Application Insights captures. Idempotent — safe to call more than once."""
import logging
import sys

_CONFIGURED = False


def configure_logging() -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger()
    if _CONFIGURED:
        return logger

    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
    logger.addHandler(ch)

    _CONFIGURED = True
    return logger
