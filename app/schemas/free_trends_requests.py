from pydantic import BaseModel


class FreeTrendsRunRequestResponse(BaseModel):
    request_id: str
    status: str
    requested_at: str
    started_at: str | None = None
    finished_at: str | None = None
    run_id: str | None = None
    error_message: str | None = None
