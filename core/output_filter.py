"""
HIVE OS - PALADIN Layer 5: Output Filtering & Exfiltration Detection
Scans outputs for sensitive data, detects exfiltration, validates format.
Based on Microsoft/AWS 2026 security research.
"""

import re
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ThreatType(Enum):
    NONE = "none"
    SENSITIVE_DATA = "sensitive_data"
    API_KEY = "api_key"
    CREDENTIAL = "credential"
    PII = "pii"
    EXFILTRATION = "exfiltration"
    POLICY_VIOLATION = "policy_violation"
    FORMAT_ERROR = "format_error"


@dataclass
class FilterResult:
    is_safe: bool
    threat_type: ThreatType
    threat_details: str
    filtered_output: str
    redacted_count: int


class OutputFilter:
    """PALADIN Layer 5 - Output Filtering and Exfiltration Detection"""
    
    # Patterns for sensitive data detection
    SENSITIVE_PATTERNS = {
        ThreatType.API_KEY: [
            r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']?([a-zA-Z0-9\-_]{20,})["\']?',
            r'(?i)(sk|pk|ak|rk)[-_][a-zA-Z0-9]{20,}',
            r'(?i)Bearer\s+[a-zA-Z0-9\-_\.]{20,}',
            r'(?i)(token|secret|password)\s*[:=]\s*["\']?([^\s"\']{10,})["\']?',
        ],
        ThreatType.CREDENTIAL: [
            r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']?([^\s"\']{6,})["\']?',
            r'(?i)(username|user|login)\s*[:=]\s*["\']?([^\s"\']{3,})["\']?',
            r'(?i)(ssh|tls|ssl)[-_]?(key|cert|private)',
            r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----',
        ],
        ThreatType.PII: [
            r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b',  # SSN
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
            r'\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',  # Phone
            r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',  # Credit card
        ],
        ThreatType.EXFILTRATION: [
            r'(?i)(curl|wget|fetch)\s+.*https?://',
            r'(?i)(post|put|patch)\s+.*https?://',
            r'(?i)(upload|exfil|send|transmit)\s+(to|data|file)',
            r'(?i)(webhook|callback|redirect)\s*(url|endpoint)',
            r'(?i)(base64|encode|decode)\s*(and|&)?\s*(send|post|upload)',
        ],
    }
    
    # Patterns to redact (replace with [REDACTED])
    REDACT_PATTERNS = [
        (r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']?[a-zA-Z0-9\-_]{20,}["\']?', '[API_KEY_REDACTED]'),
        (r'(?i)(sk|pk|ak|rk)[-_][a-zA-Z0-9]{20,}', '[API_KEY_REDACTED]'),
        (r'(?i)Bearer\s+[a-zA-Z0-9\-_\.]{20,}', '[TOKEN_REDACTED]'),
        (r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']?[^\s"\']{6,}["\']?', '[PASSWORD_REDACTED]'),
        (r'(?i)(secret|token)\s*[:=]\s*["\']?[^\s"\']{10,}["\']?', '[SECRET_REDACTED]'),
        (r'\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b', '[SSN_REDACTED]'),
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]'),
        (r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----.*?-----END\s+(RSA\s+)?PRIVATE\s+KEY-----', '[PRIVATE_KEY_REDACTED]'),
    ]
    
    def __init__(self, strict_mode: bool = True, auto_redact: bool = True):
        self.strict_mode = strict_mode
        self.auto_redact = auto_redact
        self.compiled_patterns = self._compile_patterns()
        self.redact_patterns = [(re.compile(p, re.DOTALL), r) for p, r in self.REDACT_PATTERNS]
    
    def _compile_patterns(self) -> Dict[ThreatType, List[re.Pattern]]:
        """Compile all regex patterns"""
        compiled = {}
        for threat_type, patterns in self.SENSITIVE_PATTERNS.items():
            compiled[threat_type] = [re.compile(p, re.IGNORECASE | re.DOTALL) for p in patterns]
        return compiled
    
    def scan_output(self, output: str) -> Tuple[bool, ThreatType, str]:
        """Scan output for sensitive data and threats"""
        for threat_type, patterns in self.compiled_patterns.items():
            for pattern in patterns:
                match = pattern.search(output)
                if match:
                    return False, threat_type, f"Detected: {threat_type.value} at position {match.start()}"
        
        return True, ThreatType.NONE, "Clean"
    
    def redact_sensitive(self, output: str) -> Tuple[str, int]:
        """Redact sensitive data from output"""
        redacted = output
        count = 0
        
        for pattern, replacement in self.redact_patterns:
            new_text, n = pattern.subn(replacement, redacted)
            if n > 0:
                redacted = new_text
                count += n
        
        return redacted, count
    
    def validate_format(self, output: str, expected_format: str = None) -> Tuple[bool, str]:
        """Validate output format"""
        if expected_format is None:
            return True, "No format specified"
        
        if expected_format == "json":
            try:
                json.loads(output)
                return True, "Valid JSON"
            except json.JSONDecodeError as e:
                return False, f"Invalid JSON: {e}"
        
        if expected_format == "code":
            # Basic code validation
            if len(output.strip()) == 0:
                return False, "Empty code output"
            if output.count('{') != output.count('}'):
                return False, "Unmatched braces"
            if output.count('(') != output.count(')'):
                return False, "Unmatched parentheses"
            return True, "Valid code structure"
        
        return True, "Format check passed"
    
    def check_exfiltration_attempt(self, output: str, context: dict = None) -> Tuple[bool, str]:
        """Check for data exfiltration attempts"""
        if context is None:
            context = {}
        
        # Check for external URLs in output
        url_pattern = re.compile(r'https?://[^\s<>"]+')
        urls = url_pattern.findall(output)
        
        # Known safe domains
        safe_domains = [
            'github.com', 'gitlab.com', 'stackoverflow.com',
            'docs.python.org', 'developer.mozilla.org',
            'pypi.org', 'npmjs.com'
        ]
        
        for url in urls:
            domain = re.search(r'https?://([^/]+)', url)
            if domain:
                domain_name = domain.group(1).lower()
                is_safe = any(sd in domain_name for sd in safe_domains)
                
                if not is_safe and context.get('allow_external_urls', False) is False:
                    return True, f"External URL detected: {url}"
        
        # Check for encoded data that might be exfiltration
        if re.search(r'(?i)(base64|encode).*?(send|post|upload|transmit)', output):
            return True, "Potential encoded exfiltration detected"
        
        return False, "No exfiltration detected"
    
    def filter_output(self, output: str, context: dict = None) -> FilterResult:
        """Main filtering method - comprehensive output analysis"""
        if context is None:
            context = {}
        
        # Step 1: Scan for threats
        is_clean, threat_type, threat_details = self.scan_output(output)
        
        # Step 2: Check exfiltration
        is_exfil, exfil_details = self.check_exfiltration_attempt(output, context)
        if is_exfil:
            return FilterResult(
                is_safe=False,
                threat_type=ThreatType.EXFILTRATION,
                threat_details=exfil_details,
                filtered_output="[EXFILTRATION_BLOCKED] Output blocked due to exfiltration attempt",
                redacted_count=0
            )
        
        # Step 3: If threat detected and strict mode, block
        if not is_clean and self.strict_mode:
            return FilterResult(
                is_safe=False,
                threat_type=threat_type,
                threat_details=threat_details,
                filtered_output=f"[BLOCKED] Output contains {threat_type.value}",
                redacted_count=0
            )
        
        # Step 4: Auto-redact if enabled
        filtered_output = output
        redacted_count = 0
        
        if self.auto_redact:
            filtered_output, redacted_count = self.redact_sensitive(output)
        
        # Step 5: Format validation if specified
        expected_format = context.get('expected_format')
        if expected_format:
            is_valid_format, format_msg = self.validate_format(filtered_output, expected_format)
            if not is_valid_format:
                return FilterResult(
                    is_safe=False,
                    threat_type=ThreatType.FORMAT_ERROR,
                    threat_details=format_msg,
                    filtered_output=f"[FORMAT_ERROR] {format_msg}",
                    redacted_count=redacted_count
                )
        
        # Step 6: Length check
        max_length = context.get('max_length', 10000)
        if len(filtered_output) > max_length:
            filtered_output = filtered_output[:max_length] + "...[TRUNCATED]"
        
        return FilterResult(
            is_safe=True,
            threat_type=ThreatType.NONE,
            threat_details="Output passed all filters",
            filtered_output=filtered_output,
            redacted_count=redacted_count
        )


# Global instance
output_filter = OutputFilter(strict_mode=True, auto_redact=True)


def filter_output(output: str, context: dict = None) -> FilterResult:
    """Convenience function for output filtering"""
    return output_filter.filter_output(output, context)


def is_safe_output(output: str) -> bool:
    """Quick safety check on output"""
    result = output_filter.filter_output(output)
    return result.is_safe


def redact_sensitive(output: str) -> str:
    """Quick redaction"""
    result = output_filter.filter_output(output, {'max_length': 999999})
    return result.filtered_output
