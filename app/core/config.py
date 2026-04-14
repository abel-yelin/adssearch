from pydantic import BaseModel


class AppSettings(BaseModel):
    title: str = "Google Ads Transparency Scraper API"
    description: str = "查询域名在 Google Ads Transparency Center 的广告主和关联域名"
    version: str = "1.0.0"
    api_prefix: str = "/api"
    allow_origins: list[str] = ["*"]
    allow_credentials: bool = True
    allow_methods: list[str] = ["*"]
    allow_headers: list[str] = ["*"]


settings = AppSettings()

