import inspect
import json
import logging
from typing import List, Union


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            'timestamp': self.formatTime(record, self.datefmt),
            'name': record.name,
            'level': record.levelname,
            'message': record.getMessage(),
        }

        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


def configure(
    name: str=None,
    level: Union[str, int]=logging.ERROR,
    handlers: List[logging.Handler]= None
) -> logging.Logger:
    """Configure and return a logger with GlueOps default configuration

    Args:
        name (str, optional): The name of the logger. Defaults to None.
        level (Union[str, int], optional): The log level, as an int or str. Defaults to logging.ERROR.
            Must be less restrictive than the level applied to additional handlers for those handlers to receive logs
        handlers (List[logging.Handler], optional): List of any additional handlers that may be desired. Defaults to None.

    Returns:
        logging.Logger: Instance of configured logger
    """
    if name is None:
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        name = module.__name__ if module else "defaultLogger"

    if handlers is None:
        handlers = []

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # create default formatter and handler
    default_handler = logging.StreamHandler()
    json_formatter = JsonFormatter()
    default_handler.setFormatter(json_formatter)

    # remove handlers not configured by this module
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # add default handler
    logger.addHandler(default_handler)

    # add custom handlers
    for handler in handlers:
        logger.addHandler(handler)

    return logger
