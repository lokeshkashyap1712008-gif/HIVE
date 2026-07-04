"""
HIVE OS - PALADIN Layer 3: Inter-Agent Message Authentication
Cryptographic signing, verification, impersonation detection.
Based on A2A Protocol security and mTLS patterns.
"""

import hashlib
import hmac
import json
import time
import secrets
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import asyncio


class MessageType(Enum):
    TASK_ASSIGN = "task_assign"
    TASK_RESULT = "task_result"
    HEARTBEAT = "heartbeat"
    DEBATE_ROUND = "debate_round"
    VOTE = "vote"
    EMERGENCY = "emergency"
    STATUS_UPDATE = "status_update"
    REQUEST = "request"
    RESPONSE = "response"


@dataclass
class MessageEnvelope:
    """Authenticated message envelope with signature"""
    message_id: str
    sender_id: str
    receiver_id: str
    message_type: MessageType
    timestamp: float
    payload: dict
    signature: str = ""
    nonce: str = ""
    
    def to_dict(self) -> dict:
        return {
            'message_id': self.message_id,
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'message_type': self.message_type.value,
            'timestamp': self.timestamp,
            'payload': self.payload,
            'signature': self.signature,
            'nonce': self.nonce
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MessageEnvelope':
        return cls(
            message_id=data['message_id'],
            sender_id=data['sender_id'],
            receiver_id=data['receiver_id'],
            message_type=MessageType(data['message_type']),
            timestamp=data['timestamp'],
            payload=data['payload'],
            signature=data.get('signature', ''),
            nonce=data.get('nonce', '')
        )


class AgentKeyStore:
    """Secure key storage for agent identities"""
    
    def __init__(self):
        self.keys: Dict[str, Dict[str, str]] = {}
        self.secrets: Dict[str, str] = {}
    
    def generate_keypair(self, agent_id: str) -> Tuple[str, str]:
        """Generate HMAC keypair for agent"""
        secret = secrets.token_hex(32)
        public = hashlib.sha256(secret.encode()).hexdigest()
        
        self.keys[agent_id] = {
            'public': public,
            'secret': secret
        }
        self.secrets[agent_id] = secret
        
        return public, secret
    
    def get_secret(self, agent_id: str) -> Optional[str]:
        """Get agent's secret key"""
        return self.secrets.get(agent_id)
    
    def get_public(self, agent_id: str) -> Optional[str]:
        """Get agent's public key"""
        if agent_id in self.keys:
            return self.keys[agent_id]['public']
        return None
    
    def has_keys(self, agent_id: str) -> bool:
        """Check if agent has registered keys"""
        return agent_id in self.keys


class MessageSigner:
    """Signs messages with agent identity"""
    
    def __init__(self, key_store: AgentKeyStore):
        self.key_store = key_store
    
    def sign_message(self, envelope: MessageEnvelope) -> MessageEnvelope:
        """Sign message envelope"""
        secret = self.key_store.get_secret(envelope.sender_id)
        if not secret:
            raise ValueError(f"No secret key for agent {envelope.sender_id}")
        
        # Generate nonce if not present
        if not envelope.nonce:
            envelope.nonce = secrets.token_hex(16)
        
        # Create signature payload
        payload = self._create_signature_payload(envelope)
        
        # Sign with HMAC-SHA256
        signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        envelope.signature = signature
        return envelope
    
    def _create_signature_payload(self, envelope: MessageEnvelope) -> str:
        """Create canonical payload for signing"""
        parts = [
            envelope.message_id,
            envelope.sender_id,
            envelope.receiver_id,
            envelope.message_type.value,
            str(envelope.timestamp),
            json.dumps(envelope.payload, sort_keys=True),
            envelope.nonce
        ]
        return '|'.join(parts)


class MessageVerifier:
    """Verifies message authenticity and detects impersonation"""
    
    def __init__(self, key_store: AgentKeyStore, max_age_seconds: int = 300):
        self.key_store = key_store
        self.max_age_seconds = max_age_seconds
        self.seen_nonces: Dict[str, float] = {}
    
    def verify_message(self, envelope: MessageEnvelope) -> Tuple[bool, str]:
        """Verify message signature and authenticity"""
        # Check if agent has registered keys
        if not self.key_store.has_keys(envelope.sender_id):
            return False, f"Unknown sender: {envelope.sender_id}"
        
        # Check timestamp (prevent replay attacks)
        current_time = time.time()
        if abs(current_time - envelope.timestamp) > self.max_age_seconds:
            return False, f"Message expired: age={abs(current_time - envelope.timestamp):.1f}s"
        
        # Check nonce (prevent replay attacks)
        if envelope.nonce in self.seen_nonces:
            return False, f"Duplicate nonce: {envelope.nonce}"
        
        # Verify signature
        public = self.key_store.get_public(envelope.sender_id)
        if not public:
            return False, f"No public key for {envelope.sender_id}"
        
        # Recreate expected signature
        secret = self.key_store.get_secret(envelope.sender_id)
        payload = self._create_signature_payload(envelope)
        expected_signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(envelope.signature, expected_signature):
            return False, "Invalid signature"
        
        # Record nonce
        self.seen_nonces[envelope.nonce] = current_time
        
        # Cleanup old nonces
        self._cleanup_nonces()
        
        return True, "Valid"
    
    def _create_signature_payload(self, envelope: MessageEnvelope) -> str:
        """Create canonical payload for verification"""
        parts = [
            envelope.message_id,
            envelope.sender_id,
            envelope.receiver_id,
            envelope.message_type.value,
            str(envelope.timestamp),
            json.dumps(envelope.payload, sort_keys=True),
            envelope.nonce
        ]
        return '|'.join(parts)
    
    def _cleanup_nonces(self):
        """Remove expired nonces"""
        current_time = time.time()
        expired = [
            nonce for nonce, timestamp in self.seen_nonces.items()
            if current_time - timestamp > self.max_age_seconds
        ]
        for nonce in expired:
            del self.seen_nonces[nonce]


class ImpersonationDetector:
    """Detects impersonation attempts in agent communication"""
    
    def __init__(self):
        self.agent_profiles: Dict[str, dict] = {}
        self.anomaly_log: list = []
    
    def register_agent_profile(self, agent_id: str, profile: dict):
        """Register expected agent behavior profile"""
        self.agent_profiles[agent_id] = {
            'agent_type': profile.get('agent_type', 'unknown'),
            'expected_senders': profile.get('expected_senders', []),
            'max_messages_per_minute': profile.get('max_messages_per_minute', 60),
            'message_history': [],
            'last_seen': 0
        }
    
    def check_impersonation(self, envelope: MessageEnvelope) -> Tuple[bool, str]:
        """Check for signs of impersonation"""
        sender_id = envelope.sender_id
        
        if sender_id not in self.agent_profiles:
            # Unknown agent - suspicious but not definitive
            return False, "Unknown agent profile"
        
        profile = self.agent_profiles[sender_id]
        current_time = time.time()
        
        # Check message frequency
        recent_messages = [
            t for t in profile['message_history']
            if current_time - t < 60
        ]
        
        if len(recent_messages) >= profile['max_messages_per_minute']:
            self.anomaly_log.append({
                'agent_id': sender_id,
                'type': 'rate_limit_exceeded',
                'timestamp': current_time,
                'count': len(recent_messages)
            })
            return True, f"Rate limit exceeded: {len(recent_messages)} messages/min"
        
        # Check for unusual sender patterns
        # (In production, this would analyze communication graph)
        
        # Record message
        profile['message_history'].append(current_time)
        profile['last_seen'] = current_time
        
        # Cleanup old messages
        profile['message_history'] = [
            t for t in profile['message_history']
            if current_time - t < 300
        ]
        
        return False, "No impersonation detected"
    
    def get_anomalies(self, agent_id: str = None) -> list:
        """Get detected anomalies"""
        if agent_id:
            return [a for a in self.anomaly_log if a['agent_id'] == agent_id]
        return self.anomaly_log.copy()


class MessageAuthenticationManager:
    """Main manager for message authentication"""
    
    def __init__(self):
        self.key_store = AgentKeyStore()
        self.signer = MessageSigner(self.key_store)
        self.verifier = MessageVerifier(self.key_store)
        self.impersonation_detector = ImpersonationDetector()
    
    def register_agent(self, agent_id: str, profile: dict = None) -> str:
        """Register agent and generate keys"""
        public, secret = self.key_store.generate_keypair(agent_id)
        
        if profile:
            self.impersonation_detector.register_agent_profile(agent_id, profile)
        
        return public
    
    def create_message(self, sender_id: str, receiver_id: str,
                       message_type: MessageType, payload: dict) -> MessageEnvelope:
        """Create and sign a new message"""
        import uuid
        
        envelope = MessageEnvelope(
            message_id=str(uuid.uuid4()),
            sender_id=sender_id,
            receiver_id=receiver_id,
            message_type=message_type,
            timestamp=time.time(),
            payload=payload
        )
        
        return self.signer.sign_message(envelope)
    
    def verify_message(self, envelope: MessageEnvelope) -> Tuple[bool, str]:
        """Verify message authenticity"""
        # Check signature
        is_valid, error = self.verifier.verify_message(envelope)
        if not is_valid:
            return False, error
        
        # Check for impersonation
        is_impersonation, reason = self.impersonation_detector.check_impersonation(envelope)
        if is_impersonation:
            return False, f"Impersonation detected: {reason}"
        
        return True, "Valid"
    
    def get_agent_anomalies(self, agent_id: str) -> list:
        """Get anomalies for specific agent"""
        return self.impersonation_detector.get_anomalies(agent_id)
    
    def export_auth_state(self) -> dict:
        """Export authentication state"""
        return {
            'registered_agents': list(self.key_store.keys.keys()),
            'anomaly_count': len(self.impersonation_detector.anomaly_log),
            'recent_anomalies': self.impersonation_detector.anomaly_log[-10:]
        }


# Global instance
auth_manager = MessageAuthenticationManager()


def register_agent(agent_id: str, profile: dict = None) -> str:
    """Convenience function to register agent"""
    return auth_manager.register_agent(agent_id, profile)


def create_message(sender_id: str, receiver_id: str,
                   message_type: MessageType, payload: dict) -> MessageEnvelope:
    """Convenience function to create signed message"""
    return auth_manager.create_message(sender_id, receiver_id, message_type, payload)


def verify_message(envelope: MessageEnvelope) -> Tuple[bool, str]:
    """Convenience function to verify message"""
    return auth_manager.verify_message(envelope)
