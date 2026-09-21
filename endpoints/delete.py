from fastapi import Request
from classes.request_classes import *
from classes.response_classes import *
from utils import *
from logging_resources import *



def ep_delete(request: Request, body: DeleteRequest):
    resp = None
    status_code = 200

    # Ollama accepts model names with leading and/or trailing spaces,
    # and doesn't keep them for the various fields in the response,
    # so .strip() the model name before performing any other checks.
    # ".strip()" also fails if used on a None value, so check for that first, before cleaning the model name
    if body.model != None:
        body.model = body.model.strip()

    if body.model == None or body.model == "":
        status_code = 400
        resp = ErrorResponse(error = "model is required")
        return log_and_return(request, body, status_code, resp)
    
    # since the model has been stripped of leading and trailing spaces by this point,
    # if there are still spaces in the name (or if there simply aren't any alphanumeric characters),
    # then say the model is invalid
    elif " " in body.model or not any(c.isalnum() for c in body.model):
        status_code = 400
        resp = ErrorResponse(error = f"name \"{body.model}\" is invalid")
        return log_and_return(request, body, status_code, resp)

    # correct parameterless models so they default to ":latest" (same thing Ollama does)
    if ":" not in body.model:
        body.model += ":latest"

    # verify that the model requested for deletion is actually emulated in the first place:
    if body.model not in get_model_keys():
        status_code = 404
        resp = ErrorResponse(error = f"model '{body.model}' not found")
        return log_and_return(request, body, status_code, resp)

    # if code reaches this point, the model existed and should be removed, so just do that now:
    remove_model_from_session(body.model)

    # initialize non-error response
    # This endpoint also doesn't return a response body for success, just like /api/copy,
    # so setting 'resp' to 'None' lets "log_and_return" know to handle this accordingly
    resp = None

    # no delay required as this endpoint's response time is already as fast as FastAPI is

    return log_and_return(request, body, status_code, resp)







