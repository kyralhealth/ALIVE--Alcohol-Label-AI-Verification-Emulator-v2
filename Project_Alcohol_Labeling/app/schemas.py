"""Pydantic models shared by the API, extraction, and comparison layers."""
from typing import List, Optional

from pydantic import BaseModel, Field


class ApplicationData(BaseModel):
    """What the applicant typed into their COLA application."""

    brand_name: str = ""
    class_type: str = ""
    alcohol_content: str = ""  # free text, e.g. "45% Alc./Vol. (90 Proof)" or "45"
    net_contents: str = ""     # free text, e.g. "750 mL" or "1 L"


class ExtractedLabel(BaseModel):
    """What Claude read off the label image. Fields are None when absent/illegible."""

    brand_name: Optional[str] = None
    class_type: Optional[str] = None
    alcohol_content: Optional[str] = None
    net_contents: Optional[str] = None
    government_warning: Optional[str] = None
    warning_prefix_verbatim: Optional[str] = None  # exact casing of the "GOVERNMENT WARNING:" lead-in
    warning_appears_bold: Optional[str] = None     # "yes" | "no" | "unclear"
    image_legibility: str = "good"                 # "good" | "poor"
    legibility_notes: Optional[str] = None


class FieldResult(BaseModel):
    field: str
    status: str  # "match" | "review" | "mismatch" | "missing"
    label_value: Optional[str] = None
    application_value: Optional[str] = None
    note: Optional[str] = None


class VerificationResult(BaseModel):
    overall: str  # "pass" | "review" | "fail"
    fields: List[FieldResult]
    image_legibility: str = "good"
    legibility_notes: Optional[str] = None
    elapsed_seconds: Optional[float] = None


class BatchItemResult(BaseModel):
    filename: str
    error: Optional[str] = None
    application: Optional[ApplicationData] = None
    result: Optional[VerificationResult] = None


class BatchResponse(BaseModel):
    items: List[BatchItemResult]
    summary: dict = Field(default_factory=dict)
