"""
Audit Logger Module.

Logs all verification events, rule results, and user actions to
structured JSON log files for compliance and traceability.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from config import LOGS_DIR


class AuditLogger:
    def __init__(self, log_dir: Optional[str] = None):
        self.log_dir = Path(log_dir or LOGS_DIR)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        # Also set up a standard Python logger
        self.logger = logging.getLogger("audit")
        self.logger.setLevel(logging.INFO)
        
        # File handler for text logs
        fh = logging.FileHandler(self.log_dir / "audit.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        if not self.logger.handlers:
            self.logger.addHandler(fh)

    def log_event(self, event_type: str, case_id: str, details: Dict[str, Any], 
                  user: Optional[str] = None) -> Dict:
        """
        Log a structured audit event to both JSON file and text log.
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "case_id": case_id,
            "user": user or "system",
            "details": details
        }
        
        # Write to JSON Lines file (one event per line)
        json_log_path = self.log_dir / "audit_events.jsonl"
        with open(json_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        
        # Also log to standard logger
        self.logger.info(f"[{event_type}] Case={case_id} | {json.dumps(details, default=str)}")
        
        return event

    def log_verification_started(self, case_id: str, file_names: list, user: Optional[str] = None):
        return self.log_event(
            "VERIFICATION_STARTED",
            case_id,
            {"files": file_names, "count": len(file_names)},
            user
        )

    def log_verification_completed(self, case_id: str, overall_status: str, 
                                    total_pass: int, total_fail: int, user: Optional[str] = None):
        return self.log_event(
            "VERIFICATION_COMPLETED",
            case_id,
            {
                "overall_status": overall_status,
                "total_pass": total_pass,
                "total_fail": total_fail
            },
            user
        )

    def log_manual_override(self, case_id: str, rule_id: str, original_status: str, 
                             new_status: str, reason: str, user: str):
        return self.log_event(
            "MANUAL_OVERRIDE",
            case_id,
            {
                "rule_id": rule_id,
                "original_status": original_status,
                "new_status": new_status,
                "reason": reason
            },
            user
        )

    def get_events_for_case(self, case_id: str) -> list:
        """Retrieve all audit events for a specific case ID."""
        json_log_path = self.log_dir / "audit_events.jsonl"
        events = []
        
        if not json_log_path.exists():
            return events
            
        with open(json_log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if event.get("case_id") == case_id:
                        events.append(event)
                except json.JSONDecodeError:
                    continue
                    
        return events
