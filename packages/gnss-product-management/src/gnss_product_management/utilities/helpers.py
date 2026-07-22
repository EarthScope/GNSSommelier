"""Shared helper functions and sentinel types.

Contains low-level utilities used across the package:

* :func:`hash_file` — SHA-256 file hashing.
* :func:`_ensure_datetime` — date/datetime normalisation to UTC.
* :class:`_PassthroughDict` — dict that preserves ``{key}`` for missing keys.
* :func:`_listify` — coerce scalars to single-element lists.
* :func:`expand_dict_combinations` — Cartesian product of dict values.
"""

import datetime
import hashlib
import itertools
import logging

logger = logging.getLogger(__name__)


def hash_file(path) -> str:
    """Return the SHA-256 hex digest of a file.

    Accepts both local :class:`~pathlib.Path` and cloud
    :class:`~cloudpathlib.CloudPath` objects.

    Args:
        path: Filesystem or cloud path to the file to hash.

    Returns:
        A string in the form ``sha256:<hex_digest>``.
    """
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def _ensure_datetime(date: datetime.date | datetime.datetime) -> datetime.datetime:
    """Coerce a date to a timezone-aware ``datetime`` (UTC).

    Args:
        date: A :class:`~datetime.date` or :class:`~datetime.datetime`.
            Naive datetimes are tagged as UTC.

    Returns:
        A timezone-aware :class:`~datetime.datetime` in UTC.
    """
    if isinstance(date, datetime.date) and not isinstance(date, datetime.datetime):
        return datetime.datetime(date.year, date.month, date.day, tzinfo=datetime.timezone.utc)
    if date.tzinfo is None:
        return date.replace(tzinfo=datetime.timezone.utc)
    return date


class _PassthroughDict(dict):
    """Dict subclass that returns ``'{key}'`` for missing keys.

    Used with :meth:`str.format_map` so that unresolved placeholders
    survive template expansion rather than raising :class:`KeyError`.
    """

    def __missing__(self, key):
        return f"{{{key}}}"


def _listify(v) -> list[str]:
    """Convert ``None`` or a single string to a list.

    Args:
        v: ``None``, a single string, or an existing list.

    Returns:
        A (possibly empty) ``list[str]``.
    """
    if v is None:
        return []
    return [v] if isinstance(v, str) else list(v)


def expand_dict_combinations(d: dict[str, list[str]]) -> list[dict[str, str]]:
    """Compute the Cartesian product of dict values.

    Args:
        d: Mapping from parameter names to lists of candidate values.

    Returns:
        A list of dicts, one per combination, with a single value per key.

    Example::

        >>> expand_dict_combinations({"A": ["1","2"], "B": ["x","y"]})
        [{"A":"1","B":"x"}, {"A":"1","B":"y"}, {"A":"2","B":"x"}, {"A":"2","B":"y"}]
    """
    keys = list(d.keys())
    vals = [d[k] for k in keys]
    return [dict(zip(keys, combo)) for combo in itertools.product(*vals)]
