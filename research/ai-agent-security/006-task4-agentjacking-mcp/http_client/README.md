# HTTP Client Testing Tool

A lightweight CLI HTTP client for API testing, interface debugging, and automation scripts.

## Features

- Send HTTP requests: GET / POST / PUT / DELETE / PATCH / HEAD / OPTIONS
- Custom headers (Content-Type, Authorization, User-Agent, etc.)
- Custom body: JSON, form data, plain text
- Load body from file via `--body-file`
- Pretty-print JSON response body
- Show status code, response headers, and response body

## Requirements

```bash
pip install requests
```

## Usage

```bash
python http_client.py --url "https://api.example.com/endpoint" --method POST --headers '{"Content-Type": "application/json"}' --body '{"key": "value"}'
```

### Arguments

| Argument       | Required | Description                                              |
|----------------|----------|----------------------------------------------------------|
| `--url`        | Yes      | Target URL                                               |
| `--method`     | No       | HTTP method (default: GET)                               |
| `--headers`    | No       | Headers as JSON string                                   |
| `--body`       | No       | Request body string                                      |
| `--body-file`  | No       | Path to file with request body                           |
| `--timeout`    | No       | Timeout in seconds (default: 30)                         |
| `--no-pretty`  | No       | Disable JSON pretty-print                                |
| `--insecure`   | No       | Disable SSL certificate verification                     |

### Examples

**GET request**

```bash
python http_client.py --url "https://httpbin.org/get" --method GET
```

**POST with JSON body**

```bash
python http_client.py --url "https://httpbin.org/post" --method POST --headers "{\"Content-Type\": \"application/json\"}" --body "{\"key\": \"value\"}"
```

**POST with body from file**

```bash
python http_client.py --url "https://httpbin.org/post" --method POST --headers "{\"Content-Type\": \"application/json\"}" --body-file payload.json
```

**PUT with Authorization**

```bash
python http_client.py --url "https://httpbin.org/put" --method PUT --headers "{\"Authorization\": \"Bearer token\", \"Content-Type\": \"application/json\"}" --body "{\"name\": \"test\"}"
```

**DELETE**

```bash
python http_client.py --url "https://httpbin.org/delete" --method DELETE
```

## Output Example

```text
Status: 200 OK
Headers:
  Content-Type: application/json
  Server: nginx/1.18.0
Body:
{
  "success": true,
  "message": "Request processed"
}
```

## Exit Codes

| Code | Meaning                          |
|------|----------------------------------|
| 0    | Success (2xx / response.ok)      |
| 1    | Client/usage/network error       |
| 2    | HTTP response not OK (4xx/5xx)   |

## Project Layout

```text
http_client/
  http_client.py   # Main CLI tool
  payload.json     # Sample JSON body
  README.md        # This file
```