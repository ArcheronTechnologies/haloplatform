"""
Document upload API routes.

Provides document upload and processing functionality.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from halo.api.deps import AuditRepo, User
from halo.ingestion.document_upload import DocumentUploadAdapter

router = APIRouter()


class DocumentResponse(BaseModel):
    """Response model for processed document."""

    document_id: str
    title: str
    content_preview: str
    document_type: str
    language: str
    author: Optional[str]
    page_count: int
    filename: str
    file_size: int
    mime_type: str
    created_at: datetime


class DocumentSearchResult(BaseModel):
    """Search result for document queries."""

    document_id: str
    title: str
    snippet: str
    score: float
    document_type: str


# Initialize the adapter
_adapter = DocumentUploadAdapter()


@router.post("", response_model=DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    audit_repo: AuditRepo = None,
    user: User = None,
    case_id: Optional[UUID] = Query(None, description="Associate with case"),
    entity_id: Optional[UUID] = Query(None, description="Associate with entity"),
):
    """
    Upload and process a document.

    Extracts text content from PDF, Word, HTML, text, and email files.
    The extracted content is available for NLP analysis and search.
    """
    # Read file content
    content = await file.read()

    try:
        record = await _adapter.process_file(
            content=content,
            filename=file.filename or "unknown",
            mime_type=file.content_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"Required library not installed: {e}",
        )

    # Log the upload
    if audit_repo and user:
        await audit_repo.log(
            user_id=user.user_id,
            user_name=user.user_name,
            action="upload",
            resource_type="document",
            resource_id=UUID(record.source_id),
            details={
                "filename": file.filename,
                "file_size": len(content),
                "document_type": record.raw_data["document_type"],
                "case_id": str(case_id) if case_id else None,
                "entity_id": str(entity_id) if entity_id else None,
            },
        )

    raw = record.raw_data
    content_text = raw.get("content", "")

    return DocumentResponse(
        document_id=record.source_id,
        title=raw.get("title", file.filename),
        content_preview=content_text[:500] + "..." if len(content_text) > 500 else content_text,
        document_type=raw.get("document_type", "unknown"),
        language=raw.get("language", "sv"),
        author=raw.get("author"),
        page_count=raw.get("page_count", 0),
        filename=raw.get("filename", file.filename),
        file_size=raw.get("file_size", len(content)),
        mime_type=raw.get("mime_type", file.content_type or "application/octet-stream"),
        created_at=record.fetched_at,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    audit_repo: AuditRepo,
    user: User,
):
    """Get document by ID."""
    # Note: In a real implementation, this would query a document store
    raise HTTPException(
        status_code=501,
        detail="Document storage not implemented - documents are processed but not stored",
    )


@router.get("/{document_id}/content")
async def get_document_content(
    document_id: str,
    audit_repo: AuditRepo,
    user: User,
):
    """Get full document content."""
    raise HTTPException(
        status_code=501,
        detail="Document storage not implemented - documents are processed but not stored",
    )


@router.post("/batch", response_model=list[DocumentResponse])
async def upload_documents_batch(
    files: list[UploadFile] = File(...),
    audit_repo: AuditRepo = None,
    user: User = None,
    case_id: Optional[UUID] = Query(None, description="Associate all with case"),
):
    """
    Upload multiple documents at once.

    All documents will be processed and optionally associated with a case.
    """
    results = []
    errors = []

    for file in files:
        try:
            content = await file.read()
            record = await _adapter.process_file(
                content=content,
                filename=file.filename or "unknown",
                mime_type=file.content_type,
            )

            raw = record.raw_data
            content_text = raw.get("content", "")

            results.append(DocumentResponse(
                document_id=record.source_id,
                title=raw.get("title", file.filename),
                content_preview=content_text[:500] + "..." if len(content_text) > 500 else content_text,
                document_type=raw.get("document_type", "unknown"),
                language=raw.get("language", "sv"),
                author=raw.get("author"),
                page_count=raw.get("page_count", 0),
                filename=raw.get("filename", file.filename),
                file_size=raw.get("file_size", len(content)),
                mime_type=raw.get("mime_type", file.content_type or "application/octet-stream"),
                created_at=record.fetched_at,
            ))

            if audit_repo and user:
                await audit_repo.log(
                    user_id=user.user_id,
                    user_name=user.user_name,
                    action="upload",
                    resource_type="document",
                    resource_id=UUID(record.source_id),
                    details={
                        "filename": file.filename,
                        "batch": True,
                        "case_id": str(case_id) if case_id else None,
                    },
                )

        except (ValueError, ImportError) as e:
            errors.append({"filename": file.filename, "error": str(e)})

    if errors and not results:
        raise HTTPException(
            status_code=400,
            detail={"message": "All uploads failed", "errors": errors},
        )

    return results


@router.get("/types/supported")
async def get_supported_types():
    """Get list of supported document types."""
    return {
        "supported_types": [
            {"mime_type": "application/pdf", "extension": ".pdf", "name": "PDF"},
            {"mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "extension": ".docx", "name": "Word Document"},
            {"mime_type": "text/plain", "extension": ".txt", "name": "Plain Text"},
            {"mime_type": "text/html", "extension": ".html", "name": "HTML"},
            {"mime_type": "message/rfc822", "extension": ".eml", "name": "Email (EML)"},
            {"mime_type": "application/vnd.ms-outlook", "extension": ".msg", "name": "Outlook Email"},
        ],
        "max_file_size_mb": 50,
    }
