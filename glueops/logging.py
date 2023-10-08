import logging
import json
import inspect

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

def configure(name=None, level=logging.INFO):
    if name is None:
        frame = inspect.stack()[1]
        module = inspect.getmodule(frame[0])
        name = module.__name__ if module else "defaultLogger"

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Check if logger already has handlers attached, to avoid duplicate logs
    if not logger.hasHandlers():
        json_formatter = JsonFormatter()
        handler = logging.StreamHandler()
        handler.setFormatter(json_formatter)
        logger.addHandler(handler)

    return logger
