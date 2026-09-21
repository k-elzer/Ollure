from time import sleep
from fastapi import Request
from classes.request_classes import *
from classes.response_classes import *
from response_cache.show_cache import construct_field_values
from utils import *
from logging_resources import *

# helper method to handle aliasing of field names for the ModelInfo response object.
# SUGGESTION FROM COPILOT !
def _prefix_model_info_aliases(model_info: ModelInfo, requested_model: str) -> dict[str, object]:
    """Serialize ModelInfo using runtime-prefixed aliases."""
    model_family = get_model_family_name(requested_model) # get the model family name as the alias prefix seems to be based on the family name
    model_info_data = model_info.model_dump(by_alias=False, exclude_defaults=True, exclude_none=True)
    prefixed_model_info = {}

    for field_name, value in model_info_data.items():
        field_meta = ModelInfo.model_fields.get(field_name)
        alias_template = field_meta.alias if field_meta is not None and field_meta.alias is not None else field_name
        aliased_field_name = alias_template.replace("MODELFAMILY", model_family)
        prefixed_model_info[aliased_field_name] = value

    return prefixed_model_info



def ep_show(request: Request, body: ShowRequest):
    resp = None
    status_code = 200

    # for some reason, Ollama allows the use of the 'name' field, which is interpreted the same way as the 'model' field.
    # To avoid contantly checking for both, simply set the 'model' field to the value provided,
    # preferring the 'model' field over the 'name' if both are provided (same as Ollama does)
    body.model = body.model if body.model not in [None, ""] else body.name

    # Ollama accepts model names with leading and/or trailing spaces,
    # and doesn't keep them for the various fields in the response,
    # so .strip() the model name before performing any other checks.
    # ".strip()" also fails if used on a None value, so the code checks for that first, before cleaning the model name
    if body.model != None:
        body.model = body.model.strip()

    if body.model == None or body.model == "":
        status_code = 400
        resp = ErrorResponse(error = "model is required")
        return log_and_return(request, body, status_code, resp)

    # Ollama returns "invalid model name" for quite a few different model names,
    # including names with spaces in the middle, or names without any alphanumeric characters,
    # (although it also returns this for models like ".:b", and I don't want to be too pedantic with model name checks, so I'll ignore such cases)
    elif not any(c.isalnum() for c in body.model) or " " in body.model: # if given model contains no alphanumeric characters or contains spaces other than leading/trailing spaces:
        status_code = 400
        resp = ErrorResponse(error = "invalid model name")
        return log_and_return(request, body, status_code, resp)

    # when checking if model exists in the model dict, ensure it's a full model name, but don't change the model name itself
    requested_model = body.model if ":" in body.model else body.model + ":latest"

    # verify that the requested model is being supported/emulated
    if requested_model not in get_model_keys():
        status_code = 404
        resp = ErrorResponse(error = f"model '{body.model}' not found")
        return log_and_return(request, body, status_code, resp)

    model_params, params_suffix = get_model_param_parts(requested_model)
    model_source = get_model_name(get_model_dict().get(requested_model, {}).get("source_model", requested_model))
    model_family = get_model_family_name(model_source)

    # initialize non-error response
    model_details = ModelDetails(
        parent_model = model_source if "cloud" in requested_model else "", # cloud models seem to be the only models that show a non-empty string for the parent model
        format = "" if "cloud" in requested_model else "gguf",
        family = model_family, # api/show actually shows a non-empty family field for cloud models, unlike /api/tags and /api/ps, so simply always set this field to the model family
        families = [model_family] if "cloud" not in requested_model else [],
        parameter_size = model_params + params_suffix.upper(),
        quantization_level = "Q4_K_M"
    )

    # ! the following model info values are hardcoded despite being different for different models!
    # TODO: FIX THIS IF/WHEN OLLAMA LIBRARY LOOKUPS ARE ADDED!
    model_info = None

    if "cloud" in requested_model:
        # model info for cloud models defaults to the info gotten from "deepseek-v4-pro:cloud"
        model_info = ModelInfo(
            context_length = 1048576,
            embedding_length = 4096,
            general_architecture = model_family,
            general_parameter_count = 1600000000000,
        )

    else:
        model_info = ModelInfo(
            attention_head_count = 8,
            attention_head_count_kv = 4,
            attention_key_length = 256,
            attention_sliding_window = 1024,
            attention_value_length = 256,
            block_count = 34,
            context_length = 131072,
            embedding_length = 2560,
            feed_forward_length = 10240,
            mm_tokens_per_image = 256,
            vision_attention_head_count = 16,
            vision_attention_layer_norm_epsilon = 0.000001,
            vision_block_count = 27,
            vision_embedding_length = 1152,
            vision_feed_forward_length = 4304,
            vision_image_size = 896,
            vision_num_channels = 3,
            vision_patch_size = 14,
            general_architecture = model_family,
            general_file_type = 15,
            general_license = model_family if "llama" in model_family else None, # 
            general_parameter_count = int(get_appropriate_model_size(requested_model) * 1.34), # This scaling isn't very accurate for larger models (like llama3.1:70b), but it might be sufficiently convincing?
            general_quantization_version = 2,
            tokenizer_ggml_add_bos_token = True,
            tokenizer_ggml_add_eos_token = False,
            tokenizer_ggml_add_padding_token = False,
            tokenizer_ggml_add_unknown_token = False,
            tokenizer_ggml_bos_token_id = 2,
            tokenizer_ggml_eos_token_id = 1,
            tokenizer_ggml_merges = "null", # using strings here is a workaround for not having actual 'null' as a type - 'None' would be too suspicious, as an attacker, to see in the response
            tokenizer_ggml_model = model_family,
            tokenizer_ggml_padding_token_id = 0,
            tokenizer_ggml_pre = "default" if "gemma" in requested_model else model_family, # "gemma3" models appear to have "default" here, while others have some variation of their model family name instead
            tokenizer_ggml_scores = "null",
            tokenizer_ggml_token_type = "null",
            tokenizer_ggml_tokens = "null",
            tokenizer_ggml_unknown_token_id = 3,
        )

    # TODO: ADD ACTUAL VALUES TO THIS LATER (with values probably kept in a seperate file, or just auto-generated somehow since it's a lot of data)
    if body.verbose == True:
        setattr(model_info, 'tokenizer_ggml_merges', [""])
        setattr(model_info, 'tokenizer_ggml_scores', [0])
        setattr(model_info, 'tokenizer_ggml_token_type', [0])
        setattr(model_info, 'tokenizer_ggml_tokens', [""])

    # values obtained from this method call are based on the response from /api/show for the model "gemma3:1b",
    # with data specific to "gemma3:1b" having been replaced with the corresponding values for this given model
    cached_field_values = construct_field_values(requested_model)

    resp = ShowResponse(
        license = None if "cloud" in requested_model else cached_field_values.get("license", None),
        modelfile = None if "cloud" in requested_model else cached_field_values.get("modelfile", None),
        parameters = None if "cloud" in requested_model else cached_field_values.get("parameters", None),
        template =  None if "cloud" in requested_model else cached_field_values.get("template", None),
        details = model_details,
        model_info = model_info,
        tensors = None if "cloud" in requested_model else cached_field_values.get("tensors", None),
        capabilities = ["completion", "tools", "thinking"], # TODO: UPDATE THIS IN CASE SUPPORT FOR OTHER MODELS EVER GETS ADDED
        modified_at = get_model_dict().get("modification_time", "2026-05-13T11:10:01.926506+01:00") # get and use the modification time or, if this doesn't exist for some reason, use some default time
    )

    aliased_resp = resp.model_dump(by_alias=False, exclude_defaults=True, exclude_none=True)
    aliased_resp["model_info"] = dict(sorted(_prefix_model_info_aliases(model_info, requested_model).items()))

    # a copy of the response, but with only some of the more interesting fields
    # (this is to avoid logging a bunch of data that isn't actually that interesting to look at)
    resp_to_log = aliased_resp.copy()

    # remove all the fields that aren't interesting enough to log
    resp_to_log.pop("license", None)
    resp_to_log.pop("modelfile", None)
    resp_to_log.pop("parameters", None)
    resp_to_log.pop("template", None)
    resp_to_log.pop("model_info", None)
    resp_to_log.pop("tensors", None)


    # this endpoint is faster than the other endpoints, so delay doesn't need to be that long
    sleep(0.152) # TODO: ADD RANDOMIZATION TO THE SLEEP TIME FOR THIS ENDPOINT!

    # ? "aliased_resp" is the full response and is set as the "final_stream_chunk" which is what is returned to the client,
    # ? while "resp_to_log" is what gets logged and (as such) is made so it doesn't contain as much of the 
    return log_and_return(request, body, status_code, resp_to_log, final_stream_chunk=aliased_resp)

    # ! USE THIS RETURN INSTEAD TO LOG THE FULL RESPONSE (including license, modelfile, model_info, etc.) !
    # return log_and_return(request, body, status_code, aliased_resp)








