from time import sleep
from fastapi import Request
from classes.request_classes import *
from classes.response_classes import *
from utils import *
from logging_resources import *


def ep_embed(request: Request, body: EmbedRequest):
    resp = None
    status_code = 200

    if body.model == None or body.model == "":
        status_code = 500
        resp = ErrorResponse(error = "model '' not found")
        return log_and_return(request, body, status_code, resp)

    # Ollama accepts model names with leading and/or trailing spaces,
    # but doesn't remove those spaces from the model it shows in the response,
    # so .strip() as part of the if-statement.
    # ".strip()" and "in" fail if used on a None value, but the above if-statement handles that case by this point
    elif not any(c.isalnum() for c in body.model) or " " in body.model.strip(): # if given model contains no alphanumeric characters or contains spaces other than leading/trailing spaces:
        status_code = 400
        resp = ErrorResponse(error = "invalid model name")
        return log_and_return(request, body, status_code, resp)

    # if neither of the above resulted in an error, then model doesn't contain any spaces (aside from possibly leading/trailing spaces),
    # so stripped model name should now contain no spaces
    elif body.model.strip() not in get_model_keys():
        status_code = 404
        resp = ErrorResponse(error = f"model \"{body.model}\" not found, try pulling it first")
        return log_and_return(request, body, status_code, resp)
    
    elif body.input == None or body.input == "" or body.input == []: # if input is None, an empty string, or an empty list, Ollama just returns an empty, non-error response
        status_code = 200
        resp = EmbedResponse(
            model = body.model,
            embeddings = []
        )
        return log_and_return(request, body, status_code, resp)

    # if prompted/requested model wasn't the running model, update the running mode to be this model after a little waiting time (to emulate switching the running model to another):
    if body.model.strip() != get_running_model():
        sleep(53) # TODO: VALIDATE THIS DELAY A LITTLE MORE AND ADD RANDOMIZATION; only tried changing models like 2 or 3 times, between llama3.1:8b and gemma3:4b
        set_running_model(body.model.strip())

    # ? E.g., the "gemma3:4b" model doesn't support embeddings (seemingly because it's also vision-capable),
    # ? but blocking embedding emulation for any models probably won't be necessary/worthwhile, so this check will just be left out (at least for now)
    # TODO: Might update this to check for and catch specific models that don't support embeddings (or might curl Ollama and somehow check that way?)
    # else:
    #     status_code = 501
    #     resp = ErrorResponse(error = "this model does not support embeddings")
    #     return log_and_return(request, body, status_code, resp)

    total_input_length = len(body.input) if type(body.input) == str else sum(len(i) for i in body.input)

    # # initialize non-error response
    # TODO: tweak this for streaming vs. non-streaming responses
    resp = EmbedResponse(
        model = body.model,
        embeddings = [[
            -0.012059132,0.012904897,-0.01688204,-0.008666071,0.006037851,
            -0.0138402665,-0.019853828,0.005354084,0.0034439492,0.0029634659,
            0.0011931245,0.0030507217,0.0062839617,-0.015376126,-5.2192263e-7,
            0.022931108,-0.0027951926,0.00020934266,0.00050168374,-0.0135437865,
            0.012702862,-0.01377733,-0.0018401992,-0.0016710185,-0.008723453
        ]],                                        # *
        total_duration = 98502800,                 # TODO: test this out with Ollama a few more times to get a feel for which values to use or ranges to generate random values from
        load_duration = 64618600,                  # *
        prompt_eval_count = total_input_length,    # *
    )

    # TODO: ADD RANDOMIZATION TO THE SLEEP TIMES FOR THIS ENDPOINT!
    sleep(0.091) # this endpoint is significantly faster than the other endpoints, so delay doesn't need to be that long

    return log_and_return(request, body, status_code, resp)








