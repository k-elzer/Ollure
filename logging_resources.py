from logging import getLogger, Formatter as log_Formatter, FileHandler as log_FileHandler, INFO as log_INFO # renaming imported methods to avoid confusion
from os import getenv
from datetime import datetime
from pathlib import Path
from re import sub as re_sub
from fastapi import Response
from fastapi.responses import JSONResponse

from classes.logging_classes import *
from utils import get_client_ip, get_client_headers

# a module-level logger which will be used everywhere
logger = getLogger("honey_logger")


# helper method to normalize the raw request text to make it easier to read and work with in the logs
# (it simply removes some escaped characters, merges consecutive spaces into one and removes leading and trailing spaces)
def _normalize_raw_request_text(raw_request: str) -> str:
    """Make raw request text easier to scan in logs without touching byte-accurate hex dumps."""
    compact = raw_request.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    compact = re_sub(r"\s+", " ", compact)
    return compact.strip()


# SUGGESTION FROM COPILOT
def get_custom_headers(content_type: str | None = None) -> dict[str, str]:
    headers = {} # TODO: handle Transfer-Encoding: chunked header as well!
                 # TODO: CHECK FOR OTHER TYPES OF HEADERS AND MAYBE HANDLE THEM ON A PER-ENDPOINT BASIS

    if content_type is not None:
        headers["Content-Type"] = content_type

    return headers


# for JSON formatting
# ORIGINAL FROM: https://hadar.gr/json-pyhon-logging
# MODIFIED USING COPILOT
class JsonFormatter(log_Formatter):
    def format(self, record):

        # TODO: LOG ALSO SOMETHING LIKE IP ADDRESSES!

        # formatting according to the LogEntry class defined in logging_classes.py
        entry = LogEntry(
            time=datetime.fromtimestamp(record.created).isoformat() + "Z",
            source_ip = record.__dict__.get("source_ip"),
            http_method = record.__dict__.get("http_method"),
            endpoint = record.__dict__.get("endpoint"),
            status_code = record.__dict__.get("status_code"),
            streamed = record.__dict__.get("streamed"),
            headers = record.__dict__.get("headers") if "headers" in record.__dict__ else None,
            request_hex_dump = record.__dict__.get("request_hex_dump") if "request_hex_dump" in record.__dict__ else None,
            error_data = record.__dict__.get("error_data") if "error_data" in record.__dict__ else None,
            request_body = record.__dict__.get("request_body") if "request_body" in record.__dict__ else None,
            response = record.__dict__.get("response") if "response" in record.__dict__ else None # "reponse" might be None because of the /api/copy response structure, so allow 'None' values!
        )

        return entry.model_dump_json(exclude_defaults = True, exclude_none = True) # TODO: REMOVE THE EXCLUDES BECAUSE THEY SHOULDN'T BE NEEDED ANYMORE


# setup for JSON formatting
# ORIGINAL FROM: https://hadar.gr/json-pyhon-logging
# MODIFIED USING COPILOT FOR DYNAMIC FILENAME AND LOG DIRECTORY CONFIGURATION/HANDLING
def configure_logging(filename="in-out.log", log_dir: str | None = None):
    filename = getenv("LOG_FILE", filename) # use an environment variable, if present. Otherwise, use whatever the filename is set to (default name is "in-out.log")
    log_dir = log_dir or getenv("LOG_DIR", "logs") # use given logging directory, if given. Otherwise use environment variable or just default to folder name "/logs"

    # Resolve relative paths against the process working directory and create the folder if missing.
    resolved_log_dir = Path(log_dir).expanduser()
    if not resolved_log_dir.is_absolute():
        resolved_log_dir = Path.cwd() / resolved_log_dir
    resolved_log_dir.mkdir(parents=True, exist_ok=True)

    h = log_FileHandler(resolved_log_dir / filename, encoding="utf-8") # encoding is mainly for safety, ensuring consistency
    h.setFormatter(JsonFormatter())
    getLogger().addHandler(h)

    # TODO: figure out if this should be changed to something else (container runs with "--log-level critical" after all),
    # TODO: or if it should just be removed
    logger.setLevel(log_INFO)
    return logger


# method used for both logging and returning responses.
# All interactions should be logged, and this method handles this, even when no response is returned (e.g., /api/copy)
def log_and_return(
        request,
        request_body,
        status_code,
        response,
        error_data = None,
        streamed = None,
        final_stream_chunk = None):

    if response is not None and not isinstance(response, dict):
        response = response.model_dump(by_alias = True, exclude_defaults = True, exclude_none = True)

    # initialize the data to be logged (some additional data may be added later)
    extra = {
        "source_ip": get_client_ip(),
        "http_method": request.method,
        "endpoint": request.url.path,
        "status_code": status_code,
        "streamed": streamed,
        "headers": get_client_headers() if getenv("LOG_HEADERS", "True").lower() in ['true', '1', 't'] else None,
        "request_hex_dump": getattr(request.state, "raw_body_hex", None),
        "response": response
    }

    # if error_data is neither None, nor an empty dict, there must've been errors, so include this error data in the log entry created later!
    if error_data:
        # Keep error payload flexible, but normalize raw_request text for readability.
        error_data_to_log = dict(error_data)
        raw_request = error_data_to_log.get("raw_request")
        if isinstance(raw_request, str):
            # normalize the raw request text to make it easier to read in the logs
            error_data_to_log["raw_request"] = _normalize_raw_request_text(raw_request)

        extra["error_data"] = error_data_to_log

    # add the request body to the log entry, if it exists
    elif request_body is not None:
        request_body = request_body.model_dump(by_alias = True, exclude_defaults = True, exclude_none = True)
        extra["request_body"] = request_body

    # base case, mainly to handle GET requests which do not have a request body
    else:
        extra["request_body"] = None

    logger.info("creating log entry!", extra=extra) # ! THIS CREATES THE LOG ENTRY!

    # if response was streamed, this will contain the final chunk of the stream,
    # which should be returned as the final responnse
    # (this is not what is logged, just what is returned at the end, so it still logs the response string)
    if final_stream_chunk is not None:
        return final_stream_chunk

    # return the response, if any should be returned
    if request.url.path == "/":
        return Response(
            status_code = status_code,
            content = "Ollama is running",
            headers = get_custom_headers("text/plain; charset=utf-8"),
        )
    elif response is not None:
        return JSONResponse(
            status_code = status_code,
            content = response,
            # media_type="application/json; charset=utf-8",
            headers = get_custom_headers("application/json; charset=utf-8"),
        )
    else:
        # responses of "None" indicate that no response content/body should be returned
        # (e.g., /api/copy returns an empty response body, so this handles such cases)
        return Response(
            status_code = status_code, 
            headers = get_custom_headers("text/plain; charset=utf-8"))
