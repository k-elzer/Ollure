from datetime import datetime
from time import sleep
from random import randrange
from fastapi import Request
from fastapi.responses import StreamingResponse
from classes.request_classes import *
from classes.response_classes import *
from response_cache.generate_cache import lookup
from utils import *
from logging_resources import *


# helper method for streaming the response,
# with the response being sent in small chunks,
# before the final response with all the fields being sent at the end
def _build_generate_stream(model: str, response_chunks: list[str], total_waiting_time: float, final_response: GenerateResponse):
    # set the waiting time for streaming the chunks, with the waiting time split up equally among the chunks
    chunk_waiting_time = total_waiting_time / len(response_chunks)

    for chunk_text in response_chunks:
        # yield each response token as a separate, small chunk first:
        yield GenerateResponse(
            model = model,
            created_at = datetime.now().isoformat()+"Z",
            response = chunk_text,
            done = False,
        ).model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"

        # sleep a bit between each chunk
        sleep(chunk_waiting_time)

    # now, set creation time of the final response chunk after all the other chunks have been yielded/sent
    setattr(final_response, 'created_at', datetime.now().isoformat()+"Z")

    # finally, yield the final chunk of the response text
    yield final_response.model_dump_json(exclude_defaults = True, exclude_none = True) + "\n"


