import re
from typing import Any, Callable, Dict


def mask_email(text: str) -> str:
    return re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "[REDACTED_EMAIL]", text)


def mask_upi_vpa(text: str) -> str:
    return re.sub(r"[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z]{2,64}", "[REDACTED_UPI]", text)


def get_redaction_hook(role: str) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
    if role == "delivery":
        return lambda data: data
    else:
        def redact(data: Dict[str, Any]) -> Dict[str, Any]:
            redacted_data = {}
            for key, value in data.items():
                if isinstance(value, str):
                    redacted_data[key] = mask_email(mask_upi_vpa(value))
                else:
                    redacted_data[key] = value
            return redacted_data
        return redact
