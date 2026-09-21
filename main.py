from json import loads as json_loads, JSONDecodeError

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from logging_resources import *
from utils import *
from classes import request_classes, response_classes
from endpoints import root, generate, chat, embed, tags, ps, show, create, copy, pull, push, delete, version, v1models

# create the API for the script
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None) # ! LIVE HONEYPOT SHOULD NOT HAVE DOCUMENTATION ENDPOINTS ENABLED

# configure the logger using the "configure_logging()" created in 'logging_resources.py'
# "configure_logging()" has a default logging file name; "in-out.log". Pass it another name for a different honeypot log file name!
logger = configure_logging()

# middleware for instantiating request context and preparing request body for handling
# SUGGESTED BY COPILOT - the rest of the ip-code was also suggested by Copilot!
# EXTENDED BY COPILOT TO ALSO GENERATE SESSION ID
@app.middleware("http")
async def request_data_prep(request: Request, call_next):
    client_ip = request.client.host if request.client is not None else None
    user_agent = request.headers.get("user-agent") # get the "User-Agent" header from the request, if it exists (header name is supposed to be lowercase!)

    # handle missing "User-Agent" header cases:
    if user_agent is None:
        user_agent = "unknown_user_agent"

    sess_id = get_or_create_session(client_ip, user_agent)
    headers = dict(request.headers.items()) if request.headers is not None else None
    set_request_context(client_ip=client_ip, headers=headers, session_id=sess_id)

    # cache the raw body before FastAPI/Pydantic parses it to avoid losing dropped data
    try:
        raw_body = await request.body()
    except Exception:
        raw_body = b""

    # store the raw body (and a hex dump of it) in the request state to potentially use it later in the exception handler
    raw_body_text = raw_body.decode("utf-8", errors="replace")
    request.state.raw_body = raw_body
    request.state.raw_body_hex = raw_body.hex()
    request.state.raw_body_text = raw_body_text

    # check if the raw body looks like JSON and, if so, try to parse it as such
    content_type = request.headers.get("content-type", "") or ""
    stripped_body = raw_body_text.lstrip()
    if stripped_body.startswith(("{", "[")):
        try:
            json_loads(raw_body_text)
        except JSONDecodeError:
            pass

        # always make sure Content-Type headers exist and contain "application/json"
        # Ollama gives the same json-errors regardless of "text/plain" and "application/json", so this makes error handling easier
        if "application/json" not in content_type.lower():
            headers = list(request.scope.get("headers", []))
            for index, (name, value) in enumerate(headers):
                if name == b"content-type":
                    headers[index] = (name, b"application/json")
                    break
            else:
                headers.append((b"content-type", b"application/json"))
            request.scope["headers"] = headers

    return await call_next(request)


# ================= ERROR HANDLING ==================

