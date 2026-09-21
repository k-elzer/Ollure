from time import sleep
from fastapi import Request
from fastapi.responses import StreamingResponse
from hashlib import sha256
from random import randrange
from classes.request_classes import *
from classes.response_classes import *
from utils import *
from logging_resources import *


# helper method for streaming the response,
# with the response being sent in small chunks,
# before the final response with all the fields being sent at the end of the method
def _build_push_stream(model: str, final_response):
    # set the number of status update chunks to stream
    # (with "status update chunks" being the "pulling <digest>" and "using existing layer <digest>" chunks)
    # the pushing times are just random observations of how long the pushing processes seems to take for Ollama when pushing models (model sizes didn't seem to have much of an effect?),
    # and these times just get equally divided among the streamed status update chunks
    # TODO: could also either make this waiting time depend on the random numbers used for the "total" and "completed" fields?
    num_of_status_update_push_chunks = 5
    push_waiting_time = randrange(1810, 2250, 1) / 1000 / num_of_status_update_push_chunks

    # this is always the first chunk to be streamed when pushing a model for creation
    yield ModelModificationResponse(
        status = f"retrieving manifest"
    ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"

    # if model wasn't found, yield a specific chunk instead of emulating the model push:
    if not model in get_model_keys():
        # no added delay for when the model push fails, so this if-statement block doesn't call sleep() at all.
        yield ModelModificationResponse(
            status = f"couldn't retrieve manifest"
        ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"
    else:
        # ? THIS ENDPOINT DOESN'T CARE ABOUT HANDLING POTENTIAL ":cloud" MODELS BEING PUSHED,
        # ? SINCE THAT'S SIMPLY TOO UNLIKELY TO HAPPEN,
        # ? SO JUST SKIP SUCH CHECKS

        for i in range(num_of_status_update_push_chunks):
            # the values of the "total" and "completed" fields follow about the same structure as for /api/create and /api/pull,
            # however, /api/push seems to just have very few chunks, so might as well set randranges for each relevant chunk.
            # ! If the number of chunks sent by this endpoint for whatever reason changes drastically in the future,
            # ! then consider updating this streaming behaviour to be more like the one used for /api/create and /api/pull !!!
            match num_of_status_update_push_chunks - i:
                case 1:
                    total_field = randrange(487, 1481, 1) # ? higher randrange for the very last chunk is intentional!
                case 2:
                    total_field = randrange(96, 429, 1)
                case 3:
                    total_field = randrange(11355, 12320, 1)
                case 4:
                    total_field = randrange(487, 1481, 1)
                case _:
                    total_field = randrange(1036034688, 3389971840, 1)
            # the "completed" field never really gets a chance to be different from the "total" field,
            # due to the very low number of chunks.
            # ! If the number of chunks sent by this endpoint for whatever reason changes drastically in the future,
            # ! then consider updating the value of "completed_field" to be more like the one used for /api/create and /api/pull !!!
            completed_field = total_field

            # hash the model name and "total" field together, since Ollama's digests seem to depend on the "total" as well, and should change between models
            chunk_digest = sha256(f"{model}:{total_field}".encode('utf-8')).hexdigest()

            sleep(push_waiting_time) # simulate the waiting time for each status update chunk
            
            # yield each response token as a separate, small chunk first:
            yield ModelModificationResponse(
                status = f"pushing {chunk_digest[:12]}", # this status message uses the first 12 characters of the digest
                digest = f"sha256:{chunk_digest}",
                total = total_field,
                completed = completed_field,
            ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"
        
        # after "pushing" the model, stream some chunks indicating that it was sucessfully "pushed"
        yield ModelModificationResponse(
            status = f"pushing manifest"
        ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"

    # finally, yield the final chunk of the response text
    yield final_response.model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"


def ep_push(request: Request, body : PushRequest):
    resp = None
    status_code = 200


    # ? Ollama is strict regarding leading or trailing spaces, so don't try to remove them for this endpoint!


    if body.model == None or body.model == "":
        status_code = 400
        resp = ErrorResponse(error = "model is required")
        return log_and_return(request, body, status_code, resp)

    # Ollama doesn't allow pushing models with spaces in them whatsoever, nor models without alphanumeric characters,
    # and it returns the same error for both of these cases
    elif " " in body.model or not any(c.isalnum() for c in body.model):
        status_code = 500
        resp = ErrorResponse(error = f"unqualified name: registry.ollama.ai/library/{body.model}")
        return log_and_return(request, body, status_code, resp)

    elif body.insecure == False:
        # the response itself says "403", but the actual HTTP status code says 500 - best to use the actual HTTP status code
        status_code = 500
        resp = ErrorResponse(error = "403: {\"errors\":[{\"code\":\"ANONYMOUS_ACCESS_DENIED\",\"message\":\"anonymous access denied\"}]}")
        return log_and_return(request, body, status_code, resp)
    
    # correct parameterless models so they default to ":latest" (same thing Ollama does)
    if ":" not in body.model:
        body.model += ":latest"
    
    # verify that the model being pushed actually exists in the first place:
    if body.model not in get_model_keys():
        status_code = 500
        resp = ErrorResponse(error = f"open /root/.ollama/models/manifests/registry.ollama.ai/library/{body.model.replace(':', '/')}: no such file or directory")
        return log_and_return(request, body, status_code, resp)

    # iniitalize non-error response
    resp = ModelModificationResponse(
        status = "success"
    )

    # check if response should be streamed, and if so, call the streaming method and set headers accordingly
    if body.stream is not None and body.stream == True:
        streamed_resp = resp.model_copy()
        streaming_response = StreamingResponse(
            _build_push_stream(body.model, streamed_resp),
            media_type="application/x-ndjson",
            headers=get_custom_headers("application/x-ndjson"), # "charset=utf-8" is not included for streaming responses by Ollama, so don't include it here either
        )

        return log_and_return(request, body, status_code, resp, streamed = True, final_stream_chunk = streaming_response)

    sleep(randrange(1810, 2250, 1) / 1000) # just based on a few quick tests - might not be very accurate for all models, but should be sufficient for this honeypot

    return log_and_return(request, body, status_code, resp, streamed = True)







