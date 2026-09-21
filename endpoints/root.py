from fastapi import Request
from classes.request_classes import *
from classes.response_classes import *
from logging_resources import *



def ep_root(request: Request):
    status_code = 200

    # Ollama itself actually returns simply "Ollama is running", but I can't figure out how to return it without it being a string.
    # the difference between this honeypot response and the actual Ollama response is apparent when looking at the Base64-encoded response
    resp = RootResponse(
        message = "Ollama is running"
    )

    return log_and_return(request, None, status_code, resp)
