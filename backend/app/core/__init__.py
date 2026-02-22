"""Core utilities: tenant context, dependencies."""
from .tenant import get_tenant_context, TenantContext as TenantContextDep

__all__ = ["get_tenant_context", "TenantContextDep"]
