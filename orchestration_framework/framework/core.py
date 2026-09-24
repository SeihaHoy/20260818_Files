"""
Core asset registry and dependency resolver.

An "asset" is just a Python function wrapped with metadata: its name,
its upstream dependencies (other Asset objects), and optional
group/owner/description for the metadata tables in SQL.

Registering an asset does not run it. Execution and persistence live
in executor.py / db.py — this module only knows about the graph shape.
"""

_REGISTRY = {}


class Asset:
    def __init__(self, func, deps=None, name=None, group=None, owner=None, description=None):
        self.func = func
        self.deps = deps or []
        self.name = name or func.__name__
        self.group = group
        self.owner = owner
        self.description = description or (func.__doc__ or "").strip()
        self.result = None
        _REGISTRY[self.name] = self

    def __repr__(self):
        return f"<Asset {self.name}>"


def asset(deps=None, group=None, owner=None, description=None):
    """Decorator that registers a function as an Asset.

    Usage:
        @asset()
        def extract_data():
            ...

        @asset(deps=[extract_data], group="transform")
        def clean_data():
            ...
    """
    def decorator(func):
        return Asset(func, deps=deps, group=group, owner=owner, description=description)
    return decorator


def topological_order(assets=None):
    """Return registered assets in dependency order (upstream first).

    Raises ValueError if the graph has a cycle.
    """
    assets = assets or list(_REGISTRY.values())
    visited, in_progress, order = set(), set(), []

    def visit(a):
        if a.name in visited:
            return
        if a.name in in_progress:
            raise ValueError(f"Circular dependency detected involving '{a.name}'")
        in_progress.add(a.name)
        for dep in a.deps:
            visit(dep)
        in_progress.discard(a.name)
        visited.add(a.name)
        order.append(a)

    for a in assets:
        visit(a)
    return order


def get_registry():
    """Return the current asset registry as {name: Asset}."""
    return dict(_REGISTRY)


def clear_registry():
    """Mainly for tests — wipes all registered assets."""
    _REGISTRY.clear()
