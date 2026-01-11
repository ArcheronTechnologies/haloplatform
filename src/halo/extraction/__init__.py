"""
Director extraction from Swedish annual reports (årsredovisningar).

This module extracts board member and director information from annual reports
obtained via the Bolagsverket HVD API. The reports are in iXBRL format (inline XBRL
embedded in XHTML), which provides structured data for extraction.

For older reports without iXBRL, PDF fallback extraction is available.

Main components:
- XBRLExtractor: Extract directors from iXBRL annual reports
- PDFExtractor: Fallback extraction from PDF annual reports
- ExtractionPipeline: Orchestrates the full extraction workflow
"""

from .models import ExtractedDirector, ExtractedAuditor, ExtractionResult
from .xbrl_extractor import XBRLExtractor
from .pdf_extractor import PDFExtractor
from .pipeline import ExtractionPipeline, PipelineConfig, CompanyInfo, DocumentInfo

__all__ = [
    "ExtractedDirector",
    "ExtractedAuditor",
    "ExtractionResult",
    "XBRLExtractor",
    "PDFExtractor",
    "ExtractionPipeline",
    "PipelineConfig",
    "CompanyInfo",
    "DocumentInfo",
]
