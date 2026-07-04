"""
HIVE OS - PALADIN Layer 1: Input Validation & Sanitization
Blocks prompt injection, sanitizes inputs, separates instruction/data channels.
Based on OWASP LLM01:2025 and Microsoft/AWS 2026 security research.
"""

import re
import unicodedata
from typing import Optional, Tuple
from enum import Enum


class InputType(Enum):
    USER = "user"
    SYSTEM = "system"
    AGENT = "agent"
    UNKNOWN = "unknown"


class ThreatLevel(Enum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class ValidationResult:
    def __init__(self, is_valid: bool, threat_level: ThreatLevel, 
                 threat_type: str = "", sanitized: str = ""):
        self.is_valid = is_valid
        self.threat_level = threat_level
        self.threat_type = threat_type
        self.sanitized = sanitized


class InputValidator:
    """PALADIN Layer 1 - Input Validation and Sanitization"""
    
    # Known prompt injection patterns
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"ignore\s+(all\s+)?prior\s+instructions",
        r"disregard\s+(all\s+)?previous",
        r"forget\s+(all\s+)?instructions",
        r"you\s+are\s+now\s+",
        r"act\s+as\s+if\s+you\s+are",
        r"pretend\s+you\s+are",
        r"roleplay\s+as",
        r"new\s+instructions?:",
        r"system\s*:\s*",
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"\[INST\]",
        r"\[/INST\\]",
        r"<<SYS>>",
        r"<</SYS>>",
        r"<\|system\|>",
        r"<\|user\|>",
        r"<\|assistant\|>",
        r"Human:",
        r"Assistant:",
        r"AI:",
        r"System:",
        r"IMPORTANT:\s*",
        r"NOTE:\s*",
        r"WARNING:\s*",
        r"SECURITY\s+NOTICE:",
        r"OVERRIDE:",
        r"ADMIN\s+MODE:",
        r"DEBUG\s+MODE:",
        r"DEVELOPER\s+MODE:",
        r"jailbreak",
        r"DAN\s+mode",
        r"do\s+anything\s+now",
        r"bypass\s+(all\s+)?safety",
        r"disable\s+(all\s+)?safety",
        r"ignore\s+(all\s+)?safety",
        r"ignore\s+(all\s+)?restrictions",
        r"ignore\s+(all\s+)?limitations",
        r"ignore\s+(all\s+)?rules",
        r"ignore\s+(all\s+)?guidelines",
        r"ignore\s+(all\s+)?policies",
        r"ignore\s+(all\s+)?constraints",
        r"ignore\s+(all\s+)?boundaries",
        r"ignore\s+(all\s+)?filters",
        r"ignore\s+(all\s+)?moderation",
        r"override\s+(all\s+)?safety",
        r"bypass\s+(all\s+)?moderation",
        r"skip\s+(all\s+)?safety",
        r"disable\s+(all\s+)?moderation",
        r"turn\s+off\s+(all\s+)?safety",
        r"reveal\s+(your\s+)?(system\s+)?prompt",
        r"show\s+(your\s+)?(system\s+)?prompt",
        r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions)",
        r"print\s+(your\s+)?(system\s+)?(prompt|instructions)",
        r"output\s+(your\s+)?(system\s+)?(prompt|instructions)",
        r"repeat\s+(your\s+)?(system\s+)?(prompt|instructions)",
        r"extract\s+(your\s+)?(system\s+)?(prompt|instructions)",
        r"translate\s+(your\s+)?(system\s+)?(prompt|instructions)",
        r"encode\s+(your\s+)?(system\s+)?(prompt|instructions)",
        r"base64\s+encode",
        r"rot13",
        r"decode\s+this",
        r"execute\s+(this|the)\s+(code|command)",
        r"run\s+(this|the)\s+(code|command)",
        r"eval\s*\(",
        r"exec\s*\(",
        r"import\s+os",
        r"import\s+subprocess",
        r"__import__",
        r"os\.system",
        r"os\.popen",
        r"subprocess\.(run|call|Popen)",
    ]
    
    # Unicode characters that could be used for obfuscation
    DANGEROUS_UNICODE = [
        '\u200b',  # Zero-width space
        '\u200c',  # Zero-width non-joiner
        '\u200d',  # Zero-width joiner
        '\u200e',  # Left-to-right mark
        '\u200f',  # Right-to-left mark
        '\u2028',  # Line separator
        '\u2029',  # Paragraph separator
        '\u202a',  # Left-to-right embedding
        '\u202b',  # Right-to-left embedding
        '\u202c',  # Pop directional formatting
        '\u202d',  # Left-to-right override
        '\u202e',  # Right-to-left override
        '\ufeff',  # Zero-width no-break space
    ]
    
    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode
        self.injection_patterns = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in self.INJECTION_PATTERNS
        ]
    
    def normalize_unicode(self, text: str) -> str:
        """Normalize Unicode characters to prevent obfuscation attacks"""
        # Normalize to NFC form
        text = unicodedata.normalize('NFC', text)
        
        # Remove dangerous zero-width characters
        for char in self.DANGEROUS_UNICODE:
            text = text.replace(char, '')
        
        # Normalize common confusables
        replacements = {
            '\uff41': 'a',  # Fullwidth a
            '\uff42': 'b',  # Fullwidth b
            '\uff43': 'c',  # Fullwidth c
            '\uff44': 'd',  # Fullwidth d
            '\uff45': 'e',  # Fullwidth e
            '\uff46': 'f',  # Fullwidth f
            '\uff47': 'g',  # Fullwidth g
            '\uff48': 'h',  # Fullwidth h
            '\uff49': 'i',  # Fullwidth i
            '\uff4a': 'j',  # Fullwidth j
            '\uff4b': 'k',  # Fullwidth k
            '\uff4c': 'l',  # Fullwidth l
            '\uff4d': 'm',  # Fullwidth m
            '\uff4e': 'n',  # Fullwidth n
            '\uff4f': 'o',  # Fullwidth o
            '\uff50': 'p',  # Fullwidth p
            '\uff51': 'q',  # Fullwidth q
            '\uff52': 'r',  # Fullwidth r
            '\uff53': 's',  # Fullwidth s
            '\uff54': 't',  # Fullwidth t
            '\uff55': 'u',  # Fullwidth u
            '\uff56': 'v',  # Fullwidth v
            '\uff57': 'w',  # Fullwidth w
            '\uff58': 'x',  # Fullwidth x
            '\uff59': 'y',  # Fullwidth y
            '\uff5a': 'z',  # Fullwidth z
        }
        
        for old, new in replacements.items():
            text = text.replace(old, new)
        
        return text
    
    def detect_injection(self, text: str) -> Tuple[bool, ThreatLevel, str]:
        """Detect prompt injection attempts"""
        normalized = self.normalize_unicode(text)
        
        for pattern in self.injection_patterns:
            if pattern.search(normalized):
                return True, ThreatLevel.HIGH, f"Pattern: {pattern.pattern}"
        
        # Check for instruction-like structures
        if self._has_instruction_structure(normalized):
            return True, ThreatLevel.MEDIUM, "Instruction-like structure detected"
        
        # Check for excessive special characters
        if self._has_excessive_special_chars(normalized):
            return True, ThreatLevel.LOW, "Excessive special characters"
        
        return False, ThreatLevel.NONE, ""
    
    def _has_instruction_structure(self, text: str) -> bool:
        """Check for instruction-like structures in data fields"""
        # Look for patterns like "Step 1:", "First:", "1.", etc.
        instruction_starters = [
            r'^\s*(Step\s+\d+[:.])',
            r'^\s*(First|Second|Third|Fourth|Fifth)[:.]',
            r'^\s*(\d+\.)\s',
            r'^\s*(Instruction|Task|Directive|Command)[:.]',
            r'^\s*(Do|Don\'t|Never|Always|Must|Should|Shall)[:.]',
        ]
        
        for pattern in instruction_starters:
            if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
                return True
        
        return False
    
    def _has_excessive_special_chars(self, text: str) -> bool:
        """Check for excessive special characters that might indicate obfuscation"""
        if not text:
            return False
        
        special_chars = sum(1 for c in text if not c.isalnum() and not c.isspace())
        ratio = special_chars / len(text)
        
        return ratio > 0.3
    
    def classify_input(self, text: str, context: dict = None) -> InputType:
        """Classify input as user, system, or agent"""
        if context is None:
            context = {}
        
        # Check context hints
        if context.get('source') == 'user':
            return InputType.USER
        elif context.get('source') == 'system':
            return InputType.SYSTEM
        elif context.get('source') == 'agent':
            return InputType.AGENT
        
        # Heuristic classification
        text_lower = text.lower()
        
        # User-like patterns
        user_patterns = [
            r'^(can you|could you|please|help me|i want|i need)',
            r'^(what|how|why|when|where|who)',
            r'\?$',
        ]
        
        for pattern in user_patterns:
            if re.search(pattern, text_lower):
                return InputType.USER
        
        # System-like patterns
        system_patterns = [
            r'^(system|config|setting|environment)',
            r'^(error|warning|info|debug|trace)',
            r'^\[.*\]',
        ]
        
        for pattern in system_patterns:
            if re.search(pattern, text_lower):
                return InputType.SYSTEM
        
        # Agent-like patterns (structured, technical)
        agent_patterns = [
            r'^\{.*\}$',  # JSON-like
            r'^\[.*\]$',  # Array-like
            r'(task|agent|worker|delegate)',
            r'(spawn|execute|complete|status)',
        ]
        
        for pattern in agent_patterns:
            if re.search(pattern, text_lower):
                return InputType.AGENT
        
        return InputType.UNKNOWN
    
    def sanitize_inter_agent_message(self, message: str) -> str:
        """Sanitize message passed between agents (strip markdown/HTML)"""
        # Remove HTML tags
        message = re.sub(r'<[^>]+>', '', message)
        
        # Remove markdown formatting
        message = re.sub(r'\*\*.*?\*\*', '', message)  # Bold
        message = re.sub(r'\*.*?\*', '', message)  # Italic
        message = re.sub(r'`.*?`', '', message)  # Code
        message = re.sub(r'```.*?```', '', message, flags=re.DOTALL)  # Code block
        message = re.sub(r'\[.*?\]\(.*?\)', '', message)  # Links
        message = re.sub(r'#{1,6}\s', '', message)  # Headers
        message = re.sub(r'^\s*[-*+]\s', '', message, flags=re.MULTILINE)  # Lists
        message = re.sub(r'^\s*\d+\.\s', '', message, flags=re.MULTILINE)  # Numbered lists
        
        # Remove instruction-like patterns
        message = re.sub(r'^(System|Assistant|Human|AI|Bot):', '', message, flags=re.IGNORECASE)
        
        return message.strip()
    
    def validate(self, text: str, input_type: InputType = None, 
                 context: dict = None) -> ValidationResult:
        """Main validation method"""
        if context is None:
            context = {}
        
        # Classify input if not specified
        if input_type is None:
            input_type = self.classify_input(text, context)
        
        # Normalize Unicode
        normalized = self.normalize_unicode(text)
        
        # Detect injection
        has_injection, threat_level, threat_type = self.detect_injection(normalized)
        
        # Determine validity
        if has_injection and threat_level in [ThreatLevel.HIGH, ThreatLevel.CRITICAL]:
            is_valid = False
        elif self.strict_mode and has_injection and threat_level == ThreatLevel.MEDIUM:
            is_valid = False
        else:
            is_valid = True
        
        # Sanitize
        sanitized = self.sanitize_inter_agent_message(normalized) if input_type == InputType.AGENT else normalized
        
        return ValidationResult(
            is_valid=is_valid,
            threat_level=threat_level,
            threat_type=threat_type,
            sanitized=sanitized
        )


# Global instance
validator = InputValidator(strict_mode=True)


def validate_input(text: str, input_type: InputType = None, 
                   context: dict = None) -> ValidationResult:
    """Convenience function for input validation"""
    return validator.validate(text, input_type, context)


def is_safe(text: str) -> bool:
    """Quick safety check"""
    result = validator.validate(text)
    return result.is_valid


def sanitize(text: str) -> str:
    """Quick sanitization"""
    result = validator.validate(text)
    return result.sanitized
