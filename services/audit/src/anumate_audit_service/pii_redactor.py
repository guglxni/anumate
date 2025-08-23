"""
PII Redaction Engine
===================

A.27 Implementation: Automatic detection and redaction of Personally Identifiable 
Information (PII) for compliance with GDPR, CCPA, and other privacy regulations.
"""

import re
import json
import hashlib
import logging
from typing import Any, Dict, List, Set, Optional, Union
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class PIIType(Enum):
    """Types of PII that can be detected and redacted."""
    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IP_ADDRESS = "ip_address"
    NAME = "name"
    ADDRESS = "address"
    DRIVERS_LICENSE = "drivers_license"
    PASSPORT = "passport"
    DATE_OF_BIRTH = "date_of_birth"
    BANK_ACCOUNT = "bank_account"
    API_KEY = "api_key"
    PASSWORD = "password"


@dataclass
class PIIMatch:
    """Represents a detected PII match."""
    pii_type: PIIType
    value: str
    start_pos: int
    end_pos: int
    confidence: float
    context: str


@dataclass
class RedactionConfig:
    """Configuration for PII redaction."""
    enabled_types: Set[PIIType]
    redaction_char: str = "*"
    preserve_length: bool = True
    preserve_format: bool = True
    hash_pii: bool = False
    hash_salt: str = "audit_service_salt"
    min_confidence: float = 0.8