# Main error handler of the honeypot.
# Each endpoint does its own error handling, assuming request body contained valid JSON.
# ERROR TYPE AND MESSAGE CHECKS SUGGESTED BY COPILOT; modified to fit Ollama's error messages
@app.exception_handler(RequestValidationError)
async def http_exc_handler(request: Request, exc: RequestValidationError):
    status_code = 400
    error_data = {}
    response = response_classes.ErrorResponse(error="")

    # get the raw request body to see the input that caused the error
    # CODE FOR GETTING RAW DATA FROM THE REQUEST BODY WAS A SUGGESTION FROM COPILOT
    raw_request = getattr(request.state, "raw_body_text", None)

    # Get the error that caused the exception!
    # ? ("exc.errors()" is a list of errors, but seems to only ever contain one error, even when there're multiple problems in a request)
    error = exc.errors()[-1]

    # try to get various parts of the error
    error_type = error.get("type", "")
    error_msg = error.get("msg", "")    # error messages tend to have a "msg" field, but it doesn't always contain the full error message/description,
    error_ctx = error.get("ctx", {})    # so try to get the "ctx" field as well, as it tends to contain this description if "msg" didn't
    error_input = error.get("input", "")
    error_ctx_msg = error_ctx.get("error", "") if isinstance(error_ctx, dict) else ""

    # setting a default error message (used in case of unknown/unhandled error types) to the whole error,
    # since this can potentially greatly help debugging later in case of weird behavior or cases that hadn't been considered/encountered
    error_data["error_msg"] = f"unknown error: {error}"
    response.error = "An error occurred."

    # get the raw request text (mainly for finding the cause of an error)
    raw_request_text = raw_request.strip() if raw_request else ""

    # find the cause of the error in the raw request text
    error_location_character = "}"
    try:
        error_location_index = error.get("loc", (0,0))[1]
        error_location_character = raw_request_text[error_location_index if isinstance(error_location_index, int) else 0]
        error_location_character = (f"\\{error_location_character}" if error_location_character in ['\\', '\''] else error_location_character)
    except:
        pass

    if error_type == "missing":
        error_data["error_msg"] = f"{error_type}: {error_msg}"
        status_code = 404 # this is the only discovered invalid JSON case with non-400 Error
        if "Field required" in error_msg and error_input is None:
            # error for when the request didn't contain a JSON object (i.e., missing a '{}') at all
            response.error = "missing request body"
        else:
            # error for when the request only contained an empty JSON object (i.e., a '{}')
            response.error = "model '' not found"

    if error_type == "json_invalid":
        error_data["error_msg"] = f"{error_type}: {error_ctx_msg}" # save specific error for logging purposes
        if "Expecting property" in error_ctx_msg:
            error_data["error_msg"] = f"{error_type}: {error_msg}"
            # if request started correctly (i.e., with a '{'), the error must've been after this:
            if raw_request_text.startswith("{"):
                # if request wasn't simply empty (in which case it should've been caught by the "missing" error type):
                if error_location_character != '{':
                    # assume error was caused by the second character, e.g., because it was a single-quote or a backslash
                    response.error = f"invalid character '{error_location_character}' looking for beginning of object key string"
            else:
                # this error assumes the cause is a comma on the final key-value pair, where there shouldn't be one
                response.error="invalid character '}' looking for beginning of object key string"
        elif "Expecting value" in error_ctx_msg:
            # error given when a value for a key is missing (e.g., {"model": })
            # (error message should describe the invalid character rather than the hard-coded '}', but this mostly fine like this since this is an unlikely error to get)
            response.error = f"invalid character '{error_location_character}' looking for beginning of value"
        elif "Expecting ':'" in error_ctx_msg:
            # error given when a colon is missing between a key and value
            response.error = f"invalid character '{error_location_character}' after object key"
        elif "Expecting ','" in error_ctx_msg:
            # this error tends to be caused by missing comma between two key-value pairs:
            response.error = f"invalid character '{error_location_character}' after object key:value pair"
        elif "Invalid control" in error_ctx_msg:
            # error given when there's a single-quote in the middle of a key-value pair
            # (e.g. {"model': "gemma3:4b"} or {"model": "gemma3:4b'}, but not at the start of either a key or a value)
            response.error = "invalid character '\\n' in string literal"
        elif "Invalid \\escape" in error_ctx_msg:
            # error given when trying to escape a single-quote inside a prompt (haven't yet found other causes of this error)
            response.error = "invalid character '\\'' in string escape code"
        elif "Extra data" in error_ctx_msg:
            response.error = "json: cannot unmarshal string into Go value of type api.GenerateRequest"
        else:
            # default error for invalid JSON, in case the exact error message hasn't been handled yet
            response.error="invalid json in request body"

    # these errors tend to only happen with text/plain,
    # but the middleware now always sets Conten-Type headers to "application/json",
    # so this should now be redundant!
    # TODO: Remove this error type handling later as it should now be redundant!
    if error_type == "model_attributes_type":
        error_data["error_msg"] = f"{error_type}: {error_msg}"
        # some errors stem from the raw request starting (after the initial '{') with an invalid character,
        # e.g., a single-quote (normally in the case of single-quoted JSON, which is invalid),
        # or in the form of a backslash, indicating an escaped character
        # (this case is just in case the request body was malformed and a backslash happened to the first character after the initial '{')
        second_character = raw_request_text[1:].lstrip()[0] if len(raw_request_text) > 1 else ""
        second_character = (f"\\{second_character}" if second_character in ['\\', '\''] else second_character)
        # this error occurs when the request has:
        # 1. "text/plain" as the "Content-Type" header
        # 2. uses single-quotes instead of the JSON-standard double-quotes, e.g., {'model': 'gemma3:4b'} instead of {"model": "gemma3:4b"}
        if "Input should be a valid dictionary or object" in error_msg:
            if second_character != '"':
                response.error = f"invalid character '{second_character}' looking for beginning of object key string"
            else:
                response.error = f"invalid character '{error_location_character}' looking for beginning of object key string"

    if raw_request is not None:
        error_data["raw_request"] = raw_request

    # log and return the response; include error data if any was present
    return log_and_return(
        request,
        None,
        status_code,
        response,
        error_data = error_data,
    )



# ==================== ENDPOINTS ====================

@app.get("/")
def APIRoot(request: Request):
    return root.ep_root(request)

@app.post("/api/generate")
def APIGenerate(request: Request, body: request_classes.GenerateRequest):
    return generate.ep_generate(request, body)

@app.post("/api/chat")
def APIChat(request: Request, body: request_classes.ChatRequest):
    return chat.ep_chat(request, body)

@app.post("/api/embed")
def APIEmbed(request: Request, body: request_classes.EmbedRequest):
    return embed.ep_embed(request, body)

@app.get("/api/tags")
def APIModels(request: Request):
    return tags.ep_models(request)

@app.get("/api/ps")
def APIRunningModels(request: Request):
    return ps.ep_running_models(request)

@app.post("/api/show")
def APIShow(request: Request, body : request_classes.ShowRequest):
    return show.ep_show(request, body)

@app.post("/api/create")
def APICreate(request: Request, body: request_classes.CreateRequest):
    return create.ep_create(request, body)

@app.post("/api/copy")
def APICopy(request: Request, body: request_classes.CopyRequest):
    return copy.ep_copy(request, body)

@app.post("/api/pull")
def APIPull(request: Request, body: request_classes.PullRequest):
    return pull.ep_pull(request, body)

@app.post("/api/push")
def APIPush(request: Request, body: request_classes.PushRequest):
    return push.ep_push(request, body)

@app.delete("/api/delete")
def APIDelete(request: Request, body: request_classes.DeleteRequest):
    return delete.ep_delete(request, body)

@app.get("/api/version")
def APIVersion(request: Request):
    return version.ep_version(request)

@app.get("/v1/models")
def APIV1Models(request: Request):
    return v1models.ep_v1_models(request)
