from pathlib import Path
from os import getenv
from dotenv import load_dotenv
from time import monotonic
from datetime import datetime, timedelta
from random import randrange
from hashlib import sha256
from threading import RLock
from json import loads as json_loads
from dataclasses import dataclass, replace
from contextvars import ContextVar
from re import fullmatch as re_fullmatch, split as re_split # renaming imported methods to avoid confusion

######################################################################

# a file for loading environment variables needed for the honeypot,
# and for providing utilities like getting a model list or a client's IP, plus some helper functions to facilitate this
# FILE AND ITS CONTENTS WERE MOSTLY CREATED BY COPILOT, with a few tweaks here and there

######################################################################


SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")

model_list_raw = getenv("MODEL_LIST", "[]") # models are stored in a list in the .env, but the models are stored in a dict after being read/loaded
_parsed_model_list = list(json_loads(model_list_raw))

running_model = getenv("RUNNING_MODEL")

# ! The model dict is initialized by the "init_model_dict()" method AT THE END OF THE "get_or_create_session()" METHOD
# ! Specifically, the model dict initialization is done after the session is created, as the initialization relies on the session existing in the first place!


# ! SUGGESTIONS FROM GITHUB COPILOT - the IP-getter and -setter code and such was all from Copilot (tested and working, of course)
# ! ALL SESSION-RELATED CODE IS ALSO FROM COPILOT, with certain tweaks here and there!
# ! METHODS WITH DOCUMENTATION STRINGS WERE CREATED BY COPILOT AS WELL (again, tweaked as necessary)

# the RequestContext makes it easier to extend sessions with more context-specific fields later, should they be needed
# ! THE RequestContext WAS A SUGGESTION FROM COPILOT, AS WERE THE GETTER AND SETTER METHODS FOR IT AND THE FIELDS IN THE CLASS
@dataclass(frozen=True)
class RequestContext:
    client_ip: str | None = None
    latest_headers: dict[str, str] | None = None
    session_id: str | None = None

# session store contents can be seen in the "get_or_create_session()" method
# ? note, the type hint given for it only specifies the type of the models it contains, while the rest of the data are of other types
session_store: dict[str, dict] = {} # storage for session-specific data, including client-specific model dicts that clients can change for themselves only (i.e., on a per-session basis)
_session_lock = RLock() # lock to avoid race conditions when clients connect and simultaneously try to update their individual model lists
SESSION_TIMEOUT = 30 * 60 # sessions are removed from the session store after 30 minutes of inactivity (i.e., no requests from the client for that session)


current_request_context: ContextVar[RequestContext | None] = ContextVar("current_request_context", default=None)

def _get_request_context() -> RequestContext:
    context = current_request_context.get()
    return context if context is not None else RequestContext() # return an empty context class if no context was set yet

def set_request_context(
        client_ip: str | None = None,
        headers: dict[str, str] | None = None,
        session_id: str | None = None):
    rq_ctx = RequestContext(
        client_ip=client_ip,
        latest_headers=headers,
        session_id=session_id
    )
    current_request_context.set(rq_ctx)


def get_client_ip() -> str | None:
    return _get_request_context().client_ip

def set_client_ip(client_ip: str | None):
    context = _get_request_context()
    # 'replace' creates a new RequestContext object, inheriting existing values, but replacing the given field with the given value
    current_request_context.set(replace(context, client_ip=client_ip))


def get_client_headers() -> dict[str, str] | None:
    return _get_request_context().latest_headers

def set_client_headers(headers: dict[str, str] | None):
    context = _get_request_context()
    # 'replace' creates a new RequestContext object, inheriting existing values, but replacing the given field with the given value
    current_request_context.set(replace(context, latest_headers=headers))


def get_session_id() -> str | None:
    return _get_request_context().session_id

def set_session_id(session_id: str | None):
    context = _get_request_context()
    # 'replace' creates a new RequestContext object, inheriting existing values, but replacing the given field with the given value
    current_request_context.set(replace(context, session_id=session_id))


def _generate_session_id(client_ip: str | None, user_agent: str | None) -> str:
    """Generate a session ID from IP + User-Agent."""
    combined = f"{client_ip or 'unknown'}:{user_agent or 'unknown'}"
    result = sha256(combined.encode()).hexdigest()[:16]
    return result  # First 16 chars of hash

