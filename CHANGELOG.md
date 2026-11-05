# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project follows
[Semantic Versioning](https://semver.org/) from 1.0.0; until then, minor releases may
contain breaking changes.

## [0.1.0] - 2026-11-02

First release.

### Added
- `SAWEMApi` client with `get` and `post`, authenticating with a bearer token.
- `ApiReturnType`: return the raw response, the text, the parsed envelope, the `data`
  field, or a pandas DataFrame (optional `pandas` extra).
- Pagination: `limit`, `offset` and `include_total` arguments, `pages()` to read one page
  at a time and `get_all()` to combine every page. `qry_param` can be given as a dict or
  as a JSON string.
- Rate limiting: GET requests answered with 429 are retried with exponential backoff,
  honouring `Retry-After`. An optional client-side `RateLimiter` throttles calls.
  POST requests are never retried.
- API versions: the `version` argument, defaulting to `latest`. Pin a fixed version for
  anything that has to keep working.
- Dates: `date` and `datetime` values in parameters and payloads are converted to the
  API's format; ISO datetime columns in DataFrames are converted to datetimes.
- `ApiError` for non-2xx responses, carrying the status code, message, error list and
  response. `ApiWarning` for warnings in the response envelope.
- Configurable `timeout` (default 30 seconds) and TLS `verify` (`True`, `False` or a CA
  bundle path).
