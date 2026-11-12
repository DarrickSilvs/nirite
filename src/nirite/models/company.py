from pydantic import BaseModel, Field

class CompanyProspect(BaseModel):
    company_name: str | None = None
    company_domain: str | None = None
    company_website: str | None = None
    industry: str | None = None
    company_size: str | None = None
    region: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None
    linkedin_url: str | None = None
    description: str | None = None

    extra_fields: dict[str, str | None] = Field(default_factory=dict)

    source_file: str
    source_row: int
