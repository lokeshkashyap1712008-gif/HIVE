"""
HIVE OS - Security Scout Agent
OWASP Top 10 scanning, SQL injection, XSS, port scanning, header checks.
"""

import re
import socket
import subprocess
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class Vulnerability:
    severity: str  # critical, high, medium, low, info
    category: str
    description: str
    file_path: str = ""
    line_number: int = 0
    recommendation: str = ""


class SecurityScout:
    """Security analysis agent for OWASP Top 10 and common vulnerabilities"""
    
    # OWASP patterns
    SQL_INJECTION_PATTERNS = [
        r'(?i)(SELECT|INSERT|UPDATE|DELETE|DROP)\s+.*\s+FROM\s+.*\s+WHERE\s+.*["\']?\s*\+',
        r'(?i)execute\s*\(\s*["\'].*\+',
        r'(?i)cursor\.execute\s*\(\s*["\'].*%',
        r'(?i)f["\'].*SELECT.*FROM.*WHERE',
    ]
    
    XSS_PATTERNS = [
        r'(?i)innerHTML\s*=',
        r'(?i)document\.write\s*\(',
        r'(?i)\.html\s*\(\s*['""][^""]*\+',
        r'(?i)v-html\s*=',
        r'(?i)dangerouslySetInnerHTML',
    ]
    
    HARDCODED_SECRET_PATTERNS = [
        r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\'][a-zA-Z0-9\-_]{20,}["\']',
        r'(?i)(secret|password|passwd|pwd)\s*[:=]\s*["\'][^\s"\']{6,}["\']',
        r'(?i)(token|auth)\s*[:=]\s*["\'][a-zA-Z0-9\-_\.]{20,}["\']',
        r'(?i)Bearer\s+[a-zA-Z0-9\-_\.]{20,}',
        r'-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----',
    ]
    
    INSECURE_DESERIALIZATION = [
        r'(?i)pickle\.loads?\s*\(',
        r'(?i)yaml\.load\s*\([^)]*\)',
        r'(?i)marshal\.loads?\s*\(',
        r'(?i)eval\s*\(',
        r'(?i)exec\s*\(',
    ]
    
    def __init__(self):
        self.findings: List[Vulnerability] = []
    
    async def run(self, task: str) -> dict:
        """Main entry point for security analysis"""
        self.findings = []
        
        # Parse task for target
        target = self._extract_target(task)
        
        if target.endswith('.py') or target.endswith('.js') or target.endswith('.html'):
            await self._scan_file(target)
        elif ':' in target:
            await self._scan_port(target)
        else:
            await self._scan_directory(target)
        
        return self._compile_results()
    
    def _extract_target(self, task: str) -> str:
        """Extract target from task description"""
        # Try to find file path
        path_match = re.search(r'[\w/\\\.]+\.(py|js|html|json|yaml|yml)', task)
        if path_match:
            return path_match.group(0)
        
        # Try to find directory
        dir_match = re.search(r'(?:directory|folder|path)\s+[:=]?\s*([^\s]+)', task, re.IGNORECASE)
        if dir_match:
            return dir_match.group(1)
        
        # Default to current directory
        return "."
    
    async def _scan_file(self, file_path: str):
        """Scan a single file for vulnerabilities"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                lines = content.split('\n')
            
            # Check for SQL injection
            for i, line in enumerate(lines, 1):
                for pattern in self.SQL_INJECTION_PATTERNS:
                    if re.search(pattern, line):
                        self.findings.append(Vulnerability(
                            severity="high",
                            category="A03:2021 - Injection",
                            description="Potential SQL injection vulnerability",
                            file_path=file_path,
                            line_number=i,
                            recommendation="Use parameterized queries instead of string concatenation"
                        ))
                        break
            
            # Check for XSS
            for i, line in enumerate(lines, 1):
                for pattern in self.XSS_PATTERNS:
                    if re.search(pattern, line):
                        self.findings.append(Vulnerability(
                            severity="high",
                            category="A03:2021 - Injection",
                            description="Potential Cross-Site Scripting (XSS) vulnerability",
                            file_path=file_path,
                            line_number=i,
                            recommendation="Sanitize user input and use content security policy"
                        ))
                        break
            
            # Check for hardcoded secrets
            for i, line in enumerate(lines, 1):
                for pattern in self.HARDCODED_SECRET_PATTERNS:
                    if re.search(pattern, line):
                        self.findings.append(Vulnerability(
                            severity="critical",
                            category="A02:2021 - Cryptographic Failures",
                            description="Hardcoded secret or API key detected",
                            file_path=file_path,
                            line_number=i,
                            recommendation="Move secrets to environment variables or secure vault"
                        ))
                        break
            
            # Check for insecure deserialization
            for i, line in enumerate(lines, 1):
                for pattern in self.INSECURE_DESERIALIZATION:
                    if re.search(pattern, line):
                        self.findings.append(Vulnerability(
                            severity="high",
                            category="A08:2021 - Software and Data Integrity Failures",
                            description="Potential insecure deserialization",
                            file_path=file_path,
                            line_number=i,
                            recommendation="Avoid deserializing untrusted data; use safe alternatives"
                        ))
                        break
            
            # Check for missing security headers in HTML
            if file_path.endswith('.html'):
                self._check_security_headers(content, file_path)
            
        except Exception as e:
            self.findings.append(Vulnerability(
                severity="info",
                category="Scan Error",
                description=f"Could not scan file: {str(e)}"
            ))
    
    def _check_security_headers(self, content: str, file_path: str):
        """Check HTML for security headers"""
        required_headers = [
            'Content-Security-Policy',
            'X-Content-Type-Options',
            'X-Frame-Options',
            'X-XSS-Protection',
        ]
        
        for header in required_headers:
            if header.lower() not in content.lower():
                self.findings.append(Vulnerability(
                    severity="medium",
                    category="A05:2021 - Security Misconfiguration",
                    description=f"Missing security header: {header}",
                    file_path=file_path,
                    recommendation=f"Add {header} header to improve security"
                ))
    
    async def _scan_port(self, target: str):
        """Scan ports on a target"""
        host, port_range = target.split(':')
        ports = self._parse_port_range(port_range)
        
        open_ports = []
        for port in ports:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                if result == 0:
                    open_ports.append(port)
                sock.close()
            except:
                pass
        
        if open_ports:
            self.findings.append(Vulnerability(
                severity="medium",
                category="A05:2021 - Security Misconfiguration",
                description=f"Open ports detected: {open_ports}",
                recommendation="Review and close unnecessary ports"
            ))
        
        # Check for common insecure ports
        insecure_ports = {21: 'FTP', 23: 'Telnet', 25: 'SMTP', 135: 'RPC', 445: 'SMB'}
        for port in open_ports:
            if port in insecure_ports:
                self.findings.append(Vulnerability(
                    severity="high",
                    category="A05:2021 - Security Misconfiguration",
                    description=f"Insecure service running: {insecure_ports[port]} on port {port}",
                    recommendation=f"Disable {insecure_ports[port]} or replace with secure alternative"
                ))
    
    def _parse_port_range(self, port_range: str) -> List[int]:
        """Parse port range string like '80,443,8000-8100'"""
        ports = []
        for part in port_range.split(','):
            if '-' in part:
                start, end = part.split('-')
                ports.extend(range(int(start), int(end) + 1))
            else:
                ports.append(int(part))
        return ports
    
    async def _scan_directory(self, directory: str):
        """Scan a directory for vulnerabilities"""
        import os
        
        if not os.path.exists(directory):
            self.findings.append(Vulnerability(
                severity="info",
                category="Scan Error",
                description=f"Directory not found: {directory}"
            ))
            return
        
        for root, dirs, files in os.walk(directory):
            # Skip hidden and common non-code directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv']]
            
            for file in files:
                if file.endswith(('.py', '.js', '.ts', '.html', '.yaml', '.yml', '.json')):
                    file_path = os.path.join(root, file)
                    await self._scan_file(file_path)
    
    def _compile_results(self) -> dict:
        """Compile scan results"""
        severity_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0, 'info': 0}
        for finding in self.findings:
            severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1
        
        return {
            'total_findings': len(self.findings),
            'severity_summary': severity_counts,
            'findings': [
                {
                    'severity': f.severity,
                    'category': f.category,
                    'description': f.description,
                    'file_path': f.file_path,
                    'line_number': f.line_number,
                    'recommendation': f.recommendation
                }
                for f in self.findings
            ],
            'risk_level': 'critical' if severity_counts['critical'] > 0 else
                         'high' if severity_counts['high'] > 0 else
                         'medium' if severity_counts['medium'] > 0 else
                         'low' if severity_counts['low'] > 0 else 'info'
        }
    
    def get_owasp_report(self) -> dict:
        """Get OWASP Top 10 categorized report"""
        owasp_categories = {}
        for finding in self.findings:
            cat = finding.category
            if cat not in owasp_categories:
                owasp_categories[cat] = []
            owasp_categories[cat].append(finding)
        
        return {
            'categories_found': len(owasp_categories),
            'categories': {
                cat: {
                    'count': len(findings),
                    'findings': [
                        {
                            'severity': f.severity,
                            'description': f.description,
                            'file_path': f.file_path,
                            'line_number': f.line_number
                        }
                        for f in findings
                    ]
                }
                for cat, findings in owasp_categories.items()
            }
        }
