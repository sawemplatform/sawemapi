# sawemapi

Python client for the SAWEM API.

## Installation

```
pip install sawemapi
pip install sawemapi[pandas]   # to receive results as DataFrames
```

Requires Python 3.11 or later.

## Usage

```python
from sawemapi import SAWEMApi, ApiReturnType

api = SAWEMApi("https://host/api", token, version=2)

# Read: GET {url}/v2/{accessor}/{method}?day=2026-01-01
rows = api.get("Accessor", "method", {"day": "2026-01-01"},
               return_type=ApiReturnType.data)

# Write: POST {url}/v2/{accessor}/{method}
api.post("Accessor", "method", payload)

print(api.result_code)  # HTTP status of the last call
```

`url` is the base URL without a trailing slash. `token` is the bearer token issued to
you for the API.

## Pagination

List endpoints return results in pages. `limit`, `offset` and `include_total` are
keyword arguments of `get`, sent as flat query parameters. The API's `qry_param`
object, for fields beyond those three, can be passed as a dict or a JSON string instead,
but not together with them:

```python
api.get("Accessor", "method", qry_param={"limit": 50, "offset": 100})
api.get("Accessor", "method", qry_param='{"limit": 50, "offset": 100}')
```

```python
# One page at a time. Each item is the parsed envelope, including `pagination`.
for page in api.pages("Accessor", "method", {"day": "2026-12-01"},
                      limit=500, include_total=True):
    print(page["pagination"], len(page["data"]))

# Everything, combined: a list, or one DataFrame
rows = api.get_all("Accessor", "method", {"day": "2026-12-01"})
frame = api.get_all("Accessor", "method", {"day": "2026-12-01"},
                    return_type=ApiReturnType.df)
```

`pages` continues in whichever form you started with. `pages` and `get_all` follow `has_more` until the last page. `include_total` slows the
server down, so `pages` requests it on the first page only.

## Rate limiting

The API allows 500 requests per hour and 30 per minute by default; endpoints may differ
and the limits are configured per environment.

- A `get` answered with 429 is retried up to `max_retries` times (default 3). The wait
  is the server's `Retry-After` if it sends one, otherwise `backoff` seconds (default 1)
  doubling each time. When the retries run out, `ApiError` is raised.
- `post` is never retried: a 429 raises `ApiError` immediately, and whether to repeat a
  write is for you to decide.
- To avoid reaching the limit, throttle on the client side. This is off by default:

```python
from sawemapi import DEFAULT_RATE_LIMITS

api = SAWEMApi(url, token, rate_limits=DEFAULT_RATE_LIMITS)  # 30/minute, 500/hour
api = SAWEMApi(url, token, rate_limits=[(10, 60)])            # your own limits
api.rate_limiter = None                                      # switch it off
```

Calls block until they are allowed. Pass limits that match your account's.

## Versions

Every call goes to a versioned URL. The default is `latest`; **pin a fixed version**
for anything that has to keep working:

```python
api = SAWEMApi(url, token, version=2)   # calls {url}/v2/{accessor}/{method}
api = SAWEMApi(url, token)              # calls {url}/latest/{accessor}/{method}
```

`latest` follows the newest API version, so a new release can change or remove methods
under you. A fixed version only changes when you change it. `version` accepts `2`, `"2"`
or `"v2"`, and can't be left empty.

## Dates and times

- Parameters and `post` payloads: `datetime.date` values are sent as `yyyy-mm-dd` and
  `datetime.datetime` values as `yyyy-mm-dd hh:mm` (seconds are dropped). Use a `date`
  for `*_date` parameters and a `datetime` for `*_time` parameters, since the API
  rejects a time on a date parameter.
- Start values are inclusive and end values exclusive: one day is
  `start_date=date(2026, 12, 1), end_date=date(2026, 12, 2)`.
- Returned data holds ISO strings such as `2026-12-01T00:00:00`, in SAST with no
  timezone. In DataFrames, columns made up entirely of such strings are converted to
  naive datetimes. Pass `parse_dates=False` to the constructor to keep strings.

## Warnings

Entries in the envelope's `warnings` list, such as deprecation notices, are emitted
through Python's `warnings` module as `sawemapi.ApiWarning`. Silence or escalate them
with the standard filters.

## Timeout and TLS

```python
api = SAWEMApi(url, token, timeout=10, verify="/path/to/ca-bundle.pem")

api.timeout = (3, 30)   # (connect, read) seconds; None waits indefinitely
api.verify = False      # disable certificate verification (not recommended)
```

`timeout` defaults to 30 seconds. `verify` defaults to `True`; give the path to a CA
bundle if your server uses a private certificate authority. Both follow the semantics
of the same arguments in `requests`.

`post` sends the payload as JSON. Apart from dates (see below), values must be
serialisable by the standard `json` module.

## Return types

Pass `return_type` to `get` or `post` to choose what comes back:

| `ApiReturnType` | Returns                                                        |
|-----------------|----------------------------------------------------------------|
| `raw` (default) | the `requests.Response`                                        |
| `text`          | the response body as a string                                  |
| `envelope`      | the parsed JSON body, including status and message             |
| `data`          | the `data` field of the parsed body                            |
| `df`            | the `data` field as a pandas `DataFrame` (needs the extra)     |

## Thread safety

A `SAWEMApi` is not thread-safe. `result_code` holds the status of the most recent call,
so concurrent calls overwrite each other's, and settings such as `timeout` or `verify`
changed in one thread affect calls in flight in another. Use one client per thread. The
`RateLimiter` itself is thread-safe, so one instance can be shared between clients via
`rate_limits=` to keep their combined calls within a limit.

## Errors

A response with a non-2xx status raises `sawemapi.ApiError`, whatever the return type.
It carries `status_code`, `message` (the server's `message` field, else its `errors`
joined, else the response body), the `errors` list and the full `response`. `result_code` is still set.

```python
from sawemapi import ApiError

try:
    api.get("Accessor", "method", {})
except ApiError as err:
    print(err.status_code, err.message)
```

Failures of the request itself, such as a timeout or connection error, raise the
corresponding `requests.RequestException`.

## Project

The changelog (`CHANGELOG.md`) records what has changed. The roadmap (`ROADMAP.md`)
lists what is planned.

## Licence

Apache-2.0. See `LICENSE`.
