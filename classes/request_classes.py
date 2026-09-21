from typing import List, Union
from pydantic import BaseModel, Field, ConfigDict
from classes.base_classes import BaseRequest


# ======== Helper classes ========

# Options is reused among several endpoints
class Options(BaseModel):
    seed: int | None = None
    temperature: float | None = None
    top_k: float | None = None
    top_p: float | None = None
    min_p: float | None = None
    stop: str | None = None
    max_ctx: int | None = None
    max_predict: int | None = None


class ToolCallsFunction(BaseModel):
    name: str
    description: str | None = None
    arguments: dict | None = None

class ToolCalls(BaseModel):
    function: ToolCallsFunction

class Message(BaseModel):
    role: str | None = None
    content: str | None = None
    images: List[str] | None = None
    tool_calls: List[ToolCalls] | None = None

class ToolsFunction(BaseModel):
    name: str
    parameters: dict
    description: str | None = None

class Tools(BaseModel):
    type: str
    function: ToolsFunction



# ===== classes for the bodies of the various requests =====
# ============= (named based on endpoint name) =============

class GenerateRequest(BaseRequest):
    model: str | None = None
    prompt: str | None = None
    suffix: str | None = None
    images: list[str] | None = None
    format: Union[str, dict] | None = None
    system: str | None = None
    stream: bool = True
    think: Union[bool, str] | None = None
    raw: bool | None = None
    keep_alive: Union[str, int] | None = None
    options: Options | None = None
    logprobs: bool | None = None
    top_logprobs: int | None = None


class ChatRequest(BaseRequest):
    model: str | None = None
    messages: List[Message] | None = None
    tools: list[Tools] | None = None
    format: Union[str, dict] | None = None
    options: Options | None = None
    stream: bool = True
    think: Union[bool, str] | None = None
    keep_alive: Union[str, int] | None = None
    logprobs: bool | None = None
    top_logprobs: int | None = None


class EmbedRequest(BaseRequest):
    model: str | None = None
    input: Union[str, List[str]] | None = None
    truncate: bool |None = True
    dimensions: int | None = None
    keep_alive: str | None = None
    options: Options | None = None

# the 'name' field works the same as the 'model' field
# (for some reason Ollama's API docs don't specify this field, but still accepts it as though it were the 'model' field...)
class ShowRequest(BaseRequest):
    model: str | None = None
    name: str | None = None
    verbose: bool = False


class CreateRequest(BaseRequest):
    model_config = ConfigDict(populate_by_name=True)

    model: str | None = None
    make_from: str = Field(default=None, alias="from") # "from" is a keyword in Python, so using an alias to avoid issues with this
    files: dict[str, str] | None = None # this field is not used/considered, outside of checking for when neither it, nor the "make_from" field, is provided
    template: str | None = None
    license: str | None = None
    system: str | None = None
    parameters: dict | None = None
    messages: List[Message] | None = None
    quantize: str | None = None
    stream: bool = True


class CopyRequest(BaseRequest):
    source: str | None = None
    destination: str | None = None


class PullRequest(BaseRequest):
    model: str | None = None
    insecure: bool = False
    stream: bool = True


class PushRequest(BaseRequest):
    model: str | None = None
    insecure: bool = False
    stream: bool = True
    

class DeleteRequest(BaseRequest):
    model: str | None = None






