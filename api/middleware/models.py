from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Error response schema."""

    msg: str = Field(..., description="A detailed error message")
    status_code: int = Field(
        ...,
        description="The integer representing the HTTP status code",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "msg": "Workflow run not found",
                "status_code": 404,
            }
        }
    }
