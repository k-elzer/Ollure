from datetime import datetime, timedelta
from hashlib import sha256
from fastapi import Request
from classes.request_classes import *
from classes.response_classes import *
from utils import *
from logging_resources import *



def ep_running_models(request: Request):
    status_code = 200

    running_model = get_running_model()
    running_model_details = get_model_dict().get(get_running_model(), {}) # the default value for the ".get()" call is mainly for safety, though it should be redundant
    model_params, params_suffix = get_model_param_parts(running_model)
    model_source = running_model_details.get("source_model", running_model)
    model_size = get_appropriate_model_size(model_source)
    model_family = get_model_family_name(model_source)

    model_details = ModelDetails(
        parent_model = "", # TODO: UPDATE THIS SINCE OLLAMA MODELS CAN HAVE PARENT MODELS FROM THE START WITHOUT HAVING TO BE COPIED FIRST!
        format = "gguf",
        family = model_family,
        families = [model_family],
        parameter_size = model_params + params_suffix.upper(),
        quantization_level = "Q4_K_M"
    )

    model = Model(
        name = model_source,
        model = model_source,
        size = model_size,
        digest = sha256(model_source.encode('utf-8')).hexdigest(), # generate unique hash using the full model name (sha256 used because that's what Ollama uses too)
        details = model_details,
        expires_at = (datetime.now() + timedelta(minutes=4, seconds=20)).isoformat()+"Z", # faking an expiration time by slightly increasing the current time
        size_vram = 0,
        context_length = 4096 # Not sure if this ever changes, but it doesn't seeme to at least? # TODO: VERIFY THIS SOMEHOW
    )

    resp = TagsResponse(
        models = [model] # TODO: EXPAND THIS LIST IF SUPPORT FOR MULTIPLE, CONCURRENTLY RUNNING MODELS IS EVER ADDED!
    )

    # no delay required as this endpoint's response time is already as fast as FastAPI is

    return log_and_return(request, None, status_code, resp)








