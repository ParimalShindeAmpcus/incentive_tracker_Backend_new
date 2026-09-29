from pathlib import Path
from loguru import logger

from mis.core.config import settings
from mis.services.email_ingestion.email_reader import EmailReader
from mis.services.email_ingestion.excel_processor import process_jobdiva_excel
from mis.services.email_ingestion.ingestion_service import IngestionService


def clean_temp_folder() -> None:
    """Safely remove leftover files in the temporary attachment folder."""
    temp_path = Path(settings.ATTACHMENT_TEMP_DIR)
    if not temp_path.exists():
        return

    for file_item in temp_path.iterdir():
        if file_item.is_file():
            try:
                file_item.unlink()
            except Exception as e:
                logger.warning(f"Could not remove temp file {file_item.name}: {e}")


def run_email_ingestion_pipeline() -> bool:
    """Execute the end-to-end JobDiva email ingestion pipeline."""
    logger.info("================ Starting Email Ingestion Pipeline ================")

    clean_temp_folder()

    reader = EmailReader()
    service = IngestionService()

    try:
        downloaded_items = reader.connect_and_fetch_attachments()
    except Exception as e:
        logger.error(f"Failed to fetch attachments from mailbox: {e}")
        return False

    if not downloaded_items:
        logger.info("No new email attachments to process.")
        return False

    for item in downloaded_items:
        uid = item["uid"]
        mailbox = item["mailbox"]
        subject = item["subject"]
        att_name = item["attachment_name"]
        file_path = item["file_path"]

        logger.info(f"Processing attachment '{att_name}' from email UID {uid} ('{subject}')...")

        # Create audit log record
        log_id = service.create_import_log(
            mailbox=mailbox,
            message_subject=subject,
            attachment_name=att_name,
        )

        try:
            records, total_rows, valid_count, failed_rows = process_jobdiva_excel(file_path)

            inserted_rows, duplicate_rows = service.upsert_jobdiva_records(
                records=records,
                import_batch_id=log_id,
            )

            service.update_import_log(
                log_id=log_id,
                total_rows=total_rows,
                inserted_rows=inserted_rows,
                duplicate_rows=duplicate_rows,
                failed_rows=failed_rows,
                status="SUCCESS",
            )

            # Move email to Processed folder
            reader.move_email(uid, settings.IMAP_PROCESSED_FOLDER)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error processing attachment '{att_name}' for email UID {uid}: {error_msg}")

            service.update_import_log(
                log_id=log_id,
                total_rows=0,
                inserted_rows=0,
                duplicate_rows=0,
                failed_rows=0,
                status="FAILED",
                error_detail=error_msg,
            )

            # Move email to Failed folder
            reader.move_email(uid, settings.IMAP_FAILED_FOLDER)

    clean_temp_folder()
    logger.info("================ Email Ingestion Pipeline Finished ================")
    return True
