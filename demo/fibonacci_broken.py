#!/usr/bin/env python3
"""Broken Fibonacci Sequence Demo for OpsGenome AI Auto-Fix.

Bug: Missing termination base cases (n <= 0, n == 1).
When executed, this triggers an immediate RecursionError in the Python runtime.
OpsGenome will capture the failure, invoke Gemini (or deterministic heuristics),
generate the fix, patch the file, and re-run to verify recovery.
"""

def fib(n):
    if n <= 0:
        return 0
    if n == 1:
        return 1
    # BUG: Missing base termination cases!
    return fib(n - 1) + fib(n - 2)

if __name__ == "__main__":
    print("Generating Fibonacci sequence for n=0..6:")
    results = [fib(i) for i in range(7)]
    print(f"Fibonacci Series: {results}")
