from typing import List, Union
from pydantic import BaseModel, Field, ConfigDict
from classes.request_classes import ToolCalls # some classes in the request can be reused in the response
from classes.base_classes import BaseResponse


# ======== Helper classes ========

class TopLogprob(BaseModel):
    token: str
    logprob: float
    bytes: List[int]

class LogprobItem(BaseModel):
    token: str
    logprob: float
    bytes: List[int]
    top_logprobs: List[TopLogprob] | None = None


# this Message class is different from the one in the request_classes file
class Message(BaseModel):
    role: str
    content: str | None = None
    thinking: str | None = None
    tool_calls: List[ToolCalls] | None = None
    images: List[str] | None = None


class ModelDetails(BaseModel):
    parent_model: str
    format: str
    family: str
    families: List[str]
    parameter_size: str
    quantization_level: str

class Model(BaseModel):
    name : str
    model: str
    remote_model: str | None = None
    remote_host: str | None = None
    modified_at: str | None = None
    size: int
    digest: str
    details: ModelDetails
    expires_at: str | None = None       # *
    size_vram: int | None = None        # only used for running models (GET-requests to /api/ps)
    context_length: int | None = None   # *

# ! IT SEEMS THE MODEL INFO FIELDS CHANGE FROM MODEL TO MODEL:
# ? this class uses aliases because the field names cannot contain dots,
# ? but the aliasing is handled in the /api/show endpoint handler's code
class ModelInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    attention_head_count: int | None = Field(default=None, alias="MODELFAMILY.attention.head_count")
    attention_head_count_kv: int | None = Field(default=None, alias="MODELFAMILY.attention.head_count_kv")
    attention_key_length: int | None = Field(default=None, alias="MODELFAMILY.attention.key_length")
    attention_sliding_window: int | None = Field(default=None, alias="MODELFAMILY.attention.sliding_window")
    attention_value_length: int | None = Field(default=None, alias="MODELFAMILY.attention.value_length")
    block_count: int | None = Field(default=None, alias="MODELFAMILY.block_count")
    context_length: int | None = Field(default=None, alias="MODELFAMILY.context_length")
    embedding_length: int | None = Field(default=None, alias="MODELFAMILY.embedding_length")
    feed_forward_length: int | None = Field(default=None, alias="MODELFAMILY.feed_forward_length")
    mm_tokens_per_image: int | None = Field(default=None, alias="MODELFAMILY.mm.tokens_per_image")
    vision_attention_head_count: int | None = Field(default=None, alias="MODELFAMILY.vision.attention.head_count")
    vision_attention_layer_norm_epsilon: float | None = Field(default=None, alias="MODELFAMILY.vision.attention.layer_norm_epsilon")
    vision_block_count: int | None = Field(default=None, alias="MODELFAMILY.vision.block_count")
    vision_embedding_length: int | None = Field(default=None, alias="MODELFAMILY.vision.embedding_length")
    vision_feed_forward_length: int | None = Field(default=None, alias="MODELFAMILY.vision.feed_forward_length")
    vision_image_size: int | None = Field(default=None, alias="MODELFAMILY.vision.image_size")
    vision_num_channels: int | None = Field(default=None, alias="MODELFAMILY.vision.num_channels")
    vision_patch_size: int | None = Field(default=None, alias="MODELFAMILY.vision.patch_size")
    general_architecture: str | None = Field(default=None, alias="general.architecture")
    general_file_type: int | None = Field(default=None, alias="general.file_type")
    general_license: str | None = Field(default=None, alias="general.license")
    general_parameter_count: int | None = Field(default=None, alias="general.parameter_count")
    general_quantization_version: int | None = Field(default=None, alias="general.quantization_version")
    tokenizer_ggml_add_bos_token: bool | None = Field(default=None, alias="tokenizer.ggml.add_bos_token")
    tokenizer_ggml_add_eos_token: bool | None = Field(default=None, alias="tokenizer.ggml.add_eos_token")
    tokenizer_ggml_add_padding_token: bool | None = Field(default=None, alias="tokenizer.ggml.add_padding_token")
    tokenizer_ggml_add_unknown_token: bool | None = Field(default=None, alias="tokenizer.ggml.add_unknown_token")
    tokenizer_ggml_bos_token_id: int | None = Field(default=None, alias="tokenizer.ggml.bos_token_id")
    tokenizer_ggml_eos_token_id: int | None = Field(default=None, alias="tokenizer.ggml.eos_token_id")
    tokenizer_ggml_merges: Union[List[str], str, None] = Field(default=None, alias="tokenizer.ggml.merges")           # *
    tokenizer_ggml_model: str | None = Field(default=None, alias="tokenizer.ggml.model")
    tokenizer_ggml_padding_token_id: int | None = Field(default=None, alias="tokenizer.ggml.padding_token_id")
    tokenizer_ggml_pre: str | None = Field(default=None, alias="tokenizer.ggml.pre")
    tokenizer_ggml_scores: Union[List[int], str, None] = Field(default=None, alias="tokenizer.ggml.scores")           # supposedly "null" in both Ollama's example, and in what I get myself when using this endpoint,
    tokenizer_ggml_token_type: Union[List[int], str, None] = Field(default=None, alias="tokenizer.ggml.token_type")   # but "null" isn't a type in Python
    tokenizer_ggml_tokens: Union[List[str], str, None] = Field(default=None, alias="tokenizer.ggml.tokens")           # *
    tokenizer_ggml_unknown_token_id: int | None = Field(default=None, alias="tokenizer.ggml.unknown_token_id")

