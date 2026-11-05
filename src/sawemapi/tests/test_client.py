"""Tests for sawemapi.client."""
import datetime as dt
import json
import unittest
from unittest.mock import patch, MagicMock

from sawemapi.client import _to_frame
from sawemapi import (ApiError, ApiWarning, DEFAULT_TIMEOUT, RateLimiter, SAWEMApi, ApiReturnType)


class TestSAWEMApi(unittest.TestCase):
    """SAWEMApi request building and response handling."""

    def setUp(self):
        """Create a client."""
        self.api = SAWEMApi("https://host/api", "tok")

    def test_url(self):
        """The URL joins base, accessor and method."""
        self.assertEqual(self.api.url("A", "m"), "https://host/api/latest/A/m")

    def test_header_carries_token(self):
        """The token goes in the Authorization header."""
        self.assertEqual(self.api.header["Authorization"], "Bearer tok")

    @patch("sawemapi.client.requests.get")
    def test_get_data(self, get):
        """A GET returns the data field and records the status."""
        get.return_value = MagicMock(status_code=200, text='{"data": [1, 2]}')
        result = self.api.get("A", "m", {"x": 1}, return_type=ApiReturnType.data)
        self.assertEqual(result, [1, 2])
        self.assertEqual(self.api.result_code, 200)

    @patch("sawemapi.client.requests.post")
    def test_post_raw(self, post):
        """A POST returns the raw response and records the status."""
        response = MagicMock(status_code=201)
        post.return_value = response
        self.assertIs(self.api.post("A", "m", {"x": 1}), response)
        self.assertEqual(self.api.result_code, 201)

    @patch("sawemapi.client.requests.post")
    def test_post_sends_json(self, post):
        """A POST sends the payload as JSON, not form data."""
        post.return_value = MagicMock(status_code=200)
        self.api.post("A", "m", {"x": 1})
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["json"], {"x": 1})
        self.assertNotIn("data", kwargs)

    @patch("sawemapi.client.requests.get")
    def test_defaults_applied(self, get):
        """Calls use the default timeout and verify certificates."""
        get.return_value = MagicMock(status_code=200)
        self.api.get("A", "m", {})
        self.assertEqual(get.call_args.kwargs["timeout"], DEFAULT_TIMEOUT)
        self.assertIs(get.call_args.kwargs["verify"], True)

    @patch("sawemapi.client.requests.post")
    @patch("sawemapi.client.requests.get")
    def test_timeout_and_verify_settable(self, get, post):
        """Timeout and verify can be given at construction or changed afterwards."""
        get.return_value = post.return_value = MagicMock(status_code=200)
        api = SAWEMApi("https://host/api", "tok", timeout=5, verify="/ca.pem")
        api.get("A", "m", {})
        self.assertEqual(get.call_args.kwargs["timeout"], 5)
        self.assertEqual(get.call_args.kwargs["verify"], "/ca.pem")
        api.timeout = (3, 10)
        api.verify = False
        api.post("A", "m", {})
        self.assertEqual(post.call_args.kwargs["timeout"], (3, 10))
        self.assertIs(post.call_args.kwargs["verify"], False)

    @patch("sawemapi.client.requests.get")
    def test_error_raised_with_server_message(self, get):
        """A non-2xx response raises ApiError carrying the server's message."""
        get.return_value = MagicMock(status_code=403, text='{"message": "Not allowed"}')
        with self.assertRaises(ApiError) as ctx:
            self.api.get("A", "m", {}, return_type=ApiReturnType.data)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.message, "Not allowed")
        self.assertEqual(self.api.result_code, 403)

    @patch("sawemapi.client.requests.post")
    def test_error_raised_for_raw_and_non_json_body(self, post):
        """Errors are raised for every return type, and a non-JSON body becomes the message."""
        post.return_value = MagicMock(status_code=502, text="Bad Gateway")
        with self.assertRaises(ApiError) as ctx:
            self.api.post("A", "m", {})
        self.assertEqual(ctx.exception.message, "Bad Gateway")
        self.assertEqual(str(ctx.exception), "502: Bad Gateway")

    @patch("sawemapi.client.requests.post")
    def test_other_2xx_not_an_error(self, post):
        """A 201 or 204 is a success."""
        post.return_value = MagicMock(status_code=204, text="")
        self.assertEqual(self.api.post("A", "m", {}, return_type=ApiReturnType.text), "")


