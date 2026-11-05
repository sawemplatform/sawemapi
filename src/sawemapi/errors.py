"""Exceptions and warnings raised by the client."""
import json


class ApiWarning(UserWarning):
    """The API returned a warning in its envelope, e.g. a deprecation notice."""


class ApiError(Exception):
    """The API answered with an error status.

    Attributes:
        status_code (int): The HTTP status code.
        message (str): The server's ``message`` field when the body is a JSON object
            that has one, otherwise the ``errors`` list joined, otherwise the body.
        errors (list[str]): The server's ``errors`` list, empty if there is none.
        response (requests.Response): The full response.
    """

    def __init__(self, response):
        self.response = response
        self.status_code = response.status_code
        self.message, self.errors = self._parse(response)
        super().__init__(f"{self.status_code}: {self.message}")

    @staticmethod
    def _parse(response):
        """Extract (message, errors) from `response`, falling back to its body."""
        try:
            body = json.loads(response.text)
        except (ValueError, TypeError):
            return response.text, []
        if not isinstance(body, dict):
            return response.text, []
        errors = [str(e) for e in body.get("errors") or []]
        message = body.get("message")
        if message:
            return str(message), errors
        if errors:
            return "; ".join(errors), errors
        return response.text, errors
