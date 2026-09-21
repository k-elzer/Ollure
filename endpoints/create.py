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
def _build_create_stream(model: str, from_model: str, model_found : bool, param_count: float, final_response):

    # the "pulling manifest" chunk should always be yielded, but cut the stream short and return the final response immediately if model isn't found
    # (the final response will in this case be the error "pull model manifest: file does not exist", as set in the handler function before calling this streaming method)
    if not model_found:
        yield ModelModificationResponse(
            status = f"pulling manifest"    
        ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"

        sleep(randrange(472, 522) / 1000) # sleep for short amount of time to simulate checking if the model exists or not; sleep times based on 5 random tests

        yield final_response.model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"
        return

    # check the model dict for the model to create a new one from, and if it exists, consider this model cached (i.e., no need to pull it first)
    # (not a huge issue if it isn't the full model name, as then both "llama3.1:0.5b" and "llama3.1:70b" will both be seen as "llama3.1",
    # and creating from a non-existent "llama3.1:70b" would go through as though this model was actually already pulled, even if it wasn't)
    model_cached = False
    for details_dict in get_model_dict().values():
        if details_dict.get("full_model_name") == from_model:
            model_cached = True
            break

    # "model_found == False" has already been handled, so now check if model pulling should be emulated or not:
    if not model_cached:
        # set the default number of status update chunks to stream, corresponding to pulling a cloud model that hasn't already been pulled,
        # (with "status update chunks" referring to the "pulling <digest>" and "using existing layer <digest>" chunks).
        # ? The pulling and creation times are just random observations of how long the pulling processes seems to take for Ollama when pulling and/or creating existing models,
        # ? and these times just get equally divided among the streamed status update chunks
        # values gotten from pulling deepseek-v4-pro:cloud, and gemma3:1b 5 times and llama3.1:8b 2 times (long wait, so accuracy isn't as relevant), deleting it in between each test
        # random waiting time in milliseconds, and split evenly among chunks to pull
        # TODO: maybe shorten this delay considerably (or remove it entirely) since the response time seems super fast when creating the model,
        # TODO: even if /api/pull takes a while for the same model!
        # TODO: the only chunks streamed for this endpoint are also just "writing manifest" and "success", nothing else...
        # TODO: (not sure why this is, makes no sense to me...)
        num_of_status_update_pull_chunks = 19
        pull_waiting_time = randrange(1930, 2070, 1) / 1000 / num_of_status_update_pull_chunks
        total_field = 344       # when pulling "deepseek-v4-pro:cloud", these values are used for all "total", and "completed" fields,
        completed_field = 344   # so keep using these values for this type of model

        # the value of the "completed" field increases while streaming;
        # set bounds for the increment between each chunk
        completion_low_inc = 491520
        completion_high_inc = 791424

        # if model to pull isn't a cloud model, pulling time will be significantly longer, with a lot more chunks:
        if param_count is not None:
            # if parameter count wasn't none (indicating a non-cloud model), update the number of chunks to stream and the delay between each chunk
            # ? formulae derived from quick tests of relationship between number of gemma3:1b download packets and llama3.1:8b download packets,
            # ? and relationship between parameter count and corresponding total pulling time
            num_of_status_update_pull_chunks = int(param_count * 980 + 315)
            pull_waiting_time = (param_count * 61290 + 22160) / 1000 / num_of_status_update_pull_chunks

            # set random, large, initial value for "total" field
            # ("completed" usually starts around this value, and increases until it reaches the value of "total", after which it stops increasing)
            total_field = randrange(1036034688, 3389971840, 1)
            # set starting value of the "completed" field to a value that will at least be reached in the first two thirds of chunks,
            # so that the if-elif structure inside the streaming loop will always be fully executed
            # (this isn't needed for cloud models since all their chunks have the same "total" and "completed" values)
            completed_field = total_field - int(num_of_status_update_pull_chunks * 2/3 * completion_low_inc)

        # only emulate pulling the model if it doesn't already exist:
        # the "pulling manifest" chunk is always the first chunk to be streamed when pulling a model for creation
        yield ModelModificationResponse(
            status = f"pulling manifest"
        ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"

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

        # after "pulling" the model, stream some chunks indicating that it was sucessfully "pulled"
        yield ModelModificationResponse(
            status = f"verifying sha256 digest"
        ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"
        yield ModelModificationResponse(
            status = f"writing manifest"
        ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"
        yield ModelModificationResponse(
            status = f"success"
        ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"

    # try to get the source of the model being created, or use the given source directly
    # (this ensures that copies of copies retain the same source, which is what Ollama does as well!)
    model_source = get_model_dict().get(from_model, {}).get("source_model", from_model)

    # try to add the model using the "from_model" as the source.
    # This will either add or simply update the model to/in the model dict,
    # and in case it just gets updated, the original creation time will be kept
    add_model_to_session(model, modification_time=datetime.now().isoformat()+"Z", source_model=model_source)

    # usually only 4-5 chunks streamed as part of the creation process, even when pulling produced a lot of chunks
    num_of_status_update_create_chunks = 5
    creation_waiting_time = randrange(57, 134, 1) / 1000 / num_of_status_update_create_chunks

    # now that the model exists (either from emulating the model pulling, or from the model already existing in the model list),
    # stream some chunks to mimic the model "creation":
    for i in range(num_of_status_update_create_chunks):
        chunk_digest = sha256(f"{model}:{i}".encode('utf-8')).hexdigest() # hash the model name and chunk number together to make each chunk digest unique

        sleep(creation_waiting_time) # simulate the waiting time for each status update chunk

        # yield each response token as a separate, small chunk first:
        yield ModelModificationResponse(
            status = f"using existing layer sha256:{chunk_digest}",
        ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"

    # finally, stream some chunks indicating that it was sucessfully "created"
    yield ModelModificationResponse(
        status = f"writing manifest"
    ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"

    # finally, yield the final chunk of the response text
    yield final_response.model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"


def ep_create(request: Request, body: CreateRequest):
    resp = None
    status_code = 200

    # Ollama accepts model names with leading and/or trailing spaces
    # and this endpoint doesn't include the model name in the returned response,
    # so .strip() the model name before performing any other checks.
    # ".strip()" also fails if used on a None value, so the code checks for that first, before cleaning the model name
    if body.model != None:
        body.model = body.model.strip()

    if body.model == None or body.model == "":
        status_code = 400
        resp = ErrorResponse(error = "invalid model name")
        return log_and_return(request, body, status_code, resp)

    # TODO: maybe add more error-handling to check if "files" is given?
    elif body.make_from in [None, ""] and body.files in [None, "", []]: # if "from" is given but empty, and "files" is either not given or empty
        status_code = 400
        resp = ErrorResponse(error = "neither 'from' nor 'files' was specified")
        return log_and_return(request, body, status_code, resp)
    
    # Ollama returns "invalid model name" for quite a few different model names,
    # including names with spaces in the middle, or names without any alphanumeric characters,
    # (although it also returns this for models like ".:b", and I don't want to be too pedantic with model name checks, so I'll ignore such cases)
    elif body.model not in [None, ""] and (not any(c.isalnum() for c in body.model) or " " in body.model):
        status_code = 400
        resp = ErrorResponse(error = "invalid model name")
        return log_and_return(request, body, status_code, resp)

    # same deal as the above elif-statement, but for body.from
    elif body.make_from not in [None, ""] and (not any(c.isalnum() for c in body.make_from) or " " in body.make_from):
        status_code = 400
        resp = ErrorResponse(error = "invalid model name")
        return log_and_return(request, body, status_code, resp)

    # TODO: ADD AN ERROR CHECK FOR LARGE MODELS BEING ATTEMPTED PULLED,
    # TODO: AND GIVE AN APPROPRIATE MODEL SIZE FOR BOTH THE GIVEN MODEL (use the model size estimation helper method)
    # TODO: AND HOW MUCH STORAGE SPACE THE HONEYPOT SHOULD SAY IT HAS LEFT (could maybe base this on the sizes of models already downloaded?)

    # correct parameterless models so they default to ":latest" (same thing Ollama does)
    if ":" not in body.model:
        body.model += ":latest"
    
    # correct parameterless source models so they default to ":latest" (same thing Ollama does)
    # (Ollama tries to pull this model if it isn't already in the list)
    if ":" not in body.make_from:
        body.make_from += ":latest"

    # iniitalize non-error response
    # TODO: WHEN ADDING OLLAMA LIBRARY CHECK, USE THE COMMENTED-OUT IF-STATEMENT BELOW (marked with ">>>" and "<<<")!!
    # TODO: EXPAND THIS TO RUN A CURL OR REQUEST TO ollama.com/libraries/<body.model>
    # TODO: AND IF I DON'T GET AN ERROR 404 THEN ACT AS THOUGH I PULL THE MODEL!
    # >>>
    # model_was_found = False
    # if body.make_from not in get_model_keys(): #? and body.model not in OLLAMA_LIBRARY:
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
    if "cloud" not in body.make_from:
        source_param_count, _ = get_model_param_parts(body.make_from)
        source_param_count = float(source_param_count)

    # check if response should be streamed, and if so, call the streaming method and set headers accordingly
    if body.stream is not None and body.stream == True:
        streamed_resp = resp.model_copy()
        streaming_response = StreamingResponse(
            _build_create_stream(body.model, body.make_from, model_was_found, source_param_count, streamed_resp),
            media_type="application/x-ndjson",
            headers=get_custom_headers("application/x-ndjson"), # "charset=utf-8" is not included for streaming responses by Ollama, so don't include it here either
        )

        return log_and_return(request, body, status_code, resp, streamed = True, final_stream_chunk = streaming_response)

    # sleep for an appropriate amount of time,
    # based on whether the models exists, or should be pulled (and if so, if the model had a parameter count included or not).
    # Waiting time for parameterless models is short, due to ":cloud" models being easy to pull,
    # although that unfortunately also means fast pulling times for ":lastest" and parameterless models
    # TODO: UPDATE WAITING TIME FOR ":latest" AND PARAMETERLESS MODELS ONCE OLLAMA LIBRARY CHECK IS IMPLEMENTED!
    if not model_was_found:
        # default sleep time is the pulling time of parameterless models (i.e., ":latest", ":cloud", and models without parameter counts given)
        # TODO: maybe shorten this delay considerably (or remove it entirely) since the response time seems super fast when creating the model,
        # TODO: even if /api/pull takes a while for the same model!
        # TODO: the only chunks streamed for this endpoint are also just "writing manifest" and "success", nothing else...
        sleep_time = randrange(1930, 2070, 1) / 1000
        if source_param_count is not None:
            sleep_time = (source_param_count * 61290 + 22160) / 1000 # sleep time updated if model had a parameter count included in the model name
        sleep(sleep_time)

    else:
        sleep(randrange(579, 1180, 1) / 1000)

    # try to get the source of the model being created, or use the given source directly
    # (this ensures that copies of copies retain the same source, which is what Ollama does as well!)
    model_source = get_model_dict().get(body.make_from, {}).get("source_model", body.make_from)

    # try to add the model, using the "from_model" as the source.
    # This will either add or simply update the model to/in the model dict,
    # and in case it just gets updated, the original creation time will be kept
    add_model_to_session(body.model, modification_time=datetime.now().isoformat()+"Z", source_model=model_source)

    return log_and_return(request, body, status_code, resp, streamed = False)








