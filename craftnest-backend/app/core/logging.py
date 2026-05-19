import logging
import sys
import structlog
from structlog.contextvars import merge_contextvars
from app.core.config import settings

def configure_logging():
    # Clear existing handlers on the root logger
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Define standard processors to build the log structure
    shared_processors = [
        merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Select renderer based on the environment
    if settings.ENV == "development":
        # Pretty print with color in local development
        renderer = structlog.dev.ConsoleRenderer()
    else:
        # Standard strict JSON lines in production with exact key naming mapped
        json_renderer = structlog.processors.JSONRenderer()
        
        def renderer(logger, name, event_dict):
            # Map 'event' key to 'message'
            if "event" in event_dict:
                event_dict["message"] = event_dict.pop("event")
            # Map 'logger' key to 'logger_name'
            if "logger" in event_dict:
                event_dict["logger_name"] = event_dict.pop("logger")
            # Map 'status_code' key to 'status' as well
            if "status_code" in event_dict:
                event_dict["status"] = event_dict["status_code"]
            return json_renderer(logger, name, event_dict)

    # Configure structlog
    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure stdlib formatter to map logging events via structlog's processor pipeline
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processor=renderer,
    )

    # Direct standard output stream handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO if not settings.DEBUG else logging.DEBUG)

    # Route uvicorn standard logs into our formatted stream handler
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        log = logging.getLogger(logger_name)
        log.handlers = [handler]
        log.propagate = False

configure_logging()
logger = structlog.get_logger("craftnest")