def reply(status=200, body=None, headers=None):
    """A fake response whose text is `body` encoded as JSON."""
    return MagicMock(status_code=status, text=json.dumps(body) if body is not None else "",
                     headers=headers or {})


class TestRequests(unittest.TestCase):
    """Versioning, query parameters, dates, retries and warnings."""

    def setUp(self):
        """Create a client."""
        self.api = SAWEMApi("https://host/api", "tok")

    def test_version_in_url(self):
        """A version adds a normalised segment to the URL."""
        for version in (2, "2", "v2"):
            api = SAWEMApi("https://host/api", "tok", version=version)
            self.assertEqual(api.url("A", "m"), "https://host/api/v2/A/m")

    def test_latest_is_the_default_version(self):
        """Without a version the URL uses latest."""
        self.assertEqual(self.api.version, "latest")
        self.assertEqual(SAWEMApi("https://host/api", "tok", version="Latest").version, "latest")

    def test_version_required(self):
        """None and empty are not valid versions, at construction or when set."""
        for bad in (None, "", "  "):
            with self.assertRaises(ValueError):
                SAWEMApi("https://host/api", "tok", version=bad)
        with self.assertRaises(ValueError):
            self.api.version = None
        self.api.version = 3
        self.assertEqual(self.api.url("A", "m"), "https://host/api/v3/A/m")

    @patch("sawemapi.client.requests.get")
    def test_paging_arguments_sent_flat(self, get):
        """limit, offset and include_total are sent as flat parameters."""
        get.return_value = reply(200, {"data": []})
        self.api.get("A", "m", {"a": 1}, limit=50, offset=100, include_total=True)
        self.assertEqual(get.call_args.kwargs["params"],
                         {"a": 1, "limit": 50, "offset": 100, "include_total": "true"})

    @patch("sawemapi.client.requests.get")
    def test_qry_param_dict_json_encoded(self, get):
        """A qry_param dict is sent as one JSON parameter, from the argument or from params."""
        get.return_value = reply(200, {"data": []})
        params = {"a": 1, "qry_param": {"limit": 10}}
        self.api.get("A", "m", params)
        self.api.get("A", "m", {"a": 1}, qry_param={"limit": 10})
        for call in get.call_args_list:
            self.assertEqual(call.kwargs["params"]["a"], 1)
            self.assertEqual(json.loads(call.kwargs["params"]["qry_param"]), {"limit": 10})
            self.assertNotIn("limit", call.kwargs["params"])
        self.assertEqual(params["qry_param"], {"limit": 10})

    @patch("sawemapi.client.requests.get")
    def test_qry_param_string_passed_through(self, get):
        """A qry_param that is already JSON is sent unchanged."""
        get.return_value = reply(200, {"data": []})
        self.api.get("A", "m", qry_param='{"limit": 10}')
        self.assertEqual(get.call_args.kwargs["params"], {"qry_param": '{"limit": 10}'})

    def test_qry_param_conflicts(self):
        """qry_param can't be given twice or together with the flat arguments."""
        with self.assertRaises(ValueError):
            self.api.get("A", "m", {"qry_param": "{}"}, limit=5)
        with self.assertRaises(ValueError):
            self.api.get("A", "m", qry_param={"limit": 1}, offset=5)
        with self.assertRaises(ValueError):
            self.api.get("A", "m", {"qry_param": "{}"}, qry_param="{}")

    @patch("sawemapi.client.requests.get")
    def test_dates_serialised_in_params(self, get):
        """Dates and datetimes are sent in the API's format."""
        get.return_value = reply(200, {"data": []})
        self.api.get("A", "m", {"start_date": dt.date(2026, 12, 1),
                                "start_time": dt.datetime(2026, 12, 1, 14, 0, 30)})
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["start_date"], "2026-12-01")
        self.assertEqual(params["start_time"], "2026-12-01 14:00")

    @patch("sawemapi.client.requests.post")
    def test_dates_serialised_in_payload(self, post):
        """Dates nested in a payload are converted too."""
        post.return_value = reply(200, {"data": None})
        self.api.post("A", "m", {"rows": [{"day": dt.date(2026, 12, 1)}]})
        self.assertEqual(post.call_args.kwargs["json"], {"rows": [{"day": "2026-12-01"}]})

    @patch("sawemapi.client.time.sleep")
    @patch("sawemapi.client.requests.get")
    def test_retries_on_429_with_backoff(self, get, sleep):
        """A 429 is retried with a doubling delay until it succeeds."""
        get.side_effect = [reply(429), reply(429), reply(200, {"data": [1]})]
        result = self.api.get("A", "m", return_type=ApiReturnType.data)
        self.assertEqual(result, [1])
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1.0, 2.0])
        self.assertEqual(self.api.result_code, 200)

    @patch("sawemapi.client.time.sleep")
    @patch("sawemapi.client.requests.post")
    def test_post_not_retried(self, post, sleep):
        """A 429 on a write is raised at once, never retried."""
        post.return_value = reply(429, {"message": "Slow down"})
        with self.assertRaises(ApiError) as ctx:
            self.api.post("A", "m", {})
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(post.call_count, 1)
        sleep.assert_not_called()

    @patch("sawemapi.client.time.sleep")
    @patch("sawemapi.client.requests.get")
    def test_retry_after_honoured(self, get, sleep):
        """The server's Retry-After overrides the backoff."""
        get.side_effect = [reply(429, headers={"Retry-After": "7"}),
                           reply(200, {"data": []})]
        self.api.get("A", "m")
        sleep.assert_called_once_with(7.0)

    @patch("sawemapi.client.time.sleep")
    @patch("sawemapi.client.requests.get")
    def test_gives_up_after_max_retries(self, get, sleep):
        """When retries run out the 429 is raised as ApiError."""
        get.return_value = reply(429, {"message": "Slow down"})
        api = SAWEMApi("https://host/api", "tok", max_retries=2)
        with self.assertRaises(ApiError) as ctx:
            api.get("A", "m")
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch("sawemapi.client.requests.get")
    def test_throttle_used_when_configured(self, get):
        """Every attempt goes through the rate limiter, and a list of limits is accepted."""
        get.return_value = reply(200, {"data": []})
        limiter = MagicMock(spec=RateLimiter)
        api = SAWEMApi("https://host/api", "tok", rate_limits=limiter)
        api.get("A", "m")
        limiter.acquire.assert_called_once_with()
        api.rate_limiter = [(100, 60)]
        self.assertIsInstance(api.rate_limiter, RateLimiter)
        api.rate_limiter = None
        api.get("A", "m")

    @patch("sawemapi.client.requests.get")
    def test_warnings_surfaced(self, get):
        """Warnings in the envelope are emitted as ApiWarning."""
        get.return_value = reply(200, {"data": [], "warnings": ["method deprecated"]})
        with self.assertWarnsRegex(ApiWarning, "method deprecated"):
            self.api.get("A", "m", return_type=ApiReturnType.data)

    @patch("sawemapi.client.requests.get")
    def test_error_list_in_message(self, get):
        """With no message, the errors list becomes the message."""
        get.return_value = reply(400, {"status": False, "message": "",
                                          "errors": ["row 1 bad", "row 2 bad"]})
        with self.assertRaises(ApiError) as ctx:
            self.api.get("A", "m")
        self.assertEqual(ctx.exception.errors, ["row 1 bad", "row 2 bad"])
        self.assertEqual(ctx.exception.message, "row 1 bad; row 2 bad")


class TestDataFrames(unittest.TestCase):
    """ISO datetime handling in DataFrames."""

    def test_iso_columns_become_datetimes(self):
        """Columns of ISO datetimes convert; other string columns are left alone."""
        frame = _to_frame([{"t": "2026-12-01T00:00:00", "s": "x"},
                          {"t": "2026-12-01T01:00:00", "s": "2026-12-01"}])
        self.assertTrue(str(frame["t"].dtype).startswith("datetime64"))
        self.assertEqual(frame["s"].tolist(), ["x", "2026-12-01"])

    def test_parse_dates_off(self):
        """parse_dates=False leaves strings as they are."""
        frame = _to_frame([{"t": "2026-12-01T00:00:00"}], parse_dates=False)
        self.assertEqual(frame["t"].tolist(), ["2026-12-01T00:00:00"])
