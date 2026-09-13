"""Unit Tests for Language-Aware Error Parsers across Technology Stacks."""

from __future__ import annotations

import pytest
from opsgenome.signal.parsers import (
    JavaErrorParser,
    JavaScriptErrorParser,
    PythonErrorParser,
    TerraformErrorParser,
    parse_error,
)
from opsgenome.signal.stack_detector import detect_stack_from_command, is_target_tool


def test_python_traceback_parser():
    sample_traceback = """Traceback (most recent call last):
  File "/var/app/server.py", line 45, in handle_request
    response = process_order(order_payload)
  File "/var/app/pipeline.py", line 112, in process_order
    return init_payment_gateway(order_payload["gateway_config"])
  File "/var/app/checkout.py", line 17, in init_payment_gateway
    secret_key = gateway_config["api_secret_key"]
KeyError: 'api_secret_key'
"""
    parser = PythonErrorParser()
    parsed = parser.parse(sample_traceback)

    assert parsed is not None
    assert parsed["language"] == "python"
    assert parsed["exception_type"] == "KeyError"
    assert parsed["message"] == "'api_secret_key'"
    assert parsed["file"] == "/var/app/checkout.py"
    assert parsed["line"] == 17
    assert len(parsed["stack_frames"]) == 3
    # Deepest/most-relevant frame is first
    assert parsed["stack_frames"][0]["file"] == "/var/app/checkout.py"
    assert parsed["stack_frames"][0]["line"] == 17
    assert parsed["stack_frames"][0]["function"] == "init_payment_gateway"


def test_java_stack_trace_parser_with_caused_by_chain():
    sample_java_trace = """Exception in thread "main" com.example.billing.InvoiceProcessingException: Failed to generate monthly billing statement for customer CUST-9842
\tat com.example.billing.BillingService.processBillingRun(BillingService.java:18)
\tat com.example.billing.BillingService.main(BillingService.java:11)
Caused by: java.lang.NullPointerException: Cannot invoke "String.trim()" because "jurisdictionCode" is null
\tat com.example.billing.BillingService.calculateTaxAmount(BillingService.java:29)
\tat com.example.billing.BillingService.generateMonthlyStatement(BillingService.java:23)
\tat com.example.billing.BillingService.processBillingRun(BillingService.java:16)
\t... 1 more
"""
    parser = JavaErrorParser()
    parsed = parser.parse(sample_java_trace)

    assert parsed is not None
    assert parsed["language"] == "java"
    # Root cause takes precedence in Caused by: chain
    assert parsed["exception_type"] == "java.lang.NullPointerException"
    assert parsed["message"] == 'Cannot invoke "String.trim()" because "jurisdictionCode" is null'
    assert parsed["file"] == "BillingService.java"
    assert parsed["line"] == 29
    assert len(parsed["stack_frames"]) == 5
    # First frame of root cause is deepest frame
    assert parsed["stack_frames"][0]["file"] == "BillingService.java"
    assert parsed["stack_frames"][0]["line"] == 29
    assert "calculateTaxAmount" in parsed["stack_frames"][0]["function"]


def test_java_stack_trace_parser_single_exception():
    sample_trace = """Exception in thread "main" java.lang.NullPointerException: Cannot invoke "String.toLowerCase()" because "val" is null
\tat com.example.billing.Invoice.calculate(Invoice.java:42)
\tat com.example.billing.Main.main(Main.java:15)
"""
    parser = JavaErrorParser()
    parsed = parser.parse(sample_trace)

    assert parsed is not None
    assert parsed["language"] == "java"
    assert parsed["exception_type"] == "java.lang.NullPointerException"
    assert parsed["message"] == 'Cannot invoke "String.toLowerCase()" because "val" is null'
    assert parsed["file"] == "Invoice.java"
    assert parsed["line"] == 42
    assert len(parsed["stack_frames"]) == 2
    assert parsed["stack_frames"][0]["file"] == "Invoice.java"
    assert parsed["stack_frames"][0]["line"] == 42


def test_javascript_v8_parser():
    sample_node_trace = """TypeError: Cannot read properties of undefined (reading 'authorization')
    at parseBearerToken (/Users/app/demo-projects/svc-auth/auth.js:11:24)
    at handleIncomingRequest (/Users/app/demo-projects/svc-auth/auth.js:6:12)
    at main (/Users/app/demo-projects/svc-auth/auth.js:21:5)
    at Object.<anonymous> (/Users/app/demo-projects/svc-auth/auth.js:24:1)
"""
    parser = JavaScriptErrorParser()
    parsed = parser.parse(sample_node_trace)

    assert parsed is not None
    assert parsed["language"] == "javascript"
    assert parsed["exception_type"] == "TypeError"
    assert parsed["message"] == "Cannot read properties of undefined (reading 'authorization')"
    assert parsed["file"] == "/Users/app/demo-projects/svc-auth/auth.js"
    assert parsed["line"] == 11
    assert len(parsed["stack_frames"]) == 4
    assert parsed["stack_frames"][0]["line"] == 11
    assert parsed["stack_frames"][0]["function"] == "parseBearerToken"


def test_terraform_error_parser_with_line_number():
    sample_tf_error = """Error: Missing required argument

  on main.tf line 14, in resource "aws_vpc" "primary":
  14:   cidr_block = var.vpc_cidr

The argument "cidr_block" is required, but was not set.
"""
    parser = TerraformErrorParser()
    parsed = parser.parse(sample_tf_error)

    assert parsed is not None
    assert parsed["language"] == "terraform"
    assert parsed["exception_type"] == "Missing required argument"
    assert parsed["file"] == "main.tf"
    assert parsed["line"] == 14
    assert "cidr_block" in parsed["message"]
    assert len(parsed["stack_frames"]) == 1
    assert parsed["stack_frames"][0]["function"] == 'resource "aws_vpc" "primary"'


def test_terraform_error_parser_without_line_number():
    # Demonstrates honest reporting of null line number rather than fabrication
    sample_tf_error = """Error: No value for required variable

The root module input variable "environment" is not set, and has no default
value. Use a -var or -var-file command line argument to provide a value.
"""
    parser = TerraformErrorParser()
    parsed = parser.parse(sample_tf_error)

    assert parsed is not None
    assert parsed["language"] == "terraform"
    assert parsed["exception_type"] == "No value for required variable"
    assert parsed["line"] is None  # CRITICAL: Honest null, not fabricated


def test_stack_and_target_tool_detection():
    assert detect_stack_from_command("python3 checkout.py") == "python"
    assert detect_stack_from_command("python order.py") == "python"
    assert detect_stack_from_command("pytest tests/") == "python"
    assert detect_stack_from_command("java BillingService.java") == "java"
    assert detect_stack_from_command("java -jar billing.jar") == "java"
    assert detect_stack_from_command("mvn clean test") == "java"
    assert detect_stack_from_command("node auth.js") == "javascript"
    assert detect_stack_from_command("npm test") == "javascript"
    assert detect_stack_from_command("terraform plan") == "terraform"
    assert detect_stack_from_command("go run main.go") == "go"
    assert detect_stack_from_command("cargo build") == "rust"
    assert detect_stack_from_command("kubectl get pods") == "kubernetes"

    assert is_target_tool("python3") is True
    assert is_target_tool("java") is True
    assert is_target_tool("node") is True
    assert is_target_tool("terraform") is True
    assert is_target_tool("kubectl") is True
    assert is_target_tool("ls") is False
