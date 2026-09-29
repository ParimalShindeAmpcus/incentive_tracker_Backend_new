import os
import re
from pathlib import Path
from typing import Dict, List, Optional
from imap_tools import AND, MailBox, MailboxLoginError
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from mis.core.config import settings


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent directory traversal and special character issues."""
    filename = Path(filename).name
    filename = re.sub(r"[^\w\.-]", "_", filename)
    return filename


class EmailReader:
    def __init__(self):
        self.host = settings.IMAP_SERVER
        self.port = settings.IMAP_PORT
        self.email = settings.IMAP_EMAIL
        self.password = settings.IMAP_PASSWORD
        self.inbox_folder = settings.IMAP_INBOX_FOLDER
        self.processed_folder = settings.IMAP_PROCESSED_FOLDER
        self.failed_folder = settings.IMAP_FAILED_FOLDER
        self.sender_filter = settings.IMAP_SENDER_FILTER
        self.temp_dir = Path(settings.ATTACHMENT_TEMP_DIR)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def connect_and_fetch_attachments(self) -> List[Dict]:
        """
        Connect to IMAP server, retrieve unread emails containing Excel attachments,
        download attachments to local temp directory, and return details.
        """
        if not self.email or not self.password:
            logger.error("IMAP credentials (IMAP_EMAIL / IMAP_PASSWORD) are not set.")
            return []

        logger.info(f"Connecting to IMAP server {self.host}:{self.port} as {self.email}...")

        downloaded_items = []

        try:
            with MailBox(self.host, port=self.port).login(
                self.email, self.password, initial_folder=self.inbox_folder
            ) as mailbox:
                # Ensure Processed and Failed folders exist
                self._verify_or_create_folders(mailbox)

                # Fetch unread emails
                query = AND(seen=False)
                fetched_messages = list(mailbox.fetch(query, reverse=False))

                logger.info(f"Found {len(fetched_messages)} unread email(s) in '{self.inbox_folder}'.")

                for msg in fetched_messages:
                    sender = msg.from_
                    subject = msg.subject
                    uid = msg.uid

                    # Filter by sender if filter is set
                    if self.sender_filter and self.sender_filter.strip():
                        filter_emails = [e.strip().lower() for e in self.sender_filter.split(",")]
                        if sender.lower() not in filter_emails:
                            logger.info(f"Skipping email UID {uid} from '{sender}' (not in sender filter).")
                            continue

                    excel_attachments = [
                        att for att in msg.attachments if att.filename.lower().endswith((".xlsx", ".xls"))
                    ]

                    if not excel_attachments:
                        logger.info(f"No Excel attachments found in email UID {uid} ('{subject}').")
                        continue

                    for att in excel_attachments:
                        safe_name = sanitize_filename(att.filename)
                        save_path = self.temp_dir / safe_name

                        # Save attachment
                        with open(save_path, "wb") as f:
                            f.write(att.payload)

                        logger.info(f"Downloaded attachment '{safe_name}' from email UID {uid} to '{save_path}'.")

                        downloaded_items.append(
                            {
                                "uid": uid,
                                "sender": sender,
                                "subject": subject,
                                "attachment_name": safe_name,
                                "file_path": str(save_path),
                                "mailbox": self.email,
                            }
                        )

        except MailboxLoginError as e:
            logger.error(f"IMAP Authentication failed for {self.email}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error while fetching emails: {e}")
            raise

        return downloaded_items

    def _verify_or_create_folders(self, mailbox: MailBox) -> None:
        """Verify that Processed and Failed folders exist in the mailbox; create if missing."""
        try:
            folder_info_list = mailbox.folder.list()
            existing_folders = [f.name for f in folder_info_list]

            for folder in [self.processed_folder, self.failed_folder]:
                if folder not in existing_folders:
                    logger.info(f"Creating missing IMAP folder '{folder}'...")
                    mailbox.folder.create(folder)
        except Exception as e:
            logger.warning(f"Note on IMAP folder verification: {e}")

    def move_email(self, uid: str, target_folder: str) -> bool:
        """Move an email by UID to target_folder (Processed or Failed)."""
        try:
            with MailBox(self.host, port=self.port).login(
                self.email, self.password, initial_folder=self.inbox_folder
            ) as mailbox:
                mailbox.move(uid, target_folder)
                logger.info(f"Moved email UID {uid} to '{target_folder}'.")
                return True
        except Exception as e:
            logger.error(f"Failed to move email UID {uid} to '{target_folder}': {e}")
            return False