def get_or_create_session(client_ip: str | None, user_agent: str | None) -> str:
    """
    Identify or create a session for this client.
    (Called from middleware in `main.py`)
    """
    session_id = _generate_session_id(client_ip, user_agent)
    with _session_lock:

        # remove old sessions before trying to check for this session ID
        # (since "get_or_create_session()" gets called every time a new request is made, old sessions will get cleaned up often)
        # TODO: Maybe find a better way to clean up old sessions
        now = monotonic()
        for stored_session_id, data in list(session_store.items()):
            if now - data["last_access"] > SESSION_TIMEOUT:
                del session_store[stored_session_id]

        # check for the session ID in the session store and update its last access time, or just add it if it isn't there already
        if session_id not in session_store:
            # ? the "models" dict here will contain data of the type dict[str, dict[str, Any]]
            # ? see the "construct_model_details()" method for the content of the dict[str, Any] !
            session_store[session_id] = {
                "models": {},           # {} = use global default models
                "running_model": None,  # None = use global default running model
                "last_access": monotonic(), # set last access time to now
                "client_ip": client_ip,
                "user_agent": user_agent # TODO: determine if this field is actually needed or not! (might not be used, currently!)
            }
            # intialize the models for this session based on the default model list from the .env file
            session_store[session_id]["models"] = init_model_dict(_parsed_model_list)

        else:
            session_store[session_id]["last_access"] = monotonic()

    set_session_id(session_id)

    return session_id


# initializer for a session's model dict
# it loads the the given raw model list (list obtained by the caller from the .env file),
# creates a randomized creation time for each model (used for the modification time as well), working backwards from the current year and month (i.e., not from exact current time!)
# and calls the model details constructor method to add each model from the raw model list to a dict,
# with the key being the full model name and the value being the details dict (hence the return type of dict[str, dict]),
# and lastly, it sorts this model dict by the models' modification times
def init_model_dict(raw_model_list: list[str]) -> dict[str, dict]:
    models = {}

    for i, model in enumerate(raw_model_list):
        # choose a random, large amount of milliseconds to be subtracted from a baseline/starting-point creation time -
        # either the current time (if this is the first model) or the previous model's creation time -
        # to make models appear to have been created/pulled at sufficiently different times.
        # "604_800_000" is the amount of milliseconds in a week,
        # lower bound is half a week to avoid potentially very small differences in creation times,
        # upper bound is 4 weeks to allow for potentially lengthy creatime time differences
        rand_millis = randrange(int(604_800_000 / 2), int(4 * 604_800_000), 1)

        # set the baseline creation time to the current time or to the previous model's creation time (if it exists)
        baseline_creation_time = datetime.now()
        if i > 0:
            previous_model_creation_time_str = models[raw_model_list[i - 1]].get("creation_time", datetime.now().isoformat()+"Z")
            baseline_creation_time = datetime.strptime(
                previous_model_creation_time_str,
                "%Y-%m-%dT%H:%M:%S.%fZ"
            )

        # ? baseline time is converted to just the year and month to make creation times more consistent for clients;
        # ? otherwise, creation times might creep forward every time clients return after a short while
        # ? (creation times may still creep forward, but this should be less common)
        # TODO: confirm if creation times creep forward - and if so, when and why this might happen!
        randomized_creation_time = (
            datetime.strptime(baseline_creation_time.strftime("%Y-%m"), "%Y-%m")
            - timedelta(milliseconds=rand_millis)
        )

        # construct and store the model details dict for this model
        # (using the method for constructing model details to ensure a consistent structure and content of models' details)
        models[model] = construct_model_details(
            full_model_name = model,
            creation_time = randomized_creation_time.isoformat()+"Z",
            modification_time = randomized_creation_time.isoformat()+"Z",
            source_model = model
        )

    # sort the (now initialized) model dict by their modification times and return it
    return dict(
        sorted(
            models.items(),
            key=lambda item: item[1]["modification_time"],
            reverse=True,
        )
    )


# DEBUGGING METHOD for checking stuff about active sessions
def inspect_active_sessions() -> list[dict]:
    """Honeypot operator command: see who's connected and what they're seeing."""
    with _session_lock:
        return [
            {
                "session_id": sid,
                "ip": data["client_ip"],
                "user_agent": data["user_agent"],
                "custom_model_list": list((data.get("models") or {}).keys()),
                "last_activity": monotonic() - data["last_access"]
            }
            for sid, data in session_store.items()
        ]



# method for getting the model keys for this session
# (if session has no custom model list yet, the default model list from the .env will be returned instead, thus instantiating the session's model list)
def get_model_keys():
    # with the session's model dict being sorted after every update,
    # simply get the model keys for this session:
    return list(get_model_dict().keys())


def get_model_dict() -> dict[str, dict]:
    with _session_lock:
        if session_id := get_session_id():
            if session_id in session_store:
                models = session_store[session_id].get("models")
                return models if isinstance(models, dict) else {}

    return {}


