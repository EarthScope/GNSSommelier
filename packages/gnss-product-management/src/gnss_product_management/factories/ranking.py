"""ranking — module-level helpers for sorting SearchTarget results."""

from __future__ import annotations

from gnss_product_management.specifications.dependencies.dependencies import (
    SearchPreference,
)
from gnss_product_management.specifications.remote.resource import SearchTarget


def _get_param_value(rq: SearchTarget, param_name: str) -> str:
    """Extract a parameter value from a SearchTarget's product.

    Args:
        rq: The target to inspect.
        param_name: Parameter name to extract.

    Returns:
        The parameter value, or ``""`` if not found.
    """
    for p in rq.product.parameters:
        if p.name == param_name and p.value is not None:
            return p.value
    return ""


def sort_by_protocol(targets: list[SearchTarget]) -> list[SearchTarget]:
    """Sort search targets by server protocol, preferring local/file over remote.

    Args:
        targets: SearchTarget objects to sort.

    Returns:
        Sorted list of targets, with ``FILE`` / ``LOCAL`` first,
        then ``FTP`` / ``FTPS`` / ``SFTP``, then ``HTTP`` / ``HTTPS``.
    """
    protocol_sort_order = ["FILE", "LOCAL", "FTP", "FTPS", "SFTP", "HTTP", "HTTPS"]
    return sorted(
        targets,
        key=lambda rq: (
            protocol_sort_order.index((rq.server.protocol or "").upper())
            if (rq.server.protocol or "").upper() in protocol_sort_order
            else len(protocol_sort_order)
        ),
    )


def sort_by_preferences(
    targets: list[SearchTarget],
    preferences: list[SearchPreference],
) -> list[SearchTarget]:
    """Sort search targets according to a preference cascade.

    Iterates *preferences* in reverse order (lowest priority first) so
    that the highest-priority preference ends up as the primary sort key.

    Args:
        targets: SearchTarget objects to sort.
        preferences: Ordered list of :class:`SearchPreference` objects
            defining the desired sort cascade.

    Returns:
        Sorted list of targets.
    """
    if not preferences:
        return targets

    for pref in reversed(preferences):
        param_name = pref.parameter
        sorting = [v.upper() for v in pref.sorting]

        def _key(rq: SearchTarget, _pn=param_name, _s=sorting) -> int:
            try:
                val = _get_param_value(rq, _pn).upper()
                return _s.index(val)
            except (ValueError, TypeError):
                return len(_s)

        targets = sorted(targets, key=_key)

    return targets
