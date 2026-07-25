"""
Regression tests for gmail_processor.utils.

Run with:  python -m unittest discover -s tests

Loaded directly from its file path (bypassing `import gmail_processor`) so
this test only needs the standard library: utils.py itself has no external
dependencies, but `gmail_processor/__init__.py` eagerly imports the Gmail/
Anthropic API clients, which would otherwise be required just to test
string-parsing helpers.
"""
import importlib.util
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "gmail_processor_utils",
    Path(__file__).resolve().parent.parent / "gmail_processor" / "utils.py",
)
_utils = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_utils)

get_header             = _utils.get_header
extract_email_address  = _utils.extract_email_address
is_safe_rule_value     = _utils.is_safe_rule_value


class GetHeaderTests(unittest.TestCase):
    def test_case_insensitive_match(self):
        headers = [{"name": "From", "value": "a@b.com"}]
        self.assertEqual(get_header(headers, "from"), "a@b.com")

    def test_missing_returns_empty_string(self):
        self.assertEqual(get_header([], "From"), "")

    def test_malformed_header_dicts_do_not_raise(self):
        # Real-world Gmail payloads are consistent, but header parsing must
        # not KeyError on a sparse/malformed dict (see fixed bug where
        # several modules used raw h["name"] indexing instead of .get()).
        headers = [{"value": "no name key"}, {"name": "Subject", "value": "hi"}]
        self.assertEqual(get_header(headers, "Subject"), "hi")


class ExtractEmailAddressTests(unittest.TestCase):
    def test_plain_address(self):
        self.assertEqual(extract_email_address("user@example.com"), "user@example.com")

    def test_display_name_with_angle_brackets(self):
        self.assertEqual(
            extract_email_address('"User" <user@example.com>'), "user@example.com"
        )

    def test_display_name_containing_nested_angle_brackets(self):
        # This is the bug several modules had: naive `split("<")[1]` grabs
        # the first "<...>" pair, which is the nickname, not the address.
        # extract_email_address uses rfind() to always take the *last* pair.
        raw = '"User <nickname>" <user@example.com>'
        self.assertEqual(extract_email_address(raw), "user@example.com")

    def test_empty_input(self):
        self.assertEqual(extract_email_address(""), "")

    def test_lowercases_result(self):
        self.assertEqual(extract_email_address("User@Example.COM"), "user@example.com")


class IsSafeRuleValueTests(unittest.TestCase):
    def test_accepts_typical_email(self):
        self.assertTrue(is_safe_rule_value("user@example.com"))

    def test_accepts_typical_label(self):
        self.assertTrue(is_safe_rule_value("Escuela"))
        self.assertTrue(is_safe_rule_value("Facturación"))

    def test_rejects_quote_breakout_attempt(self):
        self.assertFalse(is_safe_rule_value('x@x.com", "k": 1}'))

    def test_rejects_backslash(self):
        self.assertFalse(is_safe_rule_value("a\\b@example.com"))

    def test_rejects_newline(self):
        self.assertFalse(is_safe_rule_value("a@example.com\nimport os"))

    def test_rejects_empty_string(self):
        self.assertFalse(is_safe_rule_value(""))

    def test_rejects_non_string(self):
        self.assertFalse(is_safe_rule_value(None))


if __name__ == "__main__":
    unittest.main()
