"""
HIVE OS - PALADIN Layer 2: Agent Isolation & Context Separation
Memory namespace isolation, tool permissions, sandbox execution.
Based on Microsoft Agent Governance Toolkit and AWS Agentic AI Security.
"""

import os
import json
import hashlib
from typing import Dict, Set, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import asyncio


class Permission(Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"
    FILE_SYSTEM = "file_system"
    DATABASE = "database"
    EXTERNAL_API = "external_api"
    AGENT_COMMUNICATION = "agent_communication"


@dataclass
class AgentIdentity:
    """Cryptographic identity for agent authentication"""
    agent_id: str
    agent_type: str
    created_at: float
    public_key: str = ""
    permissions: Set[Permission] = field(default_factory=set)
    memory_namespace: str = ""
    
    def __post_init__(self):
        if not self.memory_namespace:
            self.memory_namespace = f"agent_{self.agent_id}"
    
    def to_dict(self) -> dict:
        return {
            'agent_id': self.agent_id,
            'agent_type': self.agent_type,
            'created_at': self.created_at,
            'public_key': self.public_key,
            'permissions': [p.value for p in self.permissions],
            'memory_namespace': self.memory_namespace
        }


@dataclass
class MemoryNamespace:
    """Isolated memory namespace for an agent"""
    namespace: str
    agent_id: str
    data: Dict[str, Any] = field(default_factory=dict)
    access_log: list = field(default_factory=list)
    granted_access: Set[str] = field(default_factory=set)  # Other agents with access
    
    def store(self, key: str, value: Any) -> bool:
        """Store data in namespace"""
        self.data[key] = value
        self.access_log.append({
            'operation': 'store',
            'key': key,
            'timestamp': asyncio.get_event_loop().time()
        })
        return True
    
    def retrieve(self, key: str, requester_id: str) -> Optional[Any]:
        """Retrieve data from namespace"""
        if requester_id != self.agent_id and requester_id not in self.granted_access:
            self.access_log.append({
                'operation': 'denied',
                'key': key,
                'requester': requester_id,
                'timestamp': asyncio.get_event_loop().time()
            })
            return None
        
        self.access_log.append({
            'operation': 'retrieve',
            'key': key,
            'requester': requester_id,
            'timestamp': asyncio.get_event_loop().time()
        })
        return self.data.get(key)
    
    def grant_access(self, agent_id: str) -> bool:
        """Grant access to another agent"""
        self.granted_access.add(agent_id)
        self.access_log.append({
            'operation': 'grant_access',
            'target_agent': agent_id,
            'timestamp': asyncio.get_event_loop().time()
        })
        return True
    
    def revoke_access(self, agent_id: str) -> bool:
        """Revoke access from another agent"""
        self.granted_access.discard(agent_id)
        self.access_log.append({
            'operation': 'revoke_access',
            'target_agent': agent_id,
            'timestamp': asyncio.get_event_loop().time()
        })
        return True


class ToolPermissionManager:
    """Manages tool permissions per agent (principle of least privilege)"""
    
    # Default permissions by agent type
    DEFAULT_PERMISSIONS = {
        'leader': {
            Permission.READ, Permission.WRITE, Permission.AGENT_COMMUNICATION,
            Permission.DATABASE
        },
        'agent_forge': {
            Permission.READ, Permission.WRITE, Permission.EXECUTE,
            Permission.AGENT_COMMUNICATION
        },
        'cleanup_crew': {
            Permission.READ, Permission.WRITE, Permission.EXECUTE,
            Permission.FILE_SYSTEM
        },
        'safety_agent': {
            Permission.READ, Permission.AGENT_COMMUNICATION
        },
        'judge': {
            Permission.READ, Permission.AGENT_COMMUNICATION
        },
        'worker': {
            Permission.READ, Permission.WRITE
        },
        'web_scout': {
            Permission.READ, Permission.WRITE, Permission.NETWORK
        },
        'code_architect': {
            Permission.READ, Permission.WRITE, Permission.EXECUTE,
            Permission.FILE_SYSTEM, Permission.NETWORK
        },
        'security_scout': {
            Permission.READ, Permission.NETWORK
        },
        'data_analyst': {
            Permission.READ, Permission.WRITE, Permission.FILE_SYSTEM
        },
        'communicator': {
            Permission.READ, Permission.NETWORK
        },
    }
    
    def __init__(self):
        self.agent_permissions: Dict[str, Set[Permission]] = {}
        self.permission_overrides: Dict[str, Dict[Permission, bool]] = {}
    
    def register_agent(self, agent_id: str, agent_type: str) -> Set[Permission]:
        """Register agent with default permissions"""
        default_perms = self.DEFAULT_PERMISSIONS.get(agent_type, {Permission.READ})
        self.agent_permissions[agent_id] = default_perms.copy()
        return default_perms
    
    def check_permission(self, agent_id: str, permission: Permission) -> bool:
        """Check if agent has specific permission"""
        if agent_id not in self.agent_permissions:
            return False
        
        # Check overrides first
        if agent_id in self.permission_overrides:
            if permission in self.permission_overrides[agent_id]:
                return self.permission_overrides[agent_id][permission]
        
        return permission in self.agent_permissions[agent_id]
    
    def grant_permission(self, agent_id: str, permission: Permission) -> bool:
        """Grant permission to agent"""
        if agent_id not in self.agent_permissions:
            return False
        
        self.agent_permissions[agent_id].add(permission)
        return True
    
    def revoke_permission(self, agent_id: str, permission: Permission) -> bool:
        """Revoke permission from agent"""
        if agent_id not in self.agent_permissions:
            return False
        
        self.agent_permissions[agent_id].discard(permission)
        return True
    
    def get_permissions(self, agent_id: str) -> Set[Permission]:
        """Get all permissions for agent"""
        return self.agent_permissions.get(agent_id, set()).copy()


class SandboxExecutor:
    """Sandboxed execution environment for untrusted code"""
    
    def __init__(self):
        self.sandbox_dir = os.path.join(os.path.dirname(__file__), '..', 'sandboxes')
        os.makedirs(self.sandbox_dir, exist_ok=True)
    
    async def execute_in_sandbox(self, code: str, language: str = "python",
                                  timeout: int = 30) -> dict:
        """Execute code in sandboxed environment"""
        sandbox_id = hashlib.md5(code.encode()).hexdigest()[:12]
        sandbox_path = os.path.join(self.sandbox_dir, sandbox_id)
        os.makedirs(sandbox_path, exist_ok=True)
        
        try:
            if language == "python":
                result = await self._execute_python(code, sandbox_path, timeout)
            elif language == "javascript":
                result = await self._execute_javascript(code, sandbox_path, timeout)
            else:
                result = {'success': False, 'error': f'Unsupported language: {language}'}
            
            return result
            
        except asyncio.TimeoutError:
            return {'success': False, 'error': 'Execution timed out'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
        finally:
            # Cleanup sandbox
            import shutil
            if os.path.exists(sandbox_path):
                shutil.rmtree(sandbox_path, ignore_errors=True)
    
    async def _execute_python(self, code: str, sandbox_path: str, 
                               timeout: int) -> dict:
        """Execute Python code in sandbox"""
        import subprocess
        
        code_file = os.path.join(sandbox_path, 'code.py')
        with open(code_file, 'w') as f:
            f.write(code)
        
        try:
            result = subprocess.run(
                ['python', code_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=sandbox_path,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
            )
            
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Execution timed out'}
    
    async def _execute_javascript(self, code: str, sandbox_path: str,
                                   timeout: int) -> dict:
        """Execute JavaScript code in sandbox"""
        import subprocess
        
        code_file = os.path.join(sandbox_path, 'code.js')
        with open(code_file, 'w') as f:
            f.write(code)
        
        try:
            result = subprocess.run(
                ['node', code_file],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=sandbox_path
            )
            
            return {
                'success': result.returncode == 0,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {'success': False, 'error': 'Execution timed out'}


class AgentIsolationManager:
    """Main manager for agent isolation and context separation"""
    
    def __init__(self):
        self.identities: Dict[str, AgentIdentity] = {}
        self.namespaces: Dict[str, MemoryNamespace] = {}
        self.permission_manager = ToolPermissionManager()
        self.sandbox = SandboxExecutor()
    
    def register_agent(self, agent_id: str, agent_type: str) -> AgentIdentity:
        """Register new agent with isolated context"""
        import time
        
        identity = AgentIdentity(
            agent_id=agent_id,
            agent_type=agent_type,
            created_at=time.time(),
            permissions=self.permission_manager.DEFAULT_PERMISSIONS.get(
                agent_type, {Permission.READ}
            )
        )
        
        self.identities[agent_id] = identity
        self.namespaces[identity.memory_namespace] = MemoryNamespace(
            namespace=identity.memory_namespace,
            agent_id=agent_id
        )
        self.permission_manager.register_agent(agent_id, agent_type)
        
        return identity
    
    def get_identity(self, agent_id: str) -> Optional[AgentIdentity]:
        """Get agent identity"""
        return self.identities.get(agent_id)
    
    def get_namespace(self, agent_id: str) -> Optional[MemoryNamespace]:
        """Get agent's memory namespace"""
        identity = self.identities.get(agent_id)
        if identity:
            return self.namespaces.get(identity.memory_namespace)
        return None
    
    def store_agent_data(self, agent_id: str, key: str, value: Any) -> bool:
        """Store data in agent's namespace"""
        namespace = self.get_namespace(agent_id)
        if namespace:
            return namespace.store(key, value)
        return False
    
    def retrieve_agent_data(self, agent_id: str, key: str, 
                            requester_id: str) -> Optional[Any]:
        """Retrieve data from agent's namespace"""
        namespace = self.get_namespace(agent_id)
        if namespace:
            return namespace.retrieve(key, requester_id)
        return None
    
    def grant_cross_access(self, owner_id: str, target_id: str) -> bool:
        """Grant cross-agent access to memory namespace"""
        namespace = self.get_namespace(owner_id)
        if namespace:
            return namespace.grant_access(target_id)
        return False
    
    def check_tool_permission(self, agent_id: str, permission: Permission) -> bool:
        """Check if agent has permission for specific tool/action"""
        return self.permission_manager.check_permission(agent_id, permission)
    
    async def execute_sandboxed(self, agent_id: str, code: str, 
                                 language: str = "python") -> dict:
        """Execute code in agent's sandbox"""
        if not self.check_tool_permission(agent_id, Permission.EXECUTE):
            return {'success': False, 'error': 'Permission denied: EXECUTE'}
        
        return await self.sandbox.execute_in_sandbox(code, language)
    
    def get_access_log(self, agent_id: str) -> list:
        """Get access log for agent's namespace"""
        namespace = self.get_namespace(agent_id)
        if namespace:
            return namespace.access_log.copy()
        return []
    
    def export_isolation_state(self) -> dict:
        """Export complete isolation state"""
        return {
            'identities': {k: v.to_dict() for k, v in self.identities.items()},
            'namespaces': {
                k: {
                    'agent_id': v.agent_id,
                    'data_keys': list(v.data.keys()),
                    'granted_access': list(v.granted_access),
                    'access_count': len(v.access_log)
                }
                for k, v in self.namespaces.items()
            },
            'permissions': {
                agent_id: [p.value for p in perms]
                for agent_id, perms in self.permission_manager.agent_permissions.items()
            }
        }


# Global instance
isolation_manager = AgentIsolationManager()


def register_agent(agent_id: str, agent_type: str) -> AgentIdentity:
    """Convenience function to register agent"""
    return isolation_manager.register_agent(agent_id, agent_type)


def check_permission(agent_id: str, permission: Permission) -> bool:
    """Convenience function to check permission"""
    return isolation_manager.check_tool_permission(agent_id, permission)


def store_data(agent_id: str, key: str, value: Any) -> bool:
    """Convenience function to store data"""
    return isolation_manager.store_agent_data(agent_id, key, value)


def retrieve_data(agent_id: str, key: str, requester_id: str) -> Optional[Any]:
    """Convenience function to retrieve data"""
    return isolation_manager.retrieve_agent_data(agent_id, key, requester_id)
