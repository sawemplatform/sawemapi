"""Tests for SAWEMApi.pages and get_all."""
import json
import unittest
from unittest.mock import patch, MagicMock

from sawemapi import SAWEMApi, ApiReturnType


def page(rows, offset, limit, has_more, total=None):
    """A fake response for one page of a list endpoint."""
    pagination = {"offset": offset, "limit": limit, "has_more": has_more}
    if total is not None:
        pagination["total"] = total
    body = {"status": True, "message": "", "data": rows, "pagination": pagination}
    return MagicMock(status_code=200, text=json.dumps(body), headers={})


def sent(call):
    """The query parameters of a mocked request call."""
    return call.kwargs["params"]


class TestPagination(unittest.TestCase):
    """Following has_more across pages."""

    def setUp(self):
        """Create a client."""
        self.api = SAWEMApi("https://host/api", "tok")

    @patch("sawemapi.client.requests.get")
    def test_pages_follow_has_more(self, get):
        """Each request continues at offset + limit until has_more is false."""
        get.side_effect = [page([1, 2], 0, 2, True), page([3, 4], 2, 2, True),
                           page([5], 4, 2, False)]
        pages = list(self.api.pages("A", "m", {"day": "2026-12-01"}, limit=2))
        self.assertEqual([p["data"] for p in pages], [[1, 2], [3, 4], [5]])
        self.assertEqual([sent(c).get("offset") for c in get.call_args_list], [None, 2, 4])
        self.assertTrue(all(c.kwargs["params"]["day"] == "2026-12-01" for c in get.call_args_list))

    @patch("sawemapi.client.requests.get")
    def test_total_requested_on_first_page_only(self, get):
        """include_total is sent once, then switched off."""
        get.side_effect = [page([1], 0, 1, True, total=2), page([2], 1, 1, False)]
        pages = list(self.api.pages("A", "m", limit=1, include_total=True))
        self.assertEqual(pages[0]["pagination"]["total"], 2)
        self.assertEqual(sent(get.call_args_list[0])["include_total"], "true")
        self.assertEqual(sent(get.call_args_list[1])["include_total"], "false")

    @patch("sawemapi.client.requests.get")
    def test_starting_offset_respected(self, get):
        """A starting offset is used for the first request."""
        get.side_effect = [page([9], 10, 5, False)]
        list(self.api.pages("A", "m", limit=5, offset=10))
        self.assertEqual(sent(get.call_args)["offset"], 10)

    @patch("sawemapi.client.requests.get")
    def test_paging_through_qry_param(self, get):
        """With a qry_param, paging continues in that form, keeping its other fields."""
        get.side_effect = [page([1], 0, 1, True), page([2], 1, 1, False)]
        list(self.api.pages("A", "m", qry_param='{"limit": 1, "return_type": "default"}'))
        first, second = (json.loads(sent(c)["qry_param"]) for c in get.call_args_list)
        self.assertEqual(first, {"limit": 1, "return_type": "default"})
        self.assertEqual(second, {"limit": 1, "return_type": "default", "offset": 1,
                                  "include_total": False})
        self.assertNotIn("limit", sent(get.call_args))

    def test_qry_param_and_flat_conflict(self):
        """qry_param can't be combined with limit/offset."""
        with self.assertRaises(ValueError):
            list(self.api.pages("A", "m", limit=5, qry_param={"limit": 1}))

    @patch("sawemapi.client.requests.get")
    def test_stops_without_progress(self, get):
        """A page reporting has_more with no usable limit ends the walk instead of looping."""
        get.return_value = page([1], 0, 0, True)
        self.assertEqual(len(list(self.api.pages("A", "m"))), 1)

    @patch("sawemapi.client.requests.get")
    def test_get_all_data(self, get):
        """get_all concatenates the data of every page."""
        get.side_effect = [page([1, 2], 0, 2, True), page([3], 2, 2, False)]
        self.assertEqual(self.api.get_all("A", "m", limit=2), [1, 2, 3])

    @patch("sawemapi.client.requests.get")
    def test_get_all_df(self, get):
        """get_all can return one DataFrame."""
        get.side_effect = [page([{"a": 1}], 0, 1, True), page([{"a": 2}], 1, 1, False)]
        frame = self.api.get_all("A", "m", return_type=ApiReturnType.df, limit=1)
        self.assertEqual(frame["a"].tolist(), [1, 2])

    def test_get_all_rejects_other_return_types(self):
        """Only data and df make sense for combined results."""
        with self.assertRaises(ValueError):
            self.api.get_all("A", "m", return_type=ApiReturnType.raw)
