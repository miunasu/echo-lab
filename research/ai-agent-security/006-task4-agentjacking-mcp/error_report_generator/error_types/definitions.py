"""Error type definitions and sample data for report generation."""

from __future__ import annotations

from typing import Any

# Supported error types and their default metadata
ERROR_TYPES: dict[str, dict[str, Any]] = {
    "runtime_error": {
        "description": "Unhandled runtime exception",
        "severity": "error",
        "default_message": "Unhandled runtime exception occurred",
        "default_stack_trace": (
            '  File "main.py", line 42, in process_user\n'
            "    result = user_service.get_profile(user_id)\n"
            '  File "user_service.py", line 18, in get_profile\n'
            "    return self.cache[user_id].name\n"
            "KeyError: user_id not found in cache"
        ),
        "default_context": {
            "module": "user_service",
            "function": "get_profile",
            "user_id": 123,
            "request_path": "/api/users/123",
        },
    },
    "database_error": {
        "description": "Database query or connection failure",
        "severity": "error",
        "default_message": "Database operation failed",
        "default_stack_trace": (
            '  File "db/repository.py", line 87, in fetch_orders\n'
            "    cursor.execute(sql, params)\n"
            '  File "db/connection.py", line 55, in execute\n'
            "    raise OperationalError(msg)\n"
            "psycopg2.OperationalError: connection timed out"
        ),
        "default_context": {
            "db_host": "db.internal",
            "db_name": "app_prod",
            "query": "SELECT * FROM orders WHERE user_id = %s",
            "timeout_ms": 5000,
            "retry_count": 2,
        },
    },
    "api_call_failure": {
        "description": "Outbound HTTP/API call failure",
        "severity": "error",
        "default_message": "External API call failed",
        "default_stack_trace": (
            '  File "clients/payment.py", line 64, in charge\n'
            "    response = session.post(url, json=payload, timeout=10)\n"
            '  File "httpx/_client.py", line 1144, in post\n'
            "    raise HTTPStatusError(...)\n"
            "httpx.HTTPStatusError: 503 Service Unavailable"
        ),
        "default_context": {
            "service": "payment_gateway",
            "method": "POST",
            "url": "https://api.payments.example/v1/charge",
            "status_code": 503,
            "request_id": "req_9f3a2c",
            "latency_ms": 10234,
        },
    },
    "permission_error": {
        "description": "Authorization or access control failure",
        "severity": "warning",
        "default_message": "Permission denied for requested resource",
        "default_stack_trace": (
            '  File "auth/guards.py", line 31, in require_role\n'
            "    raise PermissionError(f\"role {role} not allowed\")\n"
            "PermissionError: role viewer not allowed for action delete"
        ),
        "default_context": {
            "user_id": 456,
            "role": "viewer",
            "required_role": "admin",
            "resource": "orders",
            "action": "delete",
            "ip": "10.0.0.42",
        },
    },
    "validation_error": {
        "description": "Input validation failure",
        "severity": "warning",
        "default_message": "Request validation failed",
        "default_stack_trace": (
            '  File "api/schemas.py", line 22, in parse\n'
            "    return UserCreate(**payload)\n"
            "pydantic.ValidationError: 1 validation error for UserCreate\n"
            "email\n"
            "  value is not a valid email address"
        ),
        "default_context": {
            "endpoint": "/api/users",
            "field": "email",
            "provided_value": "not-an-email",
            "schema": "UserCreate",
        },
    },
    "timeout_error": {
        "description": "Operation exceeded time limit",
        "severity": "error",
        "default_message": "Operation timed out",
        "default_stack_trace": (
            '  File "workers/job_runner.py", line 101, in run\n'
            "    result = future.result(timeout=30)\n"
            "concurrent.futures.TimeoutError: job exceeded 30s limit"
        ),
        "default_context": {
            "job_name": "export_report",
            "timeout_sec": 30,
            "queue": "default",
            "worker_id": "worker-3",
        },
    },
    "network_error": {
        "description": "Network connectivity or DNS failure",
        "severity": "error",
        "default_message": "Network connection failed",
        "default_stack_trace": (
            '  File "net/client.py", line 19, in connect\n'
            "    sock.connect((host, port))\n"
            "OSError: [Errno 101] Network is unreachable"
        ),
        "default_context": {
            "host": "api.partner.example",
            "port": 443,
            "protocol": "https",
            "dns_resolved": False,
        },
    },
    "config_error": {
        "description": "Missing or invalid configuration",
        "severity": "critical",
        "default_message": "Invalid application configuration",
        "default_stack_trace": (
            '  File "config/loader.py", line 44, in load\n'
            "    raise ConfigError(f\"missing required key: {key}\")\n"
            "ConfigError: missing required key: DATABASE_URL"
        ),
        "default_context": {
            "config_file": "/etc/app/config.yaml",
            "missing_keys": ["DATABASE_URL"],
            "environment": "production",
        },
    },
}


def list_error_types() -> list[str]:
    """Return sorted list of supported error type keys."""
    return sorted(ERROR_TYPES.keys())


def get_error_definition(error_type: str) -> dict[str, Any]:
    """Return definition for an error type or raise KeyError."""
    if error_type not in ERROR_TYPES:
        supported = ", ".join(list_error_types())
        raise KeyError(f"Unknown error type '{error_type}'. Supported: {supported}")
    return ERROR_TYPES[error_type]