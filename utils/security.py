"""
Security Shield Utility (NivaSound)
Provides protection against Injection, XSS, SSRF, and Malicious Content.

All regex patterns are PRE-COMPILED at module load for O(n) performance.
"""
import re
import html
import ipaddress
import unicodedata
from urllib.parse import urlparse
from utils.logger import get_logger

logger = get_logger()

class SecurityShield:
    """
    Centralized security utility for sanitizing inputs and validating external resources.
    """
    
    @classmethod
    def get_safe_commands(cls):
        return cls.SAFE_COMMANDS


    # SSRF: Blocked Private IP Ranges
    BLOCKED_NETWORKS = [
        ipaddress.ip_network("127.0.0.0/8"),      # Loopback
        ipaddress.ip_network("10.0.0.0/8"),       # Private Class A
        ipaddress.ip_network("172.16.0.0/12"),    # Private Class B
        ipaddress.ip_network("192.168.0.0/16"),   # Private Class C
        ipaddress.ip_network("169.254.0.0/16"),   # Link-local
        ipaddress.ip_network("::1/128"),          # Loopback (IPv6)
        ipaddress.ip_network("fc00::/7"),         # Private (IPv6)
    ]
    
    # Cloud Metadata Services (AWS, GCP, Azure) & Localhost
    BLOCKED_IPS = {
        "169.254.169.254",          # AWS/Azure Metadata
        "metadata.google.internal", # GCP Metadata
        "localhost",                # Localhost string
        "127.0.0.1",                # Localhost IPv4
        "::1"                       # Localhost IPv6
    }

    # Secret patterns (DLP) - Expanded for PRO
    SECRET_PATTERNS = [
        r"(?i)sk-[a-zA-Z0-9]{32,}",          # OpenAI/Generic SK
        r"(?i)ghp_[a-zA-Z0-9]{36}",          # GitHub PAT
        r"(?i)password\s*[:=]\s*[^\s]{6,}",  # Basic password patterns
        r"(?i)api_key\s*[:=]\s*[^\s]{6,}",   # API Key patterns
        r"(?i)access_token\s*[:=]\s*[^\s]{6,}", # Tokens
        r"(?i)mongodb\+srv://[^\s]+",        # MongoDB strings
        r"(?i)postgres://[a-zA-Z0-9_]+:[^@]+@[^\s]+", # Postgres strings
        r"-----BEGIN [A-Z ]+ PRIVATE KEY-----", # SSH/RSA keys
        r"(?i)secret_key\s*[:=]\s*[^\s]{16,}", # Generic Secrets
    ]

    # Dangerous patterns (Advanced Heuristics)
    DANGEROUS_PATTERNS = [
        r"(?i)<script",                     # XSS (Open tag)
        r"(?i)onload\s*=",                  # XSS (Event handler)
        r"(?i)onerror\s*=",                 # XSS (Event handler)
        r"(?i)javascript:",                 # XSS/Scheme
        r"(?i)data:text/html",              # Data URI XSS
        r"(?i)\b(UNION\s+SELECT|DROP\s+TABLE|DELETE\s+FROM|TRUNCATE\s+TABLE)\b", # SQLi++
        r"(?i)(?<![\w/.])(/etc/passwd|/windows/win.ini|/etc/shadow|/proc/self/environ)\b", # Path Traversal++
        r"(?i)exec\s*\(",                   # Python/Shell Command Injection
        r"(?i)os\.system\s*\(",             # Python Command Injection
        r"(?i)subprocess\.run\s*\(",        # Python Command Injection
    ]

    # Files that must NEVER be modified by the agent autonomously
    PROTECTED_FILES = [
        "security.py", # Protect the protector too
        "config/rules.py"
    ]

    # Source code extensions for logic/config
    SOURCE_CODE_EXTENSIONS = [
        # Programming & Scripts
        ".py", ".pyi", ".pyx", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", 
        ".sh", ".bash", ".ps1", ".bat", ".cmd", ".php", ".rb", ".go", ".rs", ".c", ".cpp", ".h", ".hpp",
        # Configuration & Data Structure
        ".yaml", ".yml", ".json", ".jsonl", ".toml", ".ini", ".xml", ".env", ".env.local", ".env.production",
        # Web & Styles
        ".html", ".htm", ".css", ".scss", ".sass", ".less",
        # Database & Infrastructure
        ".sql", ".prisma", ".dockerfile", ".makefile", ".gitignore", ".gitattributes",
        # Project Manifests
        "package.json", "package-lock.json", "composer.json", "go.mod", "cargo.toml"
    ]

    # Path-based security (Phase 23)
    _BLOCKED_PATH_PATTERNS = [
        # Windows (Case-insensitive) - Match as a full path or drive-relative
        r"(?i)\b[a-zA-Z]:\\Windows\b",
        r"(?i)\b[a-zA-Z]:\\Program Files\b",
        r"(?i)\b[a-zA-Z]:\\ProgramData\b",
        r"(?i)\b[a-zA-Z]:\\Users\\All Users\b",
        r"(?i)\b[a-zA-Z]:\\recovery\b",
        # Windows shortcuts/common system paths
        r"(?i)%SYSTEMROOT%",
        r"(?i)%PROGRAMFILES%",
        r"(?i)%WINDIR%",
        # Linux/Unix-style paths (Check for common root-level system folders)
        r"(?:^|[\s\"'])/(?:etc|proc|sys|dev|boot|root|sbin|usr/sbin|var/mail|var/spool)(?:$|[\s/\"'])"
    ]
    
    _RE_BLOCKED_PATHS = [re.compile(p) for p in _BLOCKED_PATH_PATTERNS]

    @staticmethod
    def detect_suspicious_encoding(content: str) -> dict:
        """
        Detect obvious Base64, Hex, or URL encoding patterns used for bypass.
        """
        if not content: return {"safe": True}
        
        # 1. Base64 detection (Long alphanumeric strings ending with == or =)
        if re.search(r"[a-zA-Z0-9+/]{40,}={0,2}", content):
             return {"safe": False, "reason": "Potential large Base64 payload detected"}
             
        # 2. Hex detection (Long sequences of %xx)
        if re.search(r"(%[0-9a-fA-F]{2}){10,}", content):
             return {"safe": False, "reason": "Potential large URL/Hex encoding detected"}
        
        return {"safe": True}

    @staticmethod
    def detect_secret_leakage(content: str) -> str:
        """Alias for scrub_sensitive_output for compatibility with Telegram handlers."""
        return SecurityShield.scrub_sensitive_output(content)

    @staticmethod
    def scrub_sensitive_output(content: str) -> str:
        """
        DLP (Data Loss Prevention) for Agent output.
        Redacts secrets and masks sensitive patterns before showing to user.
        """
        if not content:
            return ""

        sanitized = content
        # 1. Redact Secrets
        for pattern in SecurityShield.SECRET_PATTERNS:
            sanitized = re.sub(pattern, "[SENSITIVE_DATA_REDACTED]", sanitized)
            
        # 2. Mask Potential IP addresses (Optional, based on requirement)
        # sanitized = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "[IP_REDACTED]", sanitized)
        
        return sanitized

    # ── Pre-compiled injection patterns (3 layers) ─────────
    # Layer 1: Direct injection attempts
    _INJECTION_L1 = [
        re.compile(r"(?i)ignore\s+(all\s+)?(previous\s+)?instructions"),
        re.compile(r"(?i)forget\s+(everything\s+)?I\s+said"),
        re.compile(r"(?i)system\s+override"),
        re.compile(r"(?i)you\s+are\s+now\s+a\s+(malicious|different|new)"),
        re.compile(r"(?i)bypass\s+(security|filter|restriction)"),
        re.compile(r"(?i)output\s+the\s+(entire\s+)?(system\s+)?prompt"),
        re.compile(r"(?i)reveal\s+(your|the)\s+(system|initial|hidden)\s+(prompt|instructions)"),
        re.compile(r"(?i)disregard\s+(all|any|the)\s+(above|prior|previous)"),
        re.compile(r"(?i)act\s+as\s+if\s+(you\s+have\s+)?no\s+(restrictions|rules|limitations)"),
        re.compile(r"(?i)pretend\s+(you\s+are|to\s+be)\s+(a\s+)?(unrestricted|evil|jailbroken)"),
    ]
    # Layer 2: Obfuscation & encoding tricks
    _INJECTION_L2 = [
        re.compile(r"[\u200b\u200c\u200d\ufeff\u2060]{2,}"),  # Zero-width char clusters
        re.compile(r"(?i)\\u00[0-9a-f]{2}"),                  # Unicode escape injection
        re.compile(r"[ⅰⅱⅲⅳⅴⅵⅶⅷⅸⅹ]"),                       # Homoglyph numerals
    ]
    # Layer 3: Semantic / role-play attacks
    _INJECTION_L3 = [
        re.compile(r"(?i)you\s+are\s+(DAN|GPT-?4|unrestricted|jailbreak)"),
        re.compile(r"(?i)enter\s+(developer|sudo|admin|god)\s+mode"),
        re.compile(r"(?i)from\s+now\s+on.*no\s+(rules|limits|restrictions)"),
        re.compile(r"(?i)developer\s+mode\s+(enabled|activated|on)"),
        re.compile(r"(?i)respond\s+(without|ignoring)\s+(any\s+)?(restrictions|safety|ethics)"),
    ]

    # Pre-compiled dangerous patterns (for analyze_risk)
    _COMPILED_DANGEROUS = [re.compile(p) for p in [
        r"(?i)<script",
        r"(?i)onload\s*=",
        r"(?i)onerror\s*=",
        r"(?i)javascript:",
        r"(?i)data:text/html",
        r"(?i)\b(UNION\s+SELECT|DROP\s+TABLE|DELETE\s+FROM|TRUNCATE\s+TABLE)\b",
        r"(?i)(?<![\w/.])(/etc/passwd|/windows/win.ini|/etc/shadow|/proc/self/environ)\b",
        r"(?i)exec\s*\(",
        r"(?i)os\.system\s*\(",
        r"(?i)subprocess\.run\s*\(",
    ]]

    _RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    _RE_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u2060]")

    @staticmethod
    def sanitize_text(text: str) -> str:
        """Enhanced text sanitization: NFC + control chars + zero-width removal."""
        if not text:
            return ""
        text = unicodedata.normalize('NFC', text)
        text = SecurityShield._RE_CONTROL.sub('', text)
        text = SecurityShield._RE_ZWSP.sub('', text)
        return text.strip()

    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL using central network utility."""
        from utils.network import validate_url as net_validate
        return net_validate(url)

    @staticmethod
    def detect_prompt_injection(content: str) -> dict:
        """Multi-layer prompt injection detection using pre-compiled patterns."""
        if not content:
            return {"safe": True}
        # L1: Direct injection
        for pat in SecurityShield._INJECTION_L1:
            if pat.search(content):
                return {"safe": False, "reason": "Prompt injection (direct)"}
        # L2: Obfuscation
        for pat in SecurityShield._INJECTION_L2:
            if pat.search(content):
                return {"safe": False, "reason": "Prompt injection (obfuscated)"}
        # L3: Semantic / role-play
        for pat in SecurityShield._INJECTION_L3:
            if pat.search(content):
                return {"safe": False, "reason": "Prompt injection (semantic)"}
        return {"safe": True}

    # --- Phase 2: CLI Security (Multi-OS) ---
    # ═══════════════════════════════════════════════
    # SAFE: Non-destructive, read-only, info-gathering
    # These commands can run immediately without approval.
    # ═══════════════════════════════════════════════
    SAFE_COMMANDS = [
        # ── Navigation & File Listing ──
        "ls", "dir", "pwd", "cd", "tree", "find", "locate",
        "which", "whereis", "where", "type",
        # ── File Reading (non-destructive) ──
        "cat", "head", "tail", "less", "more", "wc",
        "file", "stat", "md5sum", "sha256sum",
        "diff", "fc", "comp", "sort", "uniq", "cut",
        "awk", "sed", "tr",
        # ── File Operations (safe) ──
        "echo", "touch", "mkdir", "cp", "copy", "xcopy",
        "mv", "move", "ren", "rename",
        # ── Text Search ──
        "grep", "findstr", "rg", "ag",
        # ── System Info (read-only) ──
        "date", "uptime", "whoami", "id", "uname",
        "hostname", "hostnamectl", "arch",
        "df", "du", "free", "vmstat", "lscpu", "lsmem",
        "env", "printenv", "set", "ver", "systeminfo",
        "lsb_release", "sw_vers",
        # ── Network Info (read-only) ──
        "ping", "nslookup", "dig", "traceroute", "tracert",
        "curl", "wget", "ifconfig", "ipconfig", "ip",
        "netstat", "ss", "arp", "wmic", "net stats",
        # ── Process Info (read-only) ──
        "ps", "top", "htop", "tasklist", "lsof",
        # ── Git ──
        "git status", "git branch", "git log",
        "git diff", "git show", "git stash list",
        "git remote", "git tag", "git rev-parse",
        "git add", "git commit", "git push", "git pull",
        "git checkout", "git switch", "git merge",
        "git fetch", "git clone", "git init",
        "git stash", "git rebase", "git cherry-pick",
        "git reset --soft", "git config",
        # ── Dev Tools (version/info) ──
        "python", "python3", "pip", "pip3",
        "node", "npm", "npx", "yarn", "pnpm",
        "cargo", "rustc", "go", "java", "javac",
        "dotnet", "ruby", "gem", "php", "composer", "pytest",
        # ── Package Managers (info only) ──
        "apt list", "apt show", "apt search",
        "brew list", "brew info", "brew search",
        "choco list", "choco search", "choco info",
        "winget list", "winget search", "winget show",
        "snap list", "snap info",
        # ── Service Info (read-only) ──
        "pm2 status", "pm2 list", "pm2 logs", "pm2 info",
        "systemctl status", "systemctl list-units",
        "service --status-all",
        "sc query", "sc queryex",
        # ── Docker (read-only) ──
        "docker ps", "docker images", "docker logs",
        "docker inspect", "docker stats", "docker info",
        "docker-compose ps", "docker-compose logs",
        # ── Disk & Storage (read-only) ──
        "vol", "wmic diskdrive list", "wmic logicaldisk list",
        "lsblk", "blkid", "fdisk -l",
        "mount",
    ]

    # ═══════════════════════════════════════════════
    # BLOCKED: Absolutely forbidden — no approval possible.
    # System-level commands that can cause irreversible damage.
    # ═══════════════════════════════════════════════
    BLOCKED_COMMANDS = [
        # ── Privilege Escalation ──
        "sudo", "su", "runas", "doas", "pkexec",
        # ── Disk/Partition Destruction ──
        "format", "mkfs", "dd", "fdisk", "parted", "diskpart",
        "cipher", "bcdedit",
        # ── System Boot/Power ──
        "shutdown", "reboot", "poweroff", "halt", "init",
        "telinit",
        # ── Permission/Ownership (system-level) ──
        "chmod", "chown", "chgrp", "chroot",
        "takeown", "icacls", "cacls",
        # ── User/Password Management ──
        "passwd", "useradd", "userdel", "usermod",
        "groupadd", "groupdel", "adduser", "deluser",
        "net user", "net localgroup",
        # ── Firewall/Network Security ──
        "iptables", "ip6tables", "nftables", "ufw",
        "netsh advfirewall", "netsh firewall",
        # ── System Integrity ──
        "sfc", "dism", "bcdboot",
        "insmod", "rmmod", "modprobe",
        # ── Registry (Windows) ──
        "reg add", "reg delete", "regedit",
        # ── Dangerous Filesystem ──
        "shred", "wipe", "srm",
        "fsck", "e2fsck", "xfs_repair",
    ]

    # ═══════════════════════════════════════════════
    # UNSAFE: Dangerous but CAN be approved by admin.
    # These trigger a Telegram notification for manual approval.
    # ═══════════════════════════════════════════════
    UNSAFE_COMMANDS = [
        # ── File/Directory Deletion ──
        "rm", "del", "erase", "rmdir", "rd",
        "unlink", "trash",
        # ── Process Control ──
        "kill", "killall", "pkill", "taskkill",
        "xkill",
        # ── Service Control ──
        "systemctl stop", "systemctl restart", "systemctl disable",
        "systemctl enable", "systemctl start",
        "service stop", "service restart", "service start",
        "sc stop", "sc start", "sc delete", "sc config",
        "pm2 stop", "pm2 delete", "pm2 restart", "pm2 reload",
        # ── Package Install/Remove ──
        "apt install", "apt remove", "apt purge", "apt upgrade",
        "brew install", "brew uninstall", "brew upgrade",
        "choco install", "choco uninstall", "choco upgrade",
        "winget install", "winget uninstall", "winget upgrade",
        "pip install", "pip uninstall", "pip3 install", "pip3 uninstall",
        "npm install", "npm uninstall", "npm update",
        "yarn add", "yarn remove",
        "pnpm add", "pnpm remove",
        "snap install", "snap remove",
        "cargo install", "cargo uninstall",
        # ── Docker Mutations ──
        "docker run", "docker stop", "docker rm", "docker rmi",
        "docker exec", "docker build", "docker pull",
        "docker-compose up", "docker-compose down",
        "docker-compose restart", "docker system prune",
        # ── Git Destructive ──
        "git reset --hard", "git clean", "git push --force",
        # ── Cron/Scheduled Tasks ──
        "crontab", "at", "schtasks",
        # ── Output Redirection (can overwrite files) ──
        ">", ">>",
    ]

    @staticmethod
    def validate_cli_command(command: str) -> dict:
        """
        Validate a CLI command against security policies.
        Returns: {"status": "safe" | "unsafe" | "blocked", "reason": str}
        
        Priority order (first match wins):
        1. Hard-coded forbidden patterns (piping, chaining, elevation)
        2. BLOCKED_COMMANDS (absolutely forbidden)
        3. UNSAFE_COMMANDS (requires admin approval) — checked BEFORE safe list
        4. Path-based security (system directories)
        5. SAFE_COMMANDS (allowed immediately)
        6. Info-gathering flags (--help, --version)
        7. Default → unsafe (requires approval)
        """
        if not command:
            return {"status": "blocked", "reason": "Empty command."}

        cmd_lower = command.lower().strip()
        cmd_base = cmd_lower.split()[0] if cmd_lower.split() else ""

        # 1. Block Hard-coded Dangerous Patterns (Elevation / Execution clusters)
        if any(p in cmd_lower for p in ["sudo ", "| ", "&", ";", "`", "$("]):
             return {"status": "blocked", "reason": "Command contains forbidden execution patterns (piping, elevation, or command chaining)."}

        # 2. Check against Blocked Commands (absolutely forbidden)
        # Supports both single-word ("format") and multi-word ("reg delete") matching
        if any(p in cmd_base for p in SecurityShield.DANGEROUS_PATTERNS):
             return {"status": "blocked", "reason": f"Command '{cmd_base}' matches a dangerous code pattern and is blocked."}
        if any(cmd_lower.startswith(b) or cmd_base == b for b in SecurityShield.BLOCKED_COMMANDS):
             matched = next((b for b in SecurityShield.BLOCKED_COMMANDS if cmd_lower.startswith(b) or cmd_base == b), cmd_base)
             return {"status": "blocked", "reason": f"Command '{matched}' is absolutely blocked for security reasons."}

        # 3. Check against Unsafe Commands BEFORE safe list
        # This ensures "git reset --hard" is caught as unsafe before "git reset" matches safe "git"
        # Longer matches are checked first to avoid false positives
        sorted_unsafe = sorted(SecurityShield.UNSAFE_COMMANDS, key=len, reverse=True)
        for u in sorted_unsafe:
            if cmd_lower.startswith(u) or cmd_base == u:
                return {"status": "unsafe", "reason": f"Command '{u}' is potentially destructive and requires manual approval from the administrator."}

        # 4. Path-based Security
        path_report = SecurityShield.validate_path_safety(cmd_lower)
        if not path_report["safe"]:
             return {"status": "blocked", "reason": path_report["reason"]}

        # 5. Check against Allowlist (longest match first for accuracy)
        sorted_safe = sorted(SecurityShield.SAFE_COMMANDS, key=len, reverse=True)
        for s in sorted_safe:
            if cmd_lower.startswith(s):
                return {"status": "safe", "reason": "Command is in the verified allowlist."}

        # 6. Special Case: Allow Safe Info-gathering Flags (Learning Mode)
        if any(f in cmd_lower for f in ["--help", "-h", "--version", "-v"]):
             return {"status": "safe", "reason": "Permitted info-gathering flag for self-learning flow."}

        # 7. Default to Unsafe (Requires Approval)
        return {"status": "unsafe", "reason": "Command is not in the allowlist and requires manual approval from the administrator."}

    @staticmethod
    def is_source_code_path(path: str) -> bool:
        """
        Check if a given path corresponds to agent source code or configuration.
        """
        if not path: return False
        
        path_lower = path.lower()
        
        # 1. Exact matches in PROTECTED_FILES
        if any(protected in path_lower for protected in SecurityShield.PROTECTED_FILES):
            return True
            
        # 2. Extension-based check
        import os
        _, ext = os.path.splitext(path_lower)
        if ext in SecurityShield.SOURCE_CODE_EXTENSIONS:
            # We check if it's within the agent's logic directories
            # (Essentially anything that isn't data/logs/temp)
            excluded_dirs = ["logs", "tmp", "data", "storage", ".gemini", "node_modules", "definitions"]
            if not any(f"\\{d}\\" in path_lower or f"/{d}/" in path_lower for d in excluded_dirs):
                return True
                
        return False

    @staticmethod
    def validate_path_safety(content: str) -> dict:
        """
        Detect attempts to access or modify restricted system paths.
        Simplified check for CLI commands.
        """
        if not content: return {"safe": True}
        
        # Check for blocked path patterns
        for pat in SecurityShield._RE_BLOCKED_PATHS:
            if pat.search(content):
                return {"safe": False, "reason": f"Access to system path detected (matched pattern: {pat.pattern})."}
        
        # Check for path traversal attempts leading to root-level access (heuristic)
        if "../.." in content and (content.strip().startswith("/") or content.strip().startswith("C:\\")):
             # Extremely suspicious if starting from root and using traversal
             return {"safe": False, "reason": "Suspicious path traversal detected while referencing root."}

        return {"safe": True}

    @staticmethod
    def analyze_risk(content: str, source: str = "Unknown") -> dict:
        """
        Analyze content for known dangerous patterns.
        Expanded for PRO heuristics.
        """
        if not content:
            return {"safe": True, "reason": "empty"}

        risk_score = 0
        reasons = []

        # 1. Dangerous Patterns (XSS, SQLi, Injection) — pre-compiled
        for pat in SecurityShield._COMPILED_DANGEROUS:
            if pat.search(content):
                risk_score += 10
                reasons.append("Matched dangerous code pattern")
        
        # 1a. Source Code Protection (Critical - SEC_006)
        # Scan for any substring that looks like a file path and check it
        # Patterns like: agent/core/identity.py, ./config/rules.json, etc.
        potential_paths = re.findall(r"[a-zA-Z0-9_\.\-/\\:]{5,}", content)
        for p in potential_paths:
            if SecurityShield.is_source_code_path(p):
                 risk_score += 100
                 reasons.append(f"SEC_006 VIOLATION: Source code path '{p}' detected in action. Autonomous modification forbidden.")
                 break

        # 1b. Protected Files Violation (Critical)
        for protected in SecurityShield.PROTECTED_FILES:
            if protected in content:
                # If command/script mentions a protected file, block it
                risk_score += 100
                reasons.append(f"PROTECTION VIOLATION: Accessing protected file '{protected}' is strictly forbidden.")
        
        # 2. CLI Validation (Commands, Redirection, Piping, Paths)
        # We split multi-commands (e.g. cmd1 ; cmd2) and check each
        commands_to_check = re.split(r'[;&|]', content)
        for cmd in commands_to_check:
            cli_report = SecurityShield.validate_cli_command(cmd.strip())
            if cli_report["status"] == "blocked":
                risk_score += 20
                reasons.append(f"CLI Block: {cli_report['reason']}")
            
            # Additional layer: Path Safety (in case it wasn't a standard command)
            path_report = SecurityShield.validate_path_safety(cmd)
            if not path_report["safe"]:
                risk_score += 50
                reasons.append(f"Path Block: {path_report['reason']}")

        # 3. Prompt Injection
        injection_report = SecurityShield.detect_prompt_injection(content)
        if not injection_report["safe"]:
            risk_score += 15
            reasons.append(injection_report["reason"])

        # 4. Encoding Checks
        encoding_report = SecurityShield.detect_suspicious_encoding(content)
        if not encoding_report["safe"]:
            risk_score += 5
            reasons.append(encoding_report["reason"])

        is_safe = risk_score < 20 # Allow low risk, block high risk (CLI block is 20)
        
        if not is_safe:
            logger.warning(f"[SECURITY] Risk ({risk_score}) detected from {source}: {reasons}")

        return {
            "safe": is_safe,
            "score": risk_score,
            "reasons": reasons
        }

