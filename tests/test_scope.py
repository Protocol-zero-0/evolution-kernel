"""Edge-case tests for ``evolution_kernel.scope.check_scope``.

The acceptance suite already covers the happy / unhappy paths through the
Governor. This file pins down the matcher itself so regressions in the
``allowed_paths`` semantics are caught locally:

* directory entries (``src/``) match files **recursively** under that prefix,
* file entries match by **exact** path,
* a directory prefix must not collide with a sibling whose name starts with
  the same letters (``src/`` does not match ``src.txt`` or ``srcfoo``),
* ``..`` traversal segments are rejected even if a prefix would match,
* the empty scope means "no mutation is allowed at all" (used by the
  hard-stop acceptance test).
"""

from __future__ import annotations

import unittest

from evolution_kernel.scope import check_scope


class ScopeMatcherTests(unittest.TestCase):
    def test_directory_prefix_matches_files_recursively(self):
        report = check_scope(
            ["src/a.py", "src/sub/b.py", "src/sub/deep/c.py"],
            ["src/"],
        )
        self.assertTrue(report.ok, report.violations)
        self.assertEqual(report.violations, ())

    def test_directory_prefix_does_not_match_sibling_with_same_letters(self):
        # `src/` must NOT accept `src.txt` or `srcfoo/x.py` — that would be a
        # silent scope-leak bug.
        report = check_scope(
            ["src.txt", "srcfoo/x.py", "src/ok.py"],
            ["src/"],
        )
        self.assertFalse(report.ok)
        self.assertIn("src.txt", report.violations)
        self.assertIn("srcfoo/x.py", report.violations)
        self.assertNotIn("src/ok.py", report.violations)

    def test_exact_file_match(self):
        report = check_scope(
            ["EVOLUTION_MARKER.txt", "README.md"],
            ["EVOLUTION_MARKER.txt"],
        )
        self.assertFalse(report.ok)
        self.assertEqual(report.violations, ("README.md",))

    def test_exact_file_match_does_not_act_as_prefix(self):
        # `src` (no trailing slash) is a file rule, not a directory rule, so
        # `src/foo.py` must NOT match. Authors who want recursion have to
        # write `src/`.
        report = check_scope(["src/foo.py"], ["src"])
        self.assertFalse(report.ok)
        self.assertEqual(report.violations, ("src/foo.py",))

    def test_parent_traversal_is_rejected(self):
        # Even if the prefix "src/" would technically match
        # "src/../etc/passwd", the path contains ".." and must be rejected.
        report = check_scope(["src/../etc/passwd"], ["src/"])
        self.assertFalse(report.ok)
        self.assertEqual(report.violations, ("src/../etc/passwd",))

    def test_dot_slash_is_normalized(self):
        # `git diff --name-only` never emits leading "./", but normalisation
        # is cheap insurance against the executor reporting odd paths.
        report = check_scope(["./src/a.py"], ["src/"])
        self.assertTrue(report.ok)

    def test_empty_allowed_means_no_mutation_allowed(self):
        empty_change = check_scope([], [])
        self.assertTrue(empty_change.ok)
        any_change = check_scope(["whatever.txt"], [])
        self.assertFalse(any_change.ok)
        self.assertEqual(any_change.violations, ("whatever.txt",))

    def test_mixed_directory_and_file_rules(self):
        report = check_scope(
            ["src/a.py", "VERSION", "docs/x.md"],
            ["src/", "VERSION"],
        )
        self.assertFalse(report.ok)
        self.assertEqual(report.violations, ("docs/x.md",))


if __name__ == "__main__":
    unittest.main()
