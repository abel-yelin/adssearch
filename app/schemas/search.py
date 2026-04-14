from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    domain: str = Field(..., description="要查询的域名", examples=["aiimagetovideo.ai"])
    region: str = Field(default="anywhere", description="区域过滤")
    max_scroll_pages: int = Field(default=10, ge=1, le=50, description="最大滚动页数")
    proxy: Optional[str] = Field(default=None, description="代理地址")
    timeout: int = Field(default=30000, ge=5000, le=120000, description="超时时间(ms)")


class SearchTaskSubmitResponse(BaseModel):
    success: bool
    task_id: str
    status: Literal["queued"]
    message: str


class SearchTaskStatusResponse(BaseModel):
    success: bool
    task_id: str
    status: Literal["queued", "started", "finished", "failed", "deferred", "scheduled", "stopped", "canceled", "unknown"]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
