# Roadmap

Plans for the client. Nothing here is a commitment, and the order may change. Shipped
changes are in [CHANGELOG.md](CHANGELOG.md).

## 1.0.0

The first release with a stable public API. Until then, minor releases may contain
breaking changes.

- **Connection reuse:** use a `requests.Session`, with `close()` and context manager
  support, so multi-page reads don't open a new connection per request.
- **Error types:** subclasses of `ApiError` for authentication (401/403), rate limiting
  (429) and not found, so callers can handle them separately. `ApiError` remains the base
  class.
- **Typing:** type hints throughout and a `py.typed` marker.
- **Version validation:** reject malformed version strings such as `"vv2"` when the client
  is created, instead of failing at the server (Maybe).
- **Packaging and documentation:** project URLs, classifiers and dependency bounds;
  guidance on obtaining and handling a token; example scripts.
- **Warn on cleartext URLs:** flag `http://` URLs, which would send the token unencrypted.

## Later

- Retry GET requests on server errors and connection failures, and honour `Retry-After`
  given as an HTTP date.
