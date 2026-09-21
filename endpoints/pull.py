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
# before the final response with all the metadata fields being sent at the end of the method
def _build_pull_stream(model: str, model_found : bool, param_count: float, final_response):

    # this is always the first chunk to be streamed when pulling a model for creation
    yield ModelModificationResponse(
        status = f"pulling manifest"
    ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"

    if not model_found:
        sleep(randrange(472, 522) / 1000) # sleep for short amount of time to simulate checking if the model exists or not; sleep times based on 5 random tests
    
    # the "pulling manifest"-yield should always run,
    # but only emulate successful pulling if model exists somewhere:
    else:
        # set the default number of status update chunks to stream, corresponding to pulling an existing model
        # (with "status update chunks" referring to the "pulling <digest>" and "using existing layer <digest>" chunks).
        # ? the pulling times are just random observations of how long the pulling processes seems to take for Ollama when pulling existing models,
        # ? and these times just get equally divided among the streamed status update chunks
        num_of_status_update_pull_chunks = 5
        pull_waiting_time = randrange(579, 1180, 1) / 1000 / num_of_status_update_pull_chunks

        # set random, large, initial value for "total" field
        # ("completed" usually starts around this value, and increases until it reaches the value of "total", after which it stops increasing)
        total_field = randrange(1036034688, 3389971840, 1)
        completion_low_inc = 491520
        completion_high_inc = 791424

        # values gotten from pulling deepseek-v4-pro:cloud, and gemma3:1b 5 times and llama3.1:8b 2 times (long wait, so accuracy isn't as relevant), deleting it in between each test
        # random waiting time in milliseconds, and split evenly among chunks to pull
        if param_count is None and model not in get_model_keys():
            # for ":cloud" models:
            num_of_status_update_pull_chunks = 19
            pull_waiting_time = randrange(1930, 2070, 1) / 1000 / num_of_status_update_pull_chunks
            total_field = 344       # when pulling "deepseek-v4-pro:cloud", these values are used for all "total", and "completed" fields,
            completed_field = 344   # so keep using these values for this type of model

        # in case model is already being emulated:
        elif model not in get_model_keys():
            # for non-":cloud" models, i.e. models with a parameter size given like gemma3:1b and llama3.1:8b:
            # ? formulae derived from quick tests of relationship between number of gemma3:1b download packets and llama3.1:8b download packets,
            # ? and relationship between parameter count and corresponding total pulling time
            num_of_status_update_pull_chunks = int(param_count * 980 + 315) 
            pull_waiting_time = (param_count * 61290 + 22160) / 1000 / num_of_status_update_pull_chunks

        # set starting value of the "completed" field to a value that will at least be reached in the first two thirds of chunks,
        # so that the if-elif structure inside the streaming loop will always be fully executed
        # (but only set the "completed" field this way if it's a model with a given parameter count!)
        completed_field = total_field - int(num_of_status_update_pull_chunks * 2/3 * completion_low_inc) if param_count is not None else 344

        # streaming loop:
        for i in range(num_of_status_update_pull_chunks):
            # only alter "total" and "completed" fields for models with given parameter counts:
            # ("total" and "completed" values are essentially just updated at specific points in the pulling process, in a manner mimicking Ollama's responses)
            if param_count is not None:
                # (value increase for "completed" field is also based on observed, typical increase values for this field in Ollama's responses)
                if completed_field < total_field:
                    completed_field = min(total_field, completed_field + randrange(completion_low_inc, completion_high_inc, 1))

                # 'elif'-structure checks progressively larger parts of the tailing chunks of the pulling process,
                # and determines specific value ranges for these parts.
                # This effectively splits the chunks into 4 sections, with the vast majority using the value from the original random value range,
                # before swapping to a relatively smaller value range,
                # and finally swapping to two significantly smaller value ranges for the last [57..20] and [19..1] chunks
                elif i >= num_of_status_update_pull_chunks - 19: # very last part of the tailing chunks
                    total_field = randrange(487, 1481, 1) # ? higher randrange for the very last chunks is intentional!
                    completed_field = total_field
                elif i >= num_of_status_update_pull_chunks - 57: # second to last part of the tailing chunks
                    total_field = randrange(96, 429, 1)
                    completed_field = total_field
                elif i >= num_of_status_update_pull_chunks * 2 // 3:
                    total_field = randrange(11355, 12320, 1)
                    completed_field = total_field
                else:
                    completed_field = total_field

            # hash the model name and "total" field together, since Ollama's digests seem to depend on the "total" as well, and should change between models
            chunk_digest = sha256(f"{model}:{total_field}".encode('utf-8')).hexdigest()

            sleep(pull_waiting_time) # simulate the waiting time for each status update chunk
            
            # yield each response token as a separate, small chunk first:
            yield ModelModificationResponse(
                status = f"pulling {chunk_digest[:12]}", # this status message uses the first 12 characters of the digest
                digest = f"sha256:{chunk_digest}",
                total = total_field,
                completed = completed_field,
            ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"
        
        # finally, stream some chunks indicating that it was sucessfully "pulled"
        yield ModelModificationResponse(
            status = f"verifying sha256 digest"
        ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"
        yield ModelModificationResponse(
            status = f"writing manifest"
        ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"

        # try to add the model.
        # This will either add or simply update the model to/in the model dict,
        # and in case it just gets updated, the original creation time will be kept
        add_model_to_session(model, modification_time=datetime.now().isoformat()+"Z")

    # finally, yield the final chunk of the response text
    yield final_response.model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"


def ep_pull(request: Request, body : PullRequest):
    resp = None
    status_code = 200

    # Ollama accepts model names with leading and/or trailing spaces,
    # and simply tries to pull the model after stripping away those spaces,
    # so .strip() the model name before performing any other checks.
    # ".strip()" also fails if used on a None value, so the code checks for that first, before cleaning the model name
    if body.model != None:
        body.model = body.model.strip()

    if body.model == None or body.model == "" or not any(c.isalnum() for c in body.model): # if given model is either None, is an empty string (after stripping), or contains no alphanumeric characters
        status_code = 400
        resp = ErrorResponse(error = "invalid model name")
        return log_and_return(request, body, status_code, resp)

    # TODO: ADD AN ERROR CHECK FOR LARGE MODELS BEING ATTEMPTED PULLED,
    # TODO: AND GIVE AN APPROPRIATE MODEL SIZE FOR BOTH THE GIVEN MODEL (use the model size estimation helper method)
    # TODO: AND HOW MUCH STORAGE SPACE THE HONEYPOT SHOULD SAY IT HAS LEFT (could maybe base this on the sizes of models already downloaded?)

    # correct parameterless models so they default to ":latest" (same thing Ollama does)
    if ":" not in body.model:
        body.model += ":latest"

    # iniitalize non-error response
    # TODO: WHEN ADDING OLLAMA LIBRARY CHECK, USE THE COMMENTED-OUT IF-STATEMENT BELOW (marked with ">>>" and "<<<")!!
    # TODO: EXPAND THIS TO RUN A CURL OR REQUEST TO ollama.com/libraries/<body.model>
    # TODO: AND IF I DON'T GET AN ERROR 404 THEN ACT AS THOUGH I PULL THE MODEL!
    # >>>
    # model_was_found = False
    # if body.model not in get_model_keys(): #? and body.model not in OLLAMA_LIBRARY:
    #     resp = ErrorResponse(
    #         error = "pull model manifest: file does not exist"
    #     )
    # else:
    # <<<
    model_was_found = True
    resp = ModelModificationResponse(
        status = "success"
    )

    # parameter count determines amount of chunks to stream (only for streaming responses)
    # (also checks for ":latest", and for no parameter count given)
    source_param_count = None # default value for models without parameter counts given
    if ":" in body.model and not any(word in body.model for word in (":latest", ":cloud")):
        source_param_count, _ = get_model_param_parts(body.model)
        source_param_count = float(source_param_count)

    # check if response should be streamed, and if so, call the streaming method and set headers accordingly
    if body.stream is not None and body.stream == True:
        streamed_resp = resp.model_copy()
        streaming_response = StreamingResponse(
            _build_pull_stream(body.model, model_was_found, source_param_count, streamed_resp),
            media_type="application/x-ndjson",
            headers=get_custom_headers("application/x-ndjson"), # "charset=utf-8" is not included for streaming responses by Ollama, so don't include it here either
        )

        return log_and_return(request, body, status_code, resp, streamed = True, final_stream_chunk = streaming_response)

    # sleep for an appropriate amount of time,
    # based on whether the models exists, or should be pulled (and if so, if the model had a parameter count included or not).
    # Waiting time for parameterless models is short, due to ":cloud" models being easy to pull,
    # although that unfortunately also means fast pulling times for ":lastest" and parameterless models
    # TODO: UPDATE WAITING TIME FOR ":latest" AND PARAMETERLESS MODELS ONCE OLLAMA LIBRARY CHECK IS IMPLEMENTED!
    if body.model not in get_model_keys():
        # default sleep time is the pulling time of parameterless models (i.e., ":latest", ":cloud", and models without parameter counts given)
        sleep_time = randrange(1930, 2070, 1) / 1000
        if source_param_count is not None:
            sleep_time = (source_param_count * 61290 + 22160) / 1000 # sleep time updated if model had a parameter count included in the model name
        sleep(sleep_time)

    else:
        sleep(randrange(579, 1180, 1) / 1000)

    # try to add the model.
    # This will either add or simply update the model to/in the model dict,
    # and in case it just gets updated, the original creation time will be kept
    add_model_to_session(body.model, modification_time=datetime.now().isoformat()+"Z")

    return log_and_return(request, body, status_code, resp, streamed = False)








