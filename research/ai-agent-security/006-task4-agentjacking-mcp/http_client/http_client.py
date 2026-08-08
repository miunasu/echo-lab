#!/usr/bin/env python3
"""HTTP Client Testing Tool

A simple CLI tool for API testing and interface debugging.
Supports GET/POST/PUT/DELETE with custom headers and body.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional, Tuple

try:
    import requests
except ImportError:
    print("Error: 'requests' library is required. Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


SUPPORTED_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")


def parse_headers(headers_str: Optional[str]) -> Dict[str, str]:
    """Parse headers from JSON string."""
    if not headers_str:
        return {}
    try:
        headers = json.loads(headers_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid headers JSON: {exc}") from exc
    if not isinstance(headers, dict):
        raise ValueError("Headers must be a JSON object")
    return {str(k): str(v) for k, v in headers.items()}


def load_body(body: Optional[str], body_file: Optional[str]) -> Tuple[Optional[Any], Optional[str]]:
    """Load request body from --body or --body-file.

    Returns:
        (data, raw_text): data is used when Content-Type is JSON and body is valid JSON;
        raw_text is the original string content for text/form bodies.
    """
    if body and body_file:
        raise ValueError("Use either --body or --body-file, not both")

    raw: Optional[str] = None
    if body_file:
        try:
            with open(body_file, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as exc:
            raise ValueError(f"Failed to read body file '{body_file}': {exc}") from exc
    elif body is not None:
        raw = body

    if raw is None:
        return None, None

    # Try parse as JSON; keep raw string as fallback
    try:
        return json.loads(raw), raw
    except json.JSONDecodeError:
        return None, raw


def build_request_kwargs(
    method: str,
    headers: Dict[str, str],
    data: Optional[Any],
    raw: Optional[str],
    timeout: float,
) -> Dict[str, Any]:
    """Build kwargs for requests.request based on body and Content-Type."""
    kwargs: Dict[str, Any] = {
        "headers": headers,
        "timeout": timeout,
        "allow_redirects": True,
    }

    if raw is None and data is None:
        return kwargs

    content_type = ""
    for key, value in headers.items():
        if key.lower() == "content-type":
            content_type = value.lower()
            break

    # Prefer json= for JSON content
    if data is not None and (
        "application/json" in content_type
        or (not content_type and isinstance(data, (dict, list)))
    ):
        kwargs["json"] = data
        # Ensure Content-Type is set if missing
        if not content_type:
            headers.setdefault("Content-Type", "application/json")
        return kwargs

    # Form-urlencoded: accept dict as form fields
    if "application/x-www-form-urlencoded" in content_type and isinstance(data, dict):
        kwargs["data"] = data
        return kwargs

    # Multipart form data
    if "multipart/form-data" in content_type and isinstance(data, dict):
        # Let requests set boundary; remove explicit multipart header
        headers_copy = {
            k: v for k, v in headers.items() if k.lower() != "content-type"
        }
        kwargs["headers"] = headers_copy
        kwargs["files"] = {k: (None, str(v)) for k, v in data.items()}
        return kwargs

    # Default: send raw string / bytes as body
    if raw is not None:
        kwargs["data"] = raw.encode("utf-8") if isinstance(raw, str) else raw
    elif data is not None:
        kwargs["json"] = data
        headers.setdefault("Content-Type", "application/json")

    return kwargs


def format_response(response: requests.Response, pretty: bool = True) -> str:
    """Format HTTP response for display."""
    lines = []
    reason = response.reason or ""
    lines.append(f"Status: {response.status_code} {reason}".rstrip())
    lines.append("Headers:")
    for key, value in response.headers.items():
        lines.append(f"  {key}: {value}")

    lines.append("Body:")
    body_text = response.text
    if not body_text:
        lines.append("(empty)")
        return "\n".join(lines)

    if pretty:
        content_type = response.headers.get("Content-Type", "").lower()
        if "application/json" in content_type or body_text.lstrip().startswith(("{", "[")):
            try:
                parsed = response.json()
                lines.append(json.dumps(parsed, indent=2, ensure_ascii=False))
                return "\n".join(lines)
            except (ValueError, json.JSONDecodeError):
                pass

    lines.append(body_text)
    return "\n".join(lines)


def send_request(
    url: str,
    method: str,
    headers: Dict[str, str],
    data: Optional[Any],
    raw: Optional[str],
    timeout: float,
) -> requests.Response:
    """Send HTTP request and return response."""
    method = method.upper()
    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unsupported method: {method}. Supported: {', '.join(SUPPORTED_METHODS)}")

    kwargs = build_request_kwargs(method, headers, data, raw, timeout)
    return requests.request(method, url, **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="http_client.py",
        description="HTTP Client Testing Tool - send HTTP requests for API testing and debugging",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python http_client.py --url "https://httpbin.org/get" --method GET
  python http_client.py --url "https://httpbin.org/post" --method POST \\
      --headers '{"Content-Type": "application/json"}' \\
      --body '{"key": "value"}'
  python http_client.py --url "https://httpbin.org/post" --method POST \\
      --headers '{"Content-Type": "application/json"}' \\
      --body-file payload.json
  python http_client.py --url "https://httpbin.org/put" --method PUT \\
      --headers '{"Authorization": "Bearer token", "Content-Type": "application/json"}' \\
      --body '{"name": "test"}'
        """,
    )
    parser.add_argument(
        "--url",
        required=True,
        help="Target URL for the HTTP request",
    )
    parser.add_argument(
        "--method",
        default="GET",
        choices=SUPPORTED_METHODS,
        help="HTTP method (default: GET)",
    )
    parser.add_argument(
        "--headers",
        default=None,
        help='Custom headers as JSON string, e.g. \'{"Content-Type": "application/json"}\'',
    )
    parser.add_argument(
        "--body",
        default=None,
        help="Request body as string (JSON, form data, or plain text)",
    )
    parser.add_argument(
        "--body-file",
        default=None,
        dest="body_file",
        help="Path to file containing request body content",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--no-pretty",
        action="store_true",
        help="Disable pretty-printing of JSON response body",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable SSL certificate verification",
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        headers = parse_headers(args.headers)
        data, raw = load_body(args.body, args.body_file)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        kwargs_extra: Dict[str, Any] = {}
        if args.insecure:
            kwargs_extra["verify"] = False
            # Suppress InsecureRequestWarning for cleaner output
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass

        method = args.method.upper()
        req_kwargs = build_request_kwargs(method, headers, data, raw, args.timeout)
        req_kwargs.update(kwargs_extra)

        response = requests.request(method, args.url, **req_kwargs)
        print(format_response(response, pretty=not args.no_pretty))
        return 0 if response.ok else 2
    except requests.exceptions.Timeout:
        print(f"Error: Request timed out after {args.timeout}s", file=sys.stderr)
        return 1
    except requests.exceptions.ConnectionError as exc:
        print(f"Error: Connection failed: {exc}", file=sys.stderr)
        return 1
    except requests.exceptions.RequestException as exc:
        print(f"Error: Request failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())