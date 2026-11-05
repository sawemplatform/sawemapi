"""Client for the SAWEM API: :class:`SAWEMApi` and the helpers that shape its responses."""
import datetime as dt
import json
import re
import time
import warnings
from enum import StrEnum

import requests

from sawemapi.errors import ApiError, ApiWarning
from sawemapi.ratelimit import RateLimiter

DEFAULT_TIMEOUT = 30
LATEST = "latest"

# Datetimes in returned data look like '2026-12-01T00:00:00': ISO, no timezone, SAST.
_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


class ApiReturnType(StrEnum):
    """How a response is returned to the caller."""

    raw = "raw"            # the requests.Response
    text = "text"          # the response body, unparsed
    envelope = "envelope"  # the parsed response, status and message included
    data = "data"          # the envelope's data field
    df = "df"              # the data field as a DataFrame


def _to_frame(rows, parse_dates=True):
    """Build a DataFrame from `rows`, converting ISO datetime strings to datetimes.

    Args:
        rows: The data field of a response.
        parse_dates (bool): Convert columns where every value looks like
            '2026-12-01T00:00:00'. The results are naive, in SAST like the API's times.

    Raises:
        ImportError: If pandas is not installed.
    """
    import pandas as pd  # pylint: disable=import-outside-toplevel
    frame = pd.DataFrame(rows)
    if parse_dates:
        for column in frame.columns:
            if not pd.api.types.is_string_dtype(frame[column]):
                continue
            values = frame[column].dropna()
            if len(values) and values.map(
                    lambda v: isinstance(v, str) and bool(_ISO_DATETIME.match(v))).all():
                frame[column] = pd.to_datetime(frame[column], format="%Y-%m-%dT%H:%M:%S")
    return frame


def _decode(response, return_type=ApiReturnType.raw, envelope=None, parse_dates=True):
    """Shape a response according to `return_type`.

    Args:
        response (requests.Response): The response to shape.
        return_type (ApiReturnType): The shape wanted. Defaults to the response itself.
        envelope (dict|None): The already parsed body, to avoid parsing it again.
        parse_dates (bool): For ``ApiReturnType.df``, convert ISO datetime columns.

    Returns:
        The response, its text, the parsed body, the body's ``data`` field or a
        DataFrame of that field, depending on `return_type`.

    Raises:
        ValueError: If `return_type` is not an :class:`ApiReturnType`.
        ImportError: For ``ApiReturnType.df`` when pandas is not installed.
    """
    if return_type == ApiReturnType.raw:
        return response
    if return_type == ApiReturnType.text:
        return response.text
    data = envelope if envelope is not None else json.loads(response.text)
    if return_type == ApiReturnType.envelope:
        return data
    if return_type == ApiReturnType.data:
        return data['data']
    if return_type == ApiReturnType.df:
        return _to_frame(data['data'], parse_dates)
    raise ValueError(f"Unknown return type {return_type!r}")