class PIIRedactor:
    """
    Advanced PII detection and redaction engine.
    
    Features:
    - Pattern-based detection for common PII types
    - Configurable redaction strategies
    - Context-aware detection to reduce false positives
    - Hash-based consistent redaction
    - Format preservation for structured data
    """
    
    # Regex patterns for PII detection
    PATTERNS = {
        PIIType.EMAIL: re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            re.IGNORECASE
        ),
        PIIType.PHONE: re.compile(
            r'(?:\+?1[-.\s]?)?(?:\(?[0-9]{3}\)?[-.\s]?)?[0-9]{3}[-.\s]?[0-9]{4}\b'
        ),
        PIIType.SSN: re.compile(
            r'\b(?!000|666|9\d{2})\d{3}[-.]?(?!00)\d{2}[-.]?(?!0000)\d{4}\b'
        ),
        PIIType.CREDIT_CARD: re.compile(
            r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3[0-9]{13}|6(?:011|5[0-9]{2})[0-9]{12})\b'
        ),
        PIIType.IP_ADDRESS: re.compile(
            r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
        ),
        PIIType.DRIVERS_LICENSE: re.compile(
            r'\b[A-Z]{1,2}[0-9]{6,8}\b'
        ),
        PIIType.PASSPORT: re.compile(
            r'\b[A-Z][0-9]{8}\b'
        ),
        PIIType.DATE_OF_BIRTH: re.compile(
            r'\b(?:0[1-9]|1[0-2])[/-](?:0[1-9]|[12][0-9]|3[01])[/-](?:19|20)\d{2}\b'
        ),
        PIIType.BANK_ACCOUNT: re.compile(
            r'\b[0-9]{8,17}\b'
        ),
        PIIType.API_KEY: re.compile(
            r'\b[A-Za-z0-9]{32,}\b'
        )
    }
    
    # Sensitive field names that likely contain PII
    SENSITIVE_FIELDS = {
        PIIType.EMAIL: {"email", "email_address", "user_email", "contact_email"},
        PIIType.PHONE: {"phone", "phone_number", "mobile", "telephone", "cell"},
        PIIType.NAME: {"name", "full_name", "first_name", "last_name", "username", "display_name"},
        PIIType.ADDRESS: {"address", "street", "city", "zip", "postal_code", "country"},
        PIIType.SSN: {"ssn", "social_security", "social_security_number"},
        PIIType.DATE_OF_BIRTH: {"dob", "date_of_birth", "birth_date", "birthday"},
        PIIType.PASSWORD: {"password", "passwd", "pwd", "secret", "token", "auth_token"},
        PIIType.API_KEY: {"api_key", "access_key", "secret_key", "private_key"}
    }
    
    def __init__(self, config: RedactionConfig):
        self.config = config
        self._hash_cache = {}
        
    def redact_text(self, text: str, context: str = "") -> tuple[str, List[PIIMatch]]:
        """
        Redact PII from plain text.
        
        Args:
            text: The text to redact PII from
            context: Context for better PII detection
            
        Returns:
            Tuple of (redacted_text, list_of_matches)
        """
        if not text:
            return text, []
            
        matches = self._detect_pii(text, context)
        redacted_text = self._apply_redactions(text, matches)
        
        return redacted_text, matches
        
    def redact_json(self, data: Union[Dict, List, Any], context: str = "") -> tuple[Union[Dict, List, Any], List[PIIMatch]]:
        """
        Redact PII from JSON-serializable data structures.
        
        Args:
            data: The data structure to redact
            context: Context for better PII detection
            
        Returns:
            Tuple of (redacted_data, list_of_matches)
        """
        all_matches = []
        
        if isinstance(data, dict):
            redacted_data = {}
            for key, value in data.items():
                field_context = f"{context}.{key}" if context else key
                redacted_value, matches = self._redact_value(key, value, field_context)
                redacted_data[key] = redacted_value
                all_matches.extend(matches)
                
        elif isinstance(data, list):
            redacted_data = []
            for i, item in enumerate(data):
                item_context = f"{context}[{i}]" if context else f"[{i}]"
                redacted_item, matches = self.redact_json(item, item_context)
                redacted_data.append(redacted_item)
                all_matches.extend(matches)
                
        else:
            redacted_data, matches = self._redact_primitive_value(data, context)
            all_matches.extend(matches)
            
        return redacted_data, all_matches
        
    def _redact_value(self, field_name: str, value: Any, context: str) -> tuple[Any, List[PIIMatch]]:
        """Redact a single field value based on field name and content."""
        matches = []
        
        # Check if field name suggests PII
        field_pii_type = self._get_field_pii_type(field_name.lower())
        
        if isinstance(value, str):
            if field_pii_type and field_pii_type in self.config.enabled_types:
                # Direct field-based redaction
                redacted_value = self._redact_by_type(value, field_pii_type)
                matches.append(PIIMatch(
                    pii_type=field_pii_type,
                    value=value,
                    start_pos=0,
                    end_pos=len(value),
                    confidence=0.95,
                    context=context
                ))
            else:
                # Pattern-based detection
                redacted_value, detected_matches = self.redact_text(value, context)
                matches.extend(detected_matches)
                
        elif isinstance(value, (dict, list)):
            redacted_value, nested_matches = self.redact_json(value, context)
            matches.extend(nested_matches)
            
        else:
            redacted_value = value
            
        return redacted_value, matches
        
    def _redact_primitive_value(self, value: Any, context: str) -> tuple[Any, List[PIIMatch]]:
        """Redact a primitive value (string, number, etc.)."""
        if isinstance(value, str):
            return self.redact_text(value, context)
        else:
            return value, []
            
    def _detect_pii(self, text: str, context: str = "") -> List[PIIMatch]:
        """Detect PII patterns in text."""
        matches = []
        
        for pii_type in self.config.enabled_types:
            if pii_type not in self.PATTERNS:
                continue
                
            pattern = self.PATTERNS[pii_type]
            
            for match in pattern.finditer(text):
                confidence = self._calculate_confidence(match.group(), pii_type, context)
                
                if confidence >= self.config.min_confidence:
                    matches.append(PIIMatch(
                        pii_type=pii_type,
                        value=match.group(),
                        start_pos=match.start(),
                        end_pos=match.end(),
                        confidence=confidence,
                        context=context
                    ))
                    
        # Remove overlapping matches (keep highest confidence)
        matches = self._remove_overlaps(matches)
        
        return matches
        
    def _apply_redactions(self, text: str, matches: List[PIIMatch]) -> str:
        """Apply redactions to text based on detected matches."""
        if not matches:
            return text
            
        # Sort matches by position (reverse order for safe replacement)
        matches.sort(key=lambda x: x.start_pos, reverse=True)
        
        redacted_text = text
        
        for match in matches:
            if match.pii_type in self.config.enabled_types:
                replacement = self._generate_replacement(match.value, match.pii_type)
                redacted_text = (
                    redacted_text[:match.start_pos] + 
                    replacement + 
                    redacted_text[match.end_pos:]
                )
                
        return redacted_text
        
    def _generate_replacement(self, value: str, pii_type: PIIType) -> str:
        """Generate a replacement for detected PII."""
        if self.config.hash_pii:
            return self._hash_pii(value, pii_type)
            
        if self.config.preserve_format:
            return self._format_preserving_redaction(value, pii_type)
        elif self.config.preserve_length:
            return self.config.redaction_char * len(value)
        else:
            return f"[REDACTED_{pii_type.value.upper()}]"
            
    def _format_preserving_redaction(self, value: str, pii_type: PIIType) -> str:
        """Generate format-preserving redaction."""
        if pii_type == PIIType.EMAIL:
            at_pos = value.find('@')
            if at_pos > 0:
                domain = value[at_pos:]
                username_len = at_pos
                return self.config.redaction_char * username_len + domain
                
        elif pii_type == PIIType.PHONE:
            # Preserve separators in phone numbers
            redacted = ""
            for char in value:
                if char.isdigit():
                    redacted += self.config.redaction_char
                else:
                    redacted += char
            return redacted
            
        elif pii_type == PIIType.CREDIT_CARD:
            # Show last 4 digits
            if len(value) >= 4:
                return self.config.redaction_char * (len(value) - 4) + value[-4:]
                
        elif pii_type == PIIType.SSN:
            # Preserve separators, show last 4 digits
            if len(value) >= 4:
                redacted = ""
                last_four_pos = len(value) - 4
                for i, char in enumerate(value):
                    if char.isdigit():
                        if i >= last_four_pos:
                            redacted += char
                        else:
                            redacted += self.config.redaction_char
                    else:
                        redacted += char
                return redacted
                
        # Default: preserve length only
        return self.config.redaction_char * len(value)
        
    def _hash_pii(self, value: str, pii_type: PIIType) -> str:
        """Generate consistent hash for PII value."""
        if value in self._hash_cache:
            return self._hash_cache[value]
            
        # Create deterministic hash
        hash_input = f"{self.config.hash_salt}:{pii_type.value}:{value}"
        hash_value = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
        hashed_pii = f"[{pii_type.value.upper()}_{hash_value}]"
        
        self._hash_cache[value] = hashed_pii
        return hashed_pii
        
    def _redact_by_type(self, value: str, pii_type: PIIType) -> str:
        """Redact value based on its detected type."""
        return self._generate_replacement(value, pii_type)
        
    def _get_field_pii_type(self, field_name: str) -> Optional[PIIType]:
        """Determine PII type based on field name."""
        for pii_type, field_names in self.SENSITIVE_FIELDS.items():
            if field_name in field_names or any(name in field_name for name in field_names):
                return pii_type
        return None
        
    def _calculate_confidence(self, value: str, pii_type: PIIType, context: str) -> float:
        """Calculate confidence score for detected PII."""
        base_confidence = 0.7
        
        # Boost confidence for certain patterns
        if pii_type == PIIType.EMAIL and "@" in value and "." in value:
            base_confidence = 0.9
        elif pii_type == PIIType.PHONE and len(re.sub(r'\D', '', value)) >= 10:
            base_confidence = 0.85
        elif pii_type == PIIType.CREDIT_CARD and self._luhn_check(value):
            base_confidence = 0.95
        elif pii_type == PIIType.SSN and len(re.sub(r'\D', '', value)) == 9:
            base_confidence = 0.9
            
        # Context-based adjustments
        if context:
            context_lower = context.lower()
            field_pii_type = self._get_field_pii_type(context_lower)
            if field_pii_type == pii_type:
                base_confidence = min(0.98, base_confidence + 0.2)
                
        # Reduce confidence for common false positives
        if pii_type == PIIType.API_KEY:
            # API keys in logs might be legitimate
            if "log" in context.lower() or "debug" in context.lower():
                base_confidence *= 0.5
                
        return min(1.0, base_confidence)
        
    def _luhn_check(self, card_number: str) -> bool:
        """Validate credit card number using Luhn algorithm."""
        digits = [int(d) for d in re.sub(r'\D', '', card_number)]
        
        for i in range(len(digits) - 2, -1, -2):
            digits[i] *= 2
            if digits[i] > 9:
                digits[i] -= 9
                
        return sum(digits) % 10 == 0
        
    def _remove_overlaps(self, matches: List[PIIMatch]) -> List[PIIMatch]:
        """Remove overlapping matches, keeping highest confidence."""
        if len(matches) <= 1:
            return matches
            
        # Sort by confidence (descending) then by position
        matches.sort(key=lambda x: (-x.confidence, x.start_pos))
        
        non_overlapping = []
        
        for match in matches:
            # Check if this match overlaps with any already selected match
            overlaps = False
            for selected in non_overlapping:
                if (match.start_pos < selected.end_pos and 
                    match.end_pos > selected.start_pos):
                    overlaps = True
                    break
                    
            if not overlaps:
                non_overlapping.append(match)
                
        return non_overlapping
        
    def get_redaction_summary(self, matches: List[PIIMatch]) -> Dict[str, int]:
        """Generate summary of redacted PII types."""
        summary = {}
        
        for match in matches:
            pii_type_name = match.pii_type.value
            summary[pii_type_name] = summary.get(pii_type_name, 0) + 1
            
        return summary


