from fastapi import Request
from classes.request_classes import *
from classes.response_classes import *
from utils import *
from logging_resources import *



def ep_copy(request: Request, body: CopyRequest):
    resp = None
    status_code = 200
    

    # ? Ollama is strict regarding leading or trailing spaces, so don't try to remove them for this endpoint!


    # inputs of "None", empty strings, or strings with no alphanumeric characters all give error like "<source|destination> \"\" is invalid"
    # so simply set these variables to avoid having to do more checks for "None" values
    source = "" if body.source == None else body.source
    dest = "" if body.destination == None else body.destination

    if source in ["", " "] or not any(c.isalnum() for c in body.source):
        status_code = 400
        resp = ErrorResponse(error = f"source \"{source}\" is invalid")
        return log_and_return(request, body, status_code, resp)
    
    elif dest in ["", " "] or not any(c.isalnum() for c in body.destination):
        status_code = 400
        resp = ErrorResponse(error = f"destination \"{dest}\" is invalid")
        return log_and_return(request, body, status_code, resp)

    # add the "copied" model to the session-specific model list, and update the session store with this new list
    # TODO: check what Ollama does when trying to copy an existing model without specifying its parameter count!
    # TODO: (check this for when there're multiple parameter counts of the same model, too!)
    # TODO: Depending on Ollama's behavior, try to follow it as closely as possible
    if ":" not in body.destination:
        body.destination += ":latest" # Ollama defaults to ":latest" if no parameter count is given
    
    # if the given model is not being emulated, respond accordingly
    # Ollama directly checks the model, even if no parameter count is given
    if body.source not in get_model_keys():
        status_code = 404
        resp = ErrorResponse(error = f"model \"{body.source}\" not found")
        return log_and_return(request, body, status_code, resp)

    # try to get the source of the model being copied, or use the given source directly
    # (this ensures that copies of copies retain the same source, which is what Ollama does as well!)
    model_source = get_model_dict().get(body.source, {}).get("source_model", body.source)

    # try to add the model using the "from_model" as the source.
    # This will either add or simply update the model to/in the model dict,
    # and in case it just gets updated, the original creation time will be kept
    add_model_to_session(body.destination, modification_time=datetime.now().isoformat()+"Z", source_model=model_source)

    # initialize non-error response
    # response seems to be non-existent for success from what I can tell? No need for a response class of its own in this case
    resp = None

    # no delay required as this endpoint's response time is already as fast as FastAPI is

    return log_and_return(request, body, status_code, resp)








