"""
Conftest for document splitter tests.

These tests are self-contained and do not need a database or HTTP client.
This conftest intentionally stays empty to prevent the parent conftest.py
(which requires PostgreSQL) from being loaded for this test file.
"""
