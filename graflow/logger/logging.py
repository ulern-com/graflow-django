import functools
import logging
import time

logger = logging.getLogger(__name__)


def log_node(node_name: str):
    """decorator for adding logging to every node and action in FlowStateGraph"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(state, *args, **kwargs):
            logger.info(f"[ENTER] {node_name}")
            # saving start time
            start = time.perf_counter()

            try:
                # running inner function
                result = func(state, *args, **kwargs)
                # capture end time
                elapsed = (time.perf_counter() - start) * 1000
                logger.info(f"[EXIT] {node_name} ({elapsed:.2f} ms)")

                return result
            except Exception as e:
                elapsed = (time.perf_counter() - start) * 1000
                logger.error(f"[ERROR] {node_name} ({elapsed:.2f} ms) -> {type(e).__name__}: {e}")
                raise

        return wrapper

    return decorator
