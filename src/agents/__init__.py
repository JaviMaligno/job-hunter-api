"""AI Agents for job hunting automation."""

from src.agents.base import BaseAgent
from src.agents.cv_adapter import (
    CoverLetterAgent,
    CoverLetterInput,
    CoverLetterOutput,
    CVAdapterAgent,
    CVAdapterInput,
    CVAdapterOutput,
)
from src.agents.email_parser import (
    EmailBatchParserAgent,
    EmailBatchParserInput,
    EmailBatchParserOutput,
    EmailContent,
    EmailParserAgent,
    EmailParserInput,
    EmailParserOutput,
    ExtractedJob,
)
from src.agents.form_filler import (
    CustomQuestion,
    FieldMapping,
    FormAnalysis,
    FormFillerAgent,
    FormFillerInput,
    FormFillerOutput,
    UserFormData,
)

__all__ = [
    # Base
    "BaseAgent",
    # CV Adapter
    "CVAdapterAgent",
    "CVAdapterInput",
    "CVAdapterOutput",
    "CoverLetterAgent",
    "CoverLetterInput",
    "CoverLetterOutput",
    # Email Parser
    "EmailParserAgent",
    "EmailParserInput",
    "EmailParserOutput",
    "EmailContent",
    "ExtractedJob",
    "EmailBatchParserAgent",
    "EmailBatchParserInput",
    "EmailBatchParserOutput",
    # Form Filler
    "FormFillerAgent",
    "FormFillerInput",
    "FormFillerOutput",
    "FormAnalysis",
    "UserFormData",
    "FieldMapping",
    "CustomQuestion",
]
