"""Workgroup discovery and compatibility migration helpers.

Workgroups are organizational containers.  Workers own workflows; the runtime
uses a small adapter only while legacy Department packages are being migrated.
"""

from .legacy import WorkgroupHandler, workgroup_from_legacy

__all__ = ["WorkgroupHandler", "workgroup_from_legacy"]
