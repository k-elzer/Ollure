from hashlib import sha256
from fastapi import Request
from classes.request_classes import *
from classes.response_classes import *
from utils import *
from logging_resources import *


def ep_models(request: Request):
    status_code = 200
    emulated_models = []

    for model, details_dicts in get_model_dict().items():
        model_params, params_suffix = get_model_param_parts(model)
        model_modification_time = details_dicts.get("modification_time", "2026-03-13T11:10:01.926506+01:00")
        model_source = details_dicts.get("source_model", model)
        model_size = get_appropriate_model_size(model_source)
        model_family = get_model_family_name(model_source)

        # for cloud models and non-tagged models; guess the parameter values since they can't be verified at present
        # (the guess for the cloud model comes from the deepseek-v4-pro:cloud model which is around 1.6t parameters, and this model was requested in a few of log entries)
        # (the guess for the ":latest" is pure guesswork though, under the assumption that clients would want a larger model, though they may also want a 100+b model :/ )
        # TODO: IF OLLAMA LIBRARY CHECKS ARE EVER ADDED; update this code to simply use the data from those checks
        if ":cloud" in model:
            model_params, params_suffix = "1.6", "t"
        elif ":latest" in model:
            model_params, params_suffix = "50", "b"

        model_details = ModelDetails(
            parent_model = "", # parent model just seems to always be an empty string for /api/tags responses...
            format = "" if "cloud" in model_source else "gguf", # forma
            family = model_family if "cloud" not in model_source else "",
            families = [model_family] if "cloud" not in model_source else [],
            parameter_size = model_params + params_suffix.upper(), # parameter size suffix is normally capitalized in Ollama's own responses, so doing that here too
            quantization_level = "Q4_K_M"
        )

        model_obj = Model(
            name = model,  # use the 'model' variable, specifically, for the full model including parameter count!
            model = model, # (*NOT* the source model!)
            remote_model = model_source if "cloud" in model else None,
            remote_host = "https://ollama.com:443" if "cloud" in model else None,
            modified_at = model_modification_time, # get and use the modification time or, if this doesn't exist for some reason, use some default time
            size = model_size,
            digest = sha256(model_source.encode('utf-8')).hexdigest(), # generate unique hash using the full *SOURCE* model name (sha256 used because that's what Ollama uses too)
            details = model_details
        )

        emulated_models.append(model_obj)

    resp = TagsResponse(
        models = emulated_models
    )

    # no delay required as this endpoint's response time is already as fast as FastAPI is

    return log_and_return(request, None, status_code, resp)








