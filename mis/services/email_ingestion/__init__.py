"""Email Ingestion Service Package for JobDiva Records."""

from mis.services.email_ingestion.pipeline import run_email_ingestion_pipeline

__all__ = ["run_email_ingestion_pipeline"]