# Predefined configurations for different compliance requirements
GDPR_CONFIG = RedactionConfig(
    enabled_types={
        PIIType.EMAIL, PIIType.PHONE, PIIType.NAME, PIIType.ADDRESS,
        PIIType.DATE_OF_BIRTH, PIIType.IP_ADDRESS
    },
    preserve_format=True,
    hash_pii=True,
    min_confidence=0.8
)

CCPA_CONFIG = RedactionConfig(
    enabled_types={
        PIIType.EMAIL, PIIType.PHONE, PIIType.NAME, PIIType.ADDRESS,
        PIIType.SSN, PIIType.CREDIT_CARD, PIIType.IP_ADDRESS
    },
    preserve_format=True,
    hash_pii=True,
    min_confidence=0.8
)

HIPAA_CONFIG = RedactionConfig(
    enabled_types={
        PIIType.EMAIL, PIIType.PHONE, PIIType.NAME, PIIType.ADDRESS,
        PIIType.SSN, PIIType.DATE_OF_BIRTH, PIIType.BANK_ACCOUNT
    },
    preserve_format=True,
    hash_pii=True,
    min_confidence=0.9
)

PCI_DSS_CONFIG = RedactionConfig(
    enabled_types={
        PIIType.CREDIT_CARD, PIIType.BANK_ACCOUNT, PIIType.API_KEY,
        PIIType.PASSWORD
    },
    preserve_format=False,
    hash_pii=True,
    min_confidence=0.95
)
