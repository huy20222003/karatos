"""
Network Utilities for NivaSound
Centralized functions for URL validation, SSRF protection, and network safety.
"""
import socket
import ipaddress
from urllib.parse import urlparse
from utils.logger import get_logger

logger = get_logger()

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

# Cloud Metadata Services & Localhost
BLOCKED_IPS = {
    "169.254.169.254",          # AWS/Azure Metadata
    "metadata.google.internal", # GCP Metadata
    "localhost",                # Localhost string
    "127.0.0.1",                # Localhost IPv4
    "::1"                       # Localhost IPv6
}

# TODO: Enhance IPv6 support for dual-stack networks.
def validate_url(url: str, allow_schemes: list = ["http", "https"]) -> bool:
    """
    Robust URL validation with SSRF protection and DNS resolution checks.
    """
    if not url:
        return False
        
    try:
        parsed = urlparse(url)
        
        # 1. Scheme Check
        if parsed.scheme.lower() not in allow_schemes:
            return False
            
        # 2. Hostname Check
        hostname = parsed.hostname
        if not hostname:
            return False
            
        if hostname.lower() in BLOCKED_IPS:
            logger.warning(f"[NETWORK] URL blocked (Blocked IP/Host): {url}")
            return False
            
        # 3. DNS Resolution & SSRF Check
        # Note: socket.getaddrinfo returns a list of addresses
        try:
            addr_info = socket.getaddrinfo(hostname, parsed.port or (80 if parsed.scheme == 'http' else 443))
            for family, socktype, proto, canonname, sockaddr in addr_info:
                ip_addr_str = sockaddr[0]
                ip_addr = ipaddress.ip_address(ip_addr_str)
                
                for network in BLOCKED_NETWORKS:
                    if ip_addr in network:
                        logger.warning(f"[NETWORK] URL blocked (SSRF Protection - {ip_addr_str}): {url}")
                        return False
        except socket.gaierror:
            # DNS resolution failed - could even be a malformed domain
            logger.debug(f"[NETWORK] DNS Resolution failed for: {hostname}")
            return False
            
        return True
    except Exception as e:
        logger.error(f"[NETWORK] Unexpected error during URL validation: {e}")
        return False