# THIS METHOD's SORTING CODE WAS ESSENTIALLY JUST A SUGGESTION FROM COPILOT
# The method description was written manually, however, since the method should only be used under specific circumstances!
def sort_and_set_model_dict(models: dict[str, dict]):
    """
    This method sorts the given model dict by modification time, and then sets this sorted dict as the session's model dict.
    Note that this method should ONLY EVER be used by either the "add_model_to_session" method, or by the "remove_model_from_session" method.
    If the model dict needs to be updated then use those aforementioned methods for it instead,
    to make sure that the model dict's model details maintain their proper structure and content
    """
    # sort the given model dict by its modification time
    # (using the current time as a fallback in case of somehow malformed model detiails dicts)
    sorted_models = dict(sorted(models.items(), key=lambda x: x[1].get("modification_time", datetime.now().isoformat()+"Z"), reverse=True))
    
    with _session_lock:
        if session_id := get_session_id():
            if session_id in session_store:
                session_store[session_id]["models"] = sorted_models.copy()


# all details dicts for models are created using this method.
# If new details need to be added to the model details dict later,
# this method (and its method calls) are what should be updated!
def construct_model_details(
            full_model_name: str,
            creation_time: str | None = None,
            modification_time: str | None = None,
            source_model: str | None = None) -> dict:
    """
    This method constructs a dict for the details of the models in the session store's model dict.
    NOTE: this method doesn't alter the given parameters, aside from using the current time as a fallback in case of missing creation and/or modification times!
    """
    model_details = {
        "full_model_name": full_model_name,
        "creation_time": creation_time if creation_time is not None else datetime.now().isoformat()+"Z",
        "modification_time": modification_time if modification_time is not None else datetime.now().isoformat()+"Z",
        "source_model": source_model if source_model is not None else full_model_name
    }
    return model_details

# this method adds a dict item of the type "model_name: dict[str, Any]" to the session's model dict
# ? This method calls the "construct_model_details()" method which determines the content of this "dict[str, Any]" !
# ? (this "dict[str, Any]" is the dict that contains the details of a model in the model dict)
def add_model_to_session(
            full_model_name: str,
            creation_time: str | None = None,
            modification_time: str | None = None,
            source_model: str | None = None):
    model_details = construct_model_details(
        full_model_name=full_model_name,
        creation_time=creation_time,
        modification_time=modification_time,
        source_model=source_model
    )

    models = get_model_dict()

    # if model is already in the model dict, remember to keep its original creation time instead of overwriting it!
    # (can't actually remember if the creation time and modification time are ever actually different, but updating models' data appropriately is always best)
    if full_model_name in get_model_keys():
        model_details["creation_time"] = models[full_model_name].get("creation_time", model_details["creation_time"])

    models[full_model_name] = model_details
    sort_and_set_model_dict(models)


def remove_model_from_session(full_model_name: str):
    models = get_model_dict()
    models.pop(full_model_name, {}) # if full_model_name isn't found, updates "models" to be "{}" instead
    sort_and_set_model_dict(models)


# method for getting the running running model for this session
# (if session has no custom running model yet, the default running model from the .env will be returned instead, thus instantiating the session's running model)
def get_running_model():
    session_running_model = None
    with _session_lock:
        if session_id := get_session_id():
            if session_id in session_store:
                session_running_model = session_store[session_id].get("running_model")

    # try to get and return a model list for this session and use that, if there is one;
    # otherwise, just return the existing, global "running_model"
    return session_running_model if session_running_model is not None else running_model

# method for setting the running model for this session (used by endpoint handler methods that call a model to get an output)
def set_running_model(model_name: str):
    with _session_lock:
        if session_id := get_session_id():
            if session_id in session_store:
                session_store[session_id]["running_model"] = model_name

# helper function to get name of model (this method returns the full name, i.e., including both name and parameter count)
# NOTE: (if model given doesn't contain a parameter count, the model is assumed to be the desired model name already!)
def get_model_name(model: str):
    return model[:model.find(':')] if ':' in model else model


# helper method to get what should be the name of the given model's model family
# ? certain models keep some numbers in their model family's name, so these are treated as special-cases
def get_model_family_name(model: str):
    model_name = get_model_name(model)
    if "gemma" in model_name:
        return model_name # "gemma" models retain the number in their model name (e.g., the family name for "gemma3:4b" is "gemma3")
    elif "qwen2" in model_name:
        return model_name.split(".", 1)[0] # this model keeps the "2" in the name, but disregards the rest of the name if it contains a '.'
    elif "qwen3.6" in model_name:
        return "qwen35moe" # very special case that might as well get added to the party that this method is becoming...
    elif "qwen3" in model_name: # for qwen3 models other than qwen3.6:
        return model_name.replace(".", "") # the model "qwen3.5" would return a family name of "qwen35", so just take the name and remove the '.'
    
    # base-case family name is the first chunk of alphabetical characters (numbers are also not kept in the family name)
    # ? This may well produce inaccurate model names for some models but this is hard to avoid without more special-cases being added
    else:
        first_part = re_split(r"[^A-Za-z]+", model_name, maxsplit=1)[0]
        return first_part if first_part != "" else model_name


