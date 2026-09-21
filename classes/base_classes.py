from pydantic import BaseModel, ConfigDict

# SUGGESTIONS FROM COPILOT TO HELP MAKE THE CODE MORE SCALABLE WITH MORE ENDPOINTS
class BaseRequest(BaseModel):
    """Base class for all request body models."""
    model_config = ConfigDict(extra="allow") # to allow unknown fields in the request body, instead of dropping them like they never existed


class BaseResponse(BaseModel):
    """Base class for all response body models."""
