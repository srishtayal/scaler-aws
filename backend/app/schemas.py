from typing import Literal
from pydantic import BaseModel, Field, field_validator

RecordType = Literal['A', 'AAAA', 'CNAME', 'TXT', 'MX', 'NS', 'PTR', 'SRV', 'CAA']

class LoginInput(BaseModel):
    email: str
    password: str = Field(min_length=1)

class ZoneInput(BaseModel):
    name: str = Field(min_length=1, max_length=253)
    comment: str = Field(default='', max_length=256)
    private_zone: bool = False

    @field_validator('name')
    @classmethod
    def valid_name(cls, value):
        value = value.strip().lower().rstrip('.')
        if '.' not in value or ' ' in value:
            raise ValueError('Enter a valid domain name, such as example.com')
        return value

class RecordInput(BaseModel):
    name: str = Field(min_length=1, max_length=253)
    type: RecordType
    value: str = Field(min_length=1, max_length=2048)
    ttl: int = Field(default=300, ge=0, le=2147483647)
    routing_policy: str = Field(default='Simple', max_length=50)

    @field_validator('name', 'value')
    @classmethod
    def trimmed(cls, value):
        return value.strip()

class ImportInput(BaseModel):
    content: str = Field(min_length=1, max_length=1_000_000)
    format: Literal['bind', 'json'] = 'bind'

class BulkDeleteInput(BaseModel):
    record_ids: list[str] = Field(min_length=1, max_length=500)
