"""SMTP Email sender service for Incentive Reports with auto-attached Excel/CSV files."""

import csv
import io
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import openpyxl

from app.config import get_settings
from app.models.reports.schemas import SendReportEmailRequest, SendReportEmailResponse


EXCEL_COLUMNS = [
    ("Coordinator Name", "coordinator_name"),
    ("Coordinator Type", "coordinator_type"),
    ("Candidate ID", "candidate_id"),
    ("Candidate Name", "candidate_name"),
    ("Start Date", "start_date"),
    ("Month", "month"),
    ("Cycle Name", "cycle_name"),
    ("Contract Type", "contract_type"),
    ("Margin/Finder Fees", "margin_finder_fees"),
    ("Monthly Hours / Days", "hours_placements"),
    ("Incentive Amount (INR)", "incentive_amount_inr"),
    ("Incentive Type", "incentive_type"),
    ("Candidate Source", "candidate_source"),
    ("Team", "team"),
]


def generate_excel_bytes(rows: List[Dict[str, Any]]) -> bytes:
    """Generate Excel binary buffer from report dictionary rows."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Incentive Report"

    # Header row
    headers = [col[0] for col in EXCEL_COLUMNS]
    ws.append(headers)

    # Data rows
    for r in rows:
        row_vals = []
        for col_name, key in EXCEL_COLUMNS:
            val = r.get(col_name) if col_name in r else r.get(key)
            if val is None:
                val = ""
            row_vals.append(val)
        ws.append(row_vals)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def generate_csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    """Generate CSV binary buffer from report dictionary rows."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    headers = [col[0] for col in EXCEL_COLUMNS]
    writer.writerow(headers)

    # Data rows
    for r in rows:
        row_vals = []
        for col_name, key in EXCEL_COLUMNS:
            val = r.get(col_name) if col_name in r else r.get(key)
            if val is None:
                val = ""
            row_vals.append(val)
        writer.writerow(row_vals)

    return output.getvalue().encode("utf-8")


def send_report_email(req: SendReportEmailRequest, db_rows: List[Dict[str, Any]]) -> SendReportEmailResponse:
    """Generates the report attachment in memory and sends it via SMTP."""
    settings = get_settings()

    # Determine which rows to include (selected_rows if provided, else all db_rows)
    rows_to_export = req.selected_rows if req.selected_rows and len(req.selected_rows) > 0 else db_rows

    # Generate attachment file
    file_format = (req.file_format or "EXCEL").upper()
    is_csv = file_format == "CSV"
    ext = "csv" if is_csv else "xlsx"

    date_str = datetime.now().strftime("%Y-%m-%d")
    div_part = (req.division or "All_Divisions").replace(" ", "_")
    count_part = f"_{len(rows_to_export)}selected" if req.selected_rows and len(req.selected_rows) > 0 else ""
    filename = f"Incentive_Report_{div_part}_{date_str}{count_part}.{ext}"

    if is_csv:
        file_bytes = generate_csv_bytes(rows_to_export)
        mime_subtype = "csv"
    else:
        file_bytes = generate_excel_bytes(rows_to_export)
        mime_subtype = "vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    # Construct recipients list
    to_list = [e.strip() for e in req.to_emails if e.strip()]
    cc_list = [e.strip() for e in (req.cc_emails or []) if e.strip()]
    all_recipients = list(dict.fromkeys(to_list + cc_list))

    if not to_list:
        raise ValueError("At least one valid 'To' recipient email address is required.")

    # Construct email message
    msg = MIMEMultipart()
    from_header = f"{settings.smtp_from_name} <{settings.smtp_from_email}>" if settings.smtp_from_name else settings.smtp_from_email
    msg["From"] = from_header
    msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)

    subject_text = req.subject or f"Incentive Report — {req.division or 'All Divisions'} — {date_str}"
    msg["Subject"] = subject_text

    # Default body text if not provided
    if req.body_text and req.body_text.strip():
        body_content = req.body_text
    else:
        total_amt = sum(float(r.get("Incentive Amount (INR)") or r.get("incentive_amount_inr") or 0) for r in rows_to_export)
        body_content = (
            f"Hello Team,\n\n"
            f"Please find attached below the report of incentives.\n\n"
            f"Incentive Report Summary — Generated on {date_str}\n"
            f"=======================================================\n\n"
            f"REPORT SUMMARY:\n"
            f"  Total Records   : {len(rows_to_export)}\n"
            f"  Total Incentive : INR {total_amt:,.2f}\n\n"
            f"Please find attached the exported report file ({filename}) for full row details.\n\n"
            f"Regards,\n"
            f"Incentive Tracker Portal"
        )

    msg.attach(MIMEText(body_content, "plain"))

    # Attach file
    attachment = MIMEApplication(file_bytes, _subtype=mime_subtype)
    attachment.add_header("Content-Disposition", "attachment", filename=filename)
    msg.attach(attachment)

    # Send via SMTP
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, all_recipients, msg.as_string())
    except Exception as e:
        raise RuntimeError(f"Failed to send email via SMTP ({settings.smtp_host}:{settings.smtp_port}): {str(e)}")

    return SendReportEmailResponse(
        success=True,
        message=f"Report email sent successfully with '{filename}' attached!",
        recipients_sent=all_recipients,
        filename_attached=filename,
    )