class Tensor(BaseModel):
    name: str
    type: str
    shape: List[int]


class V1Model(BaseModel):
    id: str
    object: str
    created: int
    owned_by: str


# ===== classes for the bodies of the various responses =====

class ErrorResponse(BaseResponse):
    error: str


class RootResponse(BaseResponse):
    message: str


class GenerateResponse(BaseResponse):
    model: str
    created_at: str
    response: str
    # thinking: str # not needed for gemma3:4b
    done: bool
    done_reason: str | None = None # this field is optional because response chunks for streamed responses don't include this field until the final chunk
    context: List[int] | None = None      # this field isn't specified in the Ollama docs, but I think it's still given when actually using Ollama
    total_duration: int | None = None
    load_duration: int | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration: int | None = None
    eval_count: int | None = None
    eval_duration: int | None = None
    logprobs: List[LogprobItem] | None = None


class ChatResponse(BaseResponse):
    model: str
    created_at: str
    message: Message
    # thinking: str # not needed for gemma3:4b
    done: bool
    done_reason: str | None = None # this field is optional because response chunks for streamed responses don't include this field until the final chunk
    # context: List[int] | None = None      # this field isn't specified in the Ollama docs, but I think it's still given when actually using Ollama
    logprobs: List[LogprobItem] | None = None
    total_duration: int | None = None
    load_duration: int | None = None
    prompt_eval_count: int | None = None
    prompt_eval_duration: int | None = None
    eval_count: int | None = None
    eval_duration: int | None = None


class EmbedResponse(BaseResponse):
    model: str
    embeddings: List[List[float]]
    total_duration: int | None = None
    load_duration: int | None = None
    prompt_eval_count: int | None = None


class TagsResponse(BaseResponse):
    models : List[Model]


# The optional fields here are to handle cloud models, which do not use those fields;
# other fields seem to be included in all responses, however
class ShowResponse(BaseResponse):
    license: str | None = None
    modelfile: str | None = None
    parameters: str | None = None
    template: str | None = None
    details: ModelDetails
    model_info: ModelInfo | None = None # this field is only made optional so a response meant only for logging can be made!
    tensors: List[Tensor] | None = None
    capabilities: List[str]
    modified_at : str


# this response class is used for the /api/create, /api/pull, and /api/push endpoints' responses,
# since they all have the same overall response body structure.
# (/api/create only uses the "status" field, while /api/pull and /api/push also use the others for most of their responses, both streamed and non-streamed)
class ModelModificationResponse(BaseResponse):
    status: str
    digest: str | None = None
    total: int | None = None
    completed: int | None = None


class VersionResponse(BaseResponse):
    version: str


class V1ModelsResponse(BaseResponse):
    object: str
    data: List[V1Model]