def _serialise(value):
    """Convert `value` to what the API expects, recursing into dicts, lists and tuples.

    Datetimes become 'yyyy-mm-dd hh:mm' and dates 'yyyy-mm-dd'. Seconds are dropped, as
    the API takes minute resolution.
    """
    if isinstance(value, dt.datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialise(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialise(v) for v in value]
    return value


class SAWEMApi:  # pylint: disable=too-many-instance-attributes
    """Client for the SAWEM API, authenticating every call with a bearer token.

    Not thread-safe: `result_code` and the settings are plain attributes. Use one client
    per thread, or don't rely on `result_code` and don't change settings while calls
    are in flight.

    Args:
        url (str): Base URL of the API, without a trailing slash.
        token (str): The bearer token to authenticate with.
        timeout (float|tuple|None): Seconds to wait for the server, as for ``requests``:
            a single value, or a (connect, read) pair. None waits indefinitely.
        verify (bool|str): TLS certificate verification, as for ``requests``: True to
            verify against the default CA bundle, False to disable verification, or
            the path to a CA bundle or directory.
        version (int|str): API version, e.g. 2 or "v2", or "latest" (the default). It is
            always part of the URL. Pin a fixed version in anything that must keep
            working: "latest" can change behaviour when a new version is released.
        max_retries (int): How often to retry a read (GET) answered with 429 Too Many
            Requests. Writes (POST) are never retried.
        backoff (float): Seconds to wait before the first retry; doubles on each one.
            A ``Retry-After`` header from the server takes precedence.
        rate_limits (iterable|RateLimiter|None): Throttle calls on the client side:
            (requests, seconds) pairs, or a :class:`RateLimiter`. See
            ``sawemapi.DEFAULT_RATE_LIMITS`` for the API's documented defaults. None
            disables throttling.
        parse_dates (bool): Convert ISO datetime columns to datetimes in DataFrames.
    """

    # pylint: disable-next=too-many-arguments
    def __init__(self, url, token, timeout=DEFAULT_TIMEOUT, verify=True, *, version=LATEST,
                 max_retries=3, backoff=1.0, rate_limits=None, parse_dates=True):
        self._url = url
        self._token = token
        self._result_code = None
        self.timeout = timeout
        self.verify = verify
        self.version = version
        self.max_retries = max_retries
        self.backoff = backoff
        self.rate_limiter = rate_limits
        self.parse_dates = parse_dates

    @property
    def header(self):
        """The headers sent with every request, including the authorisation token."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._token}"
        }

    @property
    def timeout(self):
        """Seconds to wait for the server; a single value, a (connect, read) pair or None."""
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        self._timeout = value

    @property
    def verify(self):
        """TLS verification: True, False, or the path to a CA bundle or directory."""
        return self._verify

    @verify.setter
    def verify(self, value):
        self._verify = value

    @property
    def version(self):
        """The API version used in the URL: "latest", or normalised to the form "v2"."""
        return self._version

    @version.setter
    def version(self, value):
        text = str(value).strip().lower() if value is not None else ""
        if not text:
            raise ValueError('version is required: a number such as 2, or "latest"')
        if text == LATEST or text.startswith("v"):
            self._version = text
        else:
            self._version = f"v{text}"

    @property
    def rate_limiter(self):
        """The client-side :class:`RateLimiter`, or None when not throttling.

        Can be set to a RateLimiter, an iterable of (requests, seconds) pairs, or None.
        """
        return self._rate_limiter

    @rate_limiter.setter
    def rate_limiter(self, value):
        if value is None or isinstance(value, RateLimiter):
            self._rate_limiter = value
        else:
            self._rate_limiter = RateLimiter(value)

    @property
    def result_code(self):
        """The HTTP status code of the most recent call, or None before the first call."""
        return self._result_code

    def url(self, accessor, method):
        """The URL of `method` on `accessor`, including the version."""
        return f"{self._url}/{self._version}/{accessor}/{method}"

    # pylint: disable-next=too-many-arguments
    def get(self, accessor, method, params=None, return_type: ApiReturnType = ApiReturnType.raw,
            *, limit=None, offset=None, include_total=None, qry_param=None):
        """Read data from the API.

        Args:
            accessor (str): The accessor to call.
            method (str): The method on the accessor.
            params (dict|None): Query string parameters. Dates and datetimes are
                converted to the API's format.
            return_type (ApiReturnType): How to return the response.
            limit (int|None): Page size.
            offset (int|None): Rows to skip.
            include_total (bool|None): Ask for the total row count.
            qry_param (dict|str|None): The API's ``qry_param`` object, as a dict or as a
                JSON encoded string, for fields beyond the three above. Use it instead of
                `limit`, `offset` and `include_total`, not together with them. It may
                also be given inside `params`.

        Returns:
            The response, shaped by `return_type`. The status code is available
            afterwards as `result_code`. Use :meth:`pages` or :meth:`get_all` to read
            beyond the first page.

        Raises:
            ApiError: If the API answers with a non-2xx status. `result_code` is still set.
            requests.RequestException: If the request itself fails, e.g. on timeout.
        """
        query = self._query(params, qry_param, limit, offset, include_total)
        return self._request("get", accessor, method, return_type, params=query)

    def post(self, accessor, method, payload, return_type: ApiReturnType = ApiReturnType.raw):
        """Send data to the API.

        Args:
            accessor (str): The accessor to call.
            method (str): The method on the accessor.
            payload: The request body, sent as JSON. Dates and datetimes are converted
                to the API's format.
            return_type (ApiReturnType): How to return the response.

        Returns:
            The response, shaped by `return_type`. The status code is available
            afterwards as `result_code`.

        Raises:
            ApiError: If the API answers with a non-2xx status. `result_code` is still set.
            requests.RequestException: If the request itself fails, e.g. on timeout.
        """
        return self._request("post", accessor, method, return_type, json=_serialise(payload))

    # pylint: disable-next=too-many-arguments
    def pages(self, accessor, method, params=None, *, limit=None, offset=None,
              include_total=False, qry_param=None):
        """Read a list endpoint one page at a time.

        Follows the response's pagination info until no more records are available.
        The total is requested on the first page only, since computing it is slow.

        Args:
            accessor (str): The accessor to call.
            method (str): The method on the accessor.
            params (dict|None): Query string parameters.
            limit (int|None): Page size. The server's default applies when None.
            offset (int|None): Row to start at.
            include_total (bool): Report the total row count on the first page.
            qry_param (dict|str|None): The API's ``qry_param`` object, as a dict or JSON
                encoded string, instead of `limit`, `offset` and `include_total`. Paging
                continues in that form.

        Yields:
            dict: The parsed envelope of each page.

        Raises:
            ApiError: If any page is answered with a non-2xx status.
        """
        by_qry_param = qry_param is not None
        if by_qry_param:
            if limit is not None or offset is not None:
                raise ValueError("pass limit and offset or qry_param, not both")
            state = json.loads(qry_param) if isinstance(qry_param, str) else dict(qry_param)
        else:
            state = {"limit": limit, "offset": offset, "include_total": include_total}
        while True:
            if by_qry_param:
                envelope = self.get(accessor, method, params, ApiReturnType.envelope,
                                    qry_param=state)
            else:
                envelope = self.get(accessor, method, params, ApiReturnType.envelope,
                                    **{k: v for k, v in state.items() if v is not None})
            yield envelope
            page = envelope.get("pagination") or {}
            step = page.get("limit") or 0
            if not page.get("has_more") or step <= 0:
                return
            state["offset"] = (page.get("offset") or 0) + step
            state["include_total"] = False

    # pylint: disable-next=too-many-arguments
    def get_all(self, accessor, method, params=None, return_type: ApiReturnType = ApiReturnType.data,
                *, limit=None, offset=None, qry_param=None):
        """Read every page of a list endpoint and combine the results.

        Args:
            accessor (str): The accessor to call.
            method (str): The method on the accessor.
            params (dict|None): Query string parameters.
            return_type (ApiReturnType): ``data`` for one list of all records, or ``df``
                for one DataFrame.
            limit (int|None): Page size. The server's default applies when None.
            offset (int|None): Row to start at.
            qry_param (dict|str|None): The API's ``qry_param`` object, as a dict or JSON
                encoded string, instead of `limit` and `offset`.

        Raises:
            ValueError: If `return_type` is not ``data`` or ``df``.
            ApiError: If any page is answered with a non-2xx status.
        """
        if return_type not in (ApiReturnType.data, ApiReturnType.df):
            raise ValueError("get_all supports the data and df return types only")
        rows = []
        for envelope in self.pages(accessor, method, params, limit=limit, offset=offset,
                                   qry_param=qry_param):
            rows.extend(envelope["data"])
        if return_type == ApiReturnType.df:
            return _to_frame(rows, self.parse_dates)
        return rows

    @staticmethod
    # pylint: disable-next=too-many-arguments
    def _query(params, qry_param, limit, offset, include_total):
        """Build the query string parameters.

        The paging arguments go as flat parameters; `qry_param` goes as one JSON encoded
        parameter. The API accepts either, but they are not combined here.

        Raises:
            ValueError: If `qry_param` is given twice, or together with flat arguments.
        """
        query = _serialise(dict(params or {}))
        embedded = query.pop("qry_param", None)
        if embedded is not None and qry_param is not None:
            raise ValueError("qry_param given both in params and as an argument")
        if qry_param is None:
            qry_param = embedded
        flat = {key: value for key, value in
                (("limit", limit), ("offset", offset), ("include_total", include_total))
                if value is not None}
        if qry_param is None:
            for key, value in flat.items():
                query[key] = str(value).lower() if isinstance(value, bool) else value
        elif flat:
            raise ValueError("pass limit, offset and include_total or qry_param, not both")
        else:
            query["qry_param"] = qry_param if isinstance(qry_param, str) else json.dumps(qry_param)
        return query

    def _request(self, http_method, accessor, method, return_type, **kwargs):
        """Send a request and shape the response. A GET answered with 429 is retried.

        Writes are never retried: whether to repeat one is for the caller to decide.

        Raises:
            ApiError: If the final response status is not 2xx.
        """
        send = getattr(requests, http_method)
        url = self.url(accessor, method)
        attempt = 0
        while True:
            if self._rate_limiter is not None:
                self._rate_limiter.acquire()
            response = send(url, headers=self.header, timeout=self.timeout,
                            verify=self.verify, **kwargs)
            self._result_code = response.status_code
            if (response.status_code != 429 or http_method != "get"
                    or attempt >= self.max_retries):
                return self._return_data(return_type, response)
            time.sleep(self._retry_delay(response, attempt))
            attempt += 1

    def _retry_delay(self, response, attempt):
        """Seconds to wait before retrying: ``Retry-After`` if given, else exponential."""
        try:
            return max(0.0, float(response.headers.get("Retry-After")))
        except (TypeError, ValueError):
            return self.backoff * 2 ** attempt

    def _return_data(self, return_type: ApiReturnType, response):
        """Shape `response` according to `return_type`, passing on any API warnings.

        Raises:
            ApiError: If the response status is not 2xx.
        """
        if not 200 <= response.status_code < 300:
            raise ApiError(response)
        try:
            envelope = json.loads(response.text)
        except (ValueError, TypeError):
            envelope = None
        if isinstance(envelope, dict):
            for message in envelope.get("warnings") or []:
                warnings.warn(str(message), ApiWarning, stacklevel=4)
        else:
            envelope = None
        return _decode(response, return_type, envelope, self.parse_dates)
