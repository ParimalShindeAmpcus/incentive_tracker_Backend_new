import json
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from mis.core.config import settings


@contextmanager
def get_db_connection():
    """Context manager for acquiring and closing a PostgreSQL connection."""
    conn_str = settings.sync_database_url
    conn = psycopg2.connect(conn_str)
    try:
        yield conn
    finally:
        conn.close()


class IngestionService:
    def __init__(self):
        self.table_name = settings.TARGET_TABLE_NAME

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        reraise=True,
    )
    def create_import_log(
        self,
        mailbox: str,
        message_subject: str,
        attachment_name: str,
    ) -> int:
        """Create a new record in email_import_logs with RUNNING status."""
        query = """
            INSERT INTO email_import_logs (
                mailbox, message_subject, attachment_name, status, run_started_at
            ) VALUES (%s, %s, %s, 'RUNNING', NOW())
            RETURNING id;
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (mailbox, message_subject, attachment_name))
                log_id = cur.fetchone()[0]
                conn.commit()
                logger.info(f"Created email import log ID {log_id} for attachment '{attachment_name}'.")
                return log_id

    def update_import_log(
        self,
        log_id: int,
        total_rows: int,
        inserted_rows: int,
        duplicate_rows: int,
        failed_rows: int,
        status: str = "SUCCESS",
        error_detail: Optional[str] = None,
    ) -> None:
        """Update email_import_logs record with final counts, status, and completion time."""
        query = """
            UPDATE email_import_logs
            SET total_rows = %s,
                inserted_rows = %s,
                duplicate_rows = %s,
                failed_rows = %s,
                status = %s,
                error_detail = %s,
                run_completed_at = NOW()
            WHERE id = %s;
        """
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    query,
                    (
                        total_rows,
                        inserted_rows,
                        duplicate_rows,
                        failed_rows,
                        status,
                        error_detail,
                        log_id,
                    ),
                )
                conn.commit()
                logger.info(
                    f"Updated email import log ID {log_id}: status={status}, "
                    f"total={total_rows}, inserted={inserted_rows}, "
                    f"updated/duplicates={duplicate_rows}, failed={failed_rows}."
                )

    def upsert_jobdiva_records(
        self,
        records: List[Dict],
        import_batch_id: int,
    ) -> Tuple[int, int]:
        """
        Perform PostgreSQL UPSERT into imported_jobdiva_records on conflict (activity_id).
        Returns: (inserted_count, duplicate_or_updated_count)
        """
        if not records:
            return 0, 0

        upsert_query = f"""
            INSERT INTO {self.table_name} (
                activity_id,
                position_type,
                candidate_full_name,
                candidate_email,
                candidate_city,
                candidate_state,
                candidate_mobile_phone,
                job_company,
                activity_date,
                jobdiva_ref_no,
                recruited_by,
                recruiter_email,
                job_title,
                work_city,
                work_state,
                start_date,
                end_date,
                end_client_name,
                work_authorization,
                organization_id,
                import_batch_id,
                raw_row_json,
                is_consumed,
                updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
            )
            ON CONFLICT (activity_id) DO UPDATE SET
                position_type = EXCLUDED.position_type,
                candidate_full_name = EXCLUDED.candidate_full_name,
                candidate_email = EXCLUDED.candidate_email,
                candidate_city = EXCLUDED.candidate_city,
                candidate_state = EXCLUDED.candidate_state,
                candidate_mobile_phone = EXCLUDED.candidate_mobile_phone,
                job_company = EXCLUDED.job_company,
                activity_date = EXCLUDED.activity_date,
                jobdiva_ref_no = EXCLUDED.jobdiva_ref_no,
                recruited_by = EXCLUDED.recruited_by,
                recruiter_email = EXCLUDED.recruiter_email,
                job_title = EXCLUDED.job_title,
                work_city = EXCLUDED.work_city,
                work_state = EXCLUDED.work_state,
                start_date = EXCLUDED.start_date,
                end_date = EXCLUDED.end_date,
                end_client_name = EXCLUDED.end_client_name,
                work_authorization = EXCLUDED.work_authorization,
                organization_id = COALESCE(EXCLUDED.organization_id, {self.table_name}.organization_id),
                import_batch_id = EXCLUDED.import_batch_id,
                raw_row_json = EXCLUDED.raw_row_json,
                updated_at = NOW()
            RETURNING (xmax = 0) AS is_inserted;
        """

        inserted_count = 0
        duplicate_count = 0

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                for rec in records:
                    raw_json_str = (
                        json.dumps(rec.get("raw_row_json")) if rec.get("raw_row_json") is not None else None
                    )
                    params = (
                        rec.get("activity_id"),
                        rec.get("position_type"),
                        rec.get("candidate_full_name"),
                        rec.get("candidate_email"),
                        rec.get("candidate_city"),
                        rec.get("candidate_state"),
                        rec.get("candidate_mobile_phone"),
                        rec.get("job_company"),
                        rec.get("activity_date"),
                        rec.get("jobdiva_ref_no"),
                        rec.get("recruited_by"),
                        rec.get("recruiter_email"),
                        rec.get("job_title"),
                        rec.get("work_city"),
                        rec.get("work_state"),
                        rec.get("start_date"),
                        rec.get("end_date"),
                        rec.get("end_client_name"),
                        rec.get("work_authorization"),
                        rec.get("organization_id"),
                        import_batch_id,
                        raw_json_str,
                        rec.get("is_consumed", False),
                    )

                    cur.execute(upsert_query, params)
                    res = cur.fetchone()
                    if res and res[0]:
                        inserted_count += 1
                    else:
                        duplicate_count += 1

                conn.commit()

        logger.info(
            f"UPSERT into '{self.table_name}' complete: {inserted_count} new row(s) inserted, "
            f"{duplicate_count} existing row(s) updated."
        )

        return inserted_count, duplicate_count
