from fastapi import Request
from classes.request_classes import *
from classes.response_classes import *
from utils import *
from logging_resources import *


def ep_v1_models(request: Request):
    status_code = 200
    emulated_models = []
    
    for model in get_model_keys():
        # TODO: Update this to use the actual model details
        # TODO: (values returned by Ollama may not perfectly match those used for /api/tags, so some testing may be needed!)
        model_entry = V1Model(
            id = model,
            object = "model",
            created = 1775415684 + len(model) * 1111,
            owned_by = "library"
        )

        emulated_models.append(model_entry)


    resp = V1ModelsResponse(
        object = "list",
        data = emulated_models
    )

    # no delay required as this endpoint's response time is already as fast as FastAPI is

    return log_and_return(request, None, status_code, resp)