# main handler method for /api/generate
def ep_generate(request: Request, body: GenerateRequest):
    resp = None
    status_code = 200

    # Ollama accepts model names with leading and/or trailing spaces,
    # but doesn't remove those spaces from the model it shows in the response,
    # so .strip() as part of the if-statement.
    # ".strip()" also fails if used on a None value, so check for that first, before cleaning the model name
    if body.model == None:
        status_code = 404
        resp = ErrorResponse(error = f"model '' not found")
        return log_and_return(request, body, status_code, resp)
    
    # if model still contains spaces after removing leading and trailing spaces, Ollama gives a slightly different error message!
    # (".strip()" and "in" fail if used on a None value, but the above if-statement handles that case by this point)
    elif " " in body.model.strip():
        status_code = 400
        resp = ErrorResponse(error = "invalid model name")
        return log_and_return(request, body, status_code, resp)

    # check if model is in the model list now that the above "invalid model name" case has been handled:
    elif body.model.strip() not in get_model_keys():
        status_code = 404
        resp = ErrorResponse(error = f"model '{body.model}' not found")
        return log_and_return(request, body, status_code, resp)

    # small, initial delay since Ollama has to interpret the prompt and figure out what to do,
    # before it starts responding (with a streamed or non-streamed response).
    # Random value range was determined via streamed responses in Postman,
    # since it (for streamed responses only) can show how long it was waiting before it started receiving response chunks
    init_sleep_time = randrange(281, 357, 1) / 1000
    sleep(init_sleep_time)

    # declare variable for additional waiting time due to simulating changing/swapping the running model
    model_swap_waiting_time = 0

    # if *SOURCE* model of the prompted/requested model wasn't the running model;
    # update the running mode to be this *SOURCE* model after a little waiting time (to emulate switching the running model to another):
    model_source = get_model_dict().get(body.model.strip(), {}).get("source_model", body.model.strip())
    if model_source != get_running_model():
        model_swap_waiting_time = randrange(52531, 54815, 1) / 1000
        sleep(model_swap_waiting_time)
        set_running_model(model_source)

    # iniitalize non-error response
    resp = GenerateResponse(
        model = body.model,
        created_at = "", # this is always overwritten later, just before the response is returned to the client (to mimic Ollama's response time being just before the response is sent)
        response = "",
        done = False
    )

    resp_string = lookup(model_source, body.prompt) # perform dynamic answering 

    # if prompt is missing or empty, only need these 3 fields for the response; nothing else!
    if resp_string == None or resp_string == "":
        setattr(resp, 'done', True)
        setattr(resp, 'done_reason', "load")

    # if prompt is present, fill out the rest of the response accordingly
    # (responses are also only attempted streamed if there's a prompt *to* stream)
    # TODO: FIX THE REMAINING HARDCODED VALUES
    else:
        # additional waiting time since there's a prompt to "evaluate".
        # The random value range used here is based on observations from testing the response time of this endpoint,
        # specifically response time for the prompt "hi"
        eval_delay = randrange(2129, 2873, 1) / 1000

        setattr(resp, 'response', resp_string)
        setattr(resp, 'done', True)
        setattr(resp, 'done_reason', "stop")
        setattr(resp, 'context', [
            128006,882,128007,271,6151,128009,
            128006,78191,128007,271,9906,0,2650,527,
            499,3432,30,2209,1070,2555,358,649,1520,
            499,449,477,1053,499,1093,311,6369,30
        ])

        # tokenize the response, as it's needed for both streamed and non-streamed responses
        tokenized_response_text = list(tokenize(getattr(resp, 'response', "")))

        # estimate values for the various "duration" fields in the final response
        # and update the response object with these values
        total_dur, load_dur, prompt_eval_dur, eval_dur = estimate_durations(init_waiting = init_sleep_time, total_waiting = (eval_delay + model_swap_waiting_time))
        setattr(resp, 'total_duration', total_dur)
        setattr(resp, 'load_duration', load_dur)
        setattr(resp, 'prompt_eval_count', 11) # ? Ollama says this field is the "number of input tokens in the prompt", but sets it to "11" for the prompt "hi".
        setattr(resp, 'prompt_eval_duration', prompt_eval_dur)
        setattr(resp, 'eval_count', len(tokenized_response_text) + 1) # "+1" to account for the final response, since Ollama seems to count this as a "token" as well
        setattr(resp, 'eval_duration', eval_dur)

        if body.logprobs == True:
            top_logprobs = None
            # using only one very simple token and its real, corresponding values
            # (gotten from asking "llama3.1:8b" to generate just the response "Hello")
            # TODO: test this out with Ollama a few times to get a feel for which values to use or ranges to generate random values from
            # TODO: (largest logprob observed: -0.36290687322616577
            # TODO: smallest non-scientific notation logprob observed: -0.0000011023458910131012,
            # TODO: smallest scientific-notation: -9.524187589704525e-7)
            logprobs = [{
                "token": "Hello",
                "logprob": -0.000014117495993559714,
                "bytes": [
                    72,
                    101,
                    108,
                    108,
                    111
                ]
            }]
            if body.top_logprobs != None and body.top_logprobs > 0:
                top_logprobs = [{
                    "token": "Hello",
                    "logprob": -0.000014117495993559714,
                    "bytes": [
                        72,
                        101,
                        108,
                        108,
                        111
                    ]
                }]
                logprobs[0]["top_logprobs"] = top_logprobs # add the top_logprobs if they were requested

            setattr(resp, 'logprobs', logprobs)

        # check if response should be streamed, and if so, call the streaming method and set headers accordingly
        if body.stream is not None and body.stream == True:
            streamed_resp = resp.model_copy(update={"response": ""})
            streaming_response = StreamingResponse(
                _build_generate_stream(resp.model, tokenized_response_text, eval_delay, streamed_resp),
                media_type="application/x-ndjson",
                headers=get_custom_headers("application/x-ndjson"), # "charset=utf-8" is not included for streaming responses by Ollama, so don't include it here either
            )

            return log_and_return(request, body, status_code, resp, streamed = True, final_stream_chunk = streaming_response)

        # additional sleeping and setting creation time for unstreamed responses is only done if there was a prompt to respond to in the first place:
        sleep(eval_delay)
        setattr(resp, 'created_at', datetime.now().isoformat()+"Z")

    # if response shouldn't be streamed, simply return the response as normal
    return log_and_return(request, body, status_code, resp, streamed = False)








