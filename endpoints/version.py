from fastapi import Request
from classes.request_classes import *
from classes.response_classes import *
from logging_resources import *



def ep_version(request: Request):
    status_code = 200

    # hard-coded version since this should be sufficient for this honeypot
    # (may also invite more attacks, but using a newer version may bring in more significant attacks?)
    # TODO: potentially update this at some point?
    resp = VersionResponse(
        version = "0.18.0"
    )

    # no delay required as this endpoint's response time is already as fast as FastAPI is

    return log_and_return(request, None, status_code, resp)
