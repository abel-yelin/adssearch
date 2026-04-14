from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    environment: str
    version: str