# helper function to get parameter count and suffix (e.g., returning "4" and "b" for "gemma3:4b")
def get_model_param_parts(model: str):
    match = re_fullmatch(r"\s*[^:]+:([0-9]+(?:\.[0-9]+)?)([a-zA-Z]+)\s*", model)
    if match is None:
        # if no parameter count could be extracted, assume a default parameter count instead
        # (guessing '8b' since it seemed somewhat common among Llama models and some Qwen models)
        # TODO: FIX THIS WHEN OLLAMA LIBRARY LOOKUPS ARE ADDED FOR CHECKING MODEL NAME VALIDITY!
        return "8", "b"

    return match.group(1), match.group(2)


# method for estimating sizes of models based on their parameter counts (provided these counts are present!)
# "* 0.48 + 0.89" was from trend observed in Ollama model sizes vs their parameter counts
# and the scaling is to convert the parameter count to an actual number in the range specified by the suffix.
def get_appropriate_model_size(model: str) -> int:
    multipliers = {
        "m": 1_234_567,
        "b": 1_234_567_891,
        "t": 1_234_567_891_234
    }

    # cloud models seem to always have a very small size (probably due to them not being fully downloaded, but running elsewhere),
    # so simply assume they all have the same size as "deepseek-v4-pro:cloud" and skip the estimation
    # TODO: Add special cases for different cloud models, since only a handful of cloud models seem to be commonly pulled!
    if "cloud" in model:
        return 344

    # if model doesn't have a parameter count, or is simply a ":latest" model, simply assume its parameter count
    # TODO: FIX THIS WHEN OLLAMA LIBRARY LOOKUPS ARE ADDED FOR CHECKING MODEL NAME VALIDITY!
    model = "name:8b" if (":latest" in model or ":" not in model) else model
    model_params, params_suffix = get_model_param_parts(model)
    suffix_scale_factor = multipliers.get(params_suffix, 1)
    
    return int((float(model_params) * 0.48 + 0.89) * suffix_scale_factor)


# method for tokenizing a response string,
# with the "tokens" simply being whole words,
# split with non-alphanumeric characters (including spaces) being included as the first characters of the next/following token
# INITIALLY GENERATED BY COPILOT, WITH SOME ADJUSTMENTS (e.g., using re.split() and a for-loop utilizing enumerate())
def tokenize(response_text: str):
    if response_text is None or response_text == "": # response might be empty, e.g., if the prompt is empty or missing
        return "" # empty prompts naturally lead to empty tokens

    # split and keep separators: spaces and single non-alnum chars are preserved
    tokens = re_split(r'(\s+|[^A-Za-z0-9])', response_text)
    tokens = [t for t in tokens if t != ''] # the split creates some empty tokens, so remove these
    
    # spaces and other non-alphanumeric characters are each a seperate token at this point,
    # so combine each with their respective, following token:
    for i, tok in enumerate(tokens):
        if tok.isspace():
            if i + 1 < len(tokens):
                tokens[i + 1] = tok + tokens[i + 1]
            continue
        yield tok


# small helper method for determining duration fields for the final response:
def estimate_durations(init_waiting: float, total_waiting: float):
    # value used to determine load_duration and prompt_eval_duration,
    # since their values combined tend to be slightly higher than the initial waiting time
    resp_prep_dur_cutoff = randrange(45, 80, 1) / 100

    # estimate values for the various "duration" fields in the final response,
    # with the estimation formulae being determined from observations of various responses from Ollama
    # "load_duration" and "prompt_eval_duration" tend to sum to a little more than the initial waiting time,
    # so using "1 - ___*0.9" to allow prompt_eval_duration to be a little higher than the remaining time after accounting for the value given to "load_duration"
    total_dur = int((total_waiting + init_waiting) * 1100220033)
    load_dur = int(init_waiting * 1000010203 * resp_prep_dur_cutoff)
    prompt_eval_dur = int(init_waiting * 1000010203 * (1 - resp_prep_dur_cutoff*0.9))
    eval_dur = total_dur - prompt_eval_dur

    return total_dur, load_dur, prompt_eval_dur, eval_dur
