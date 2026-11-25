"""Version markers for Gramma's host-side data contracts.

These versions are intentionally small integers. A reader should reject a
newer version rather than guessing at unknown fields; older versions remain
readable where the loader explicitly says so.
"""

PROJECT_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
SERVICE_CONTRACT_VERSION = 1
