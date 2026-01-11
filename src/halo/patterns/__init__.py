"""
Pattern detection module for identifying fraud patterns.

Includes:
- Shell network detection (in-memory and database-backed)
- Registration mill detection
- Real-time alerting
- Pattern matching against resolved entities
"""

from halo.patterns.shell_network import (
    ShellNetworkDetector,
    ShellNetworkMatch,
    ShellNetworkParams,
    ShellCompany,
    RegistrationMillMatch,
    ShellNetworkDBResult,
    ShellNetworkQueryService,
    detect_shell_networks_db,
    detect_registration_mills_db,
    # SQL queries for direct use if needed
    SHELL_NETWORK_QUERY,
    REGISTRATION_MILL_QUERY,
)
from halo.patterns.alerting import (
    AlertGenerator,
    Alert,
    AlertType,
    AlertSeverity,
)

__all__ = [
    # In-memory detection
    "ShellNetworkDetector",
    "ShellNetworkMatch",
    "ShellNetworkParams",
    "ShellCompany",
    "RegistrationMillMatch",
    # Database-backed detection
    "ShellNetworkDBResult",
    "ShellNetworkQueryService",
    "detect_shell_networks_db",
    "detect_registration_mills_db",
    # SQL queries
    "SHELL_NETWORK_QUERY",
    "REGISTRATION_MILL_QUERY",
    # Alerting
    "AlertGenerator",
    "Alert",
    "AlertType",
    "AlertSeverity",
]
