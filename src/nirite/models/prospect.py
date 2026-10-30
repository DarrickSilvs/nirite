from pydantic import BaseModel, Field

class Prospect(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None

    job_title: str | None = None
    company_name: str | None = None
    company_domain: str | None = None
    company_website: str | None = None
    profile_url: str | None = None
    email: str | None = None
    country: str | None = None
    state: str | None = None
    city: str | None = None

    extra_fields : dict[str, str | None] = Field(default_factory=dict)

    source_file: str
    source_row: int
