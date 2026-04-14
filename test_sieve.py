"""Tests for sieve_client.py — unit tests for build_sieve_script + integration tests against live server."""

import asyncio
import json
import os
import pytest

from sieve_client import build_sieve_script

# ---------------------------------------------------------------------------
# Unit tests: build_sieve_script (no network)
# ---------------------------------------------------------------------------


class TestBuildSieveScript:
    def test_single_from_fileinto(self):
        script = build_sieve_script([{
            "conditions": [{"field": "from", "contains": "spam@example.com"}],
            "actions": [{"type": "fileinto", "folder": "Junk"}, {"type": "stop"}],
        }])
        assert 'require "fileinto";' in script
        assert 'header :contains "From" "spam@example.com"' in script
        assert 'fileinto "Junk";' in script
        assert "stop;" in script

    def test_single_subject_discard(self):
        script = build_sieve_script([{
            "conditions": [{"field": "subject", "contains": "Buy now"}],
            "actions": [{"type": "discard"}],
        }])
        assert "fileinto" not in script  # no require fileinto
        assert 'header :contains "Subject" "Buy now"' in script
        assert "discard;" in script

    def test_body_condition_adds_require(self):
        script = build_sieve_script([{
            "conditions": [{"field": "body", "contains": "unsubscribe"}],
            "actions": [{"type": "keep"}],
        }])
        assert 'require "body";' in script
        assert 'body :contains "unsubscribe"' in script

    def test_multiple_conditions_allof(self):
        script = build_sieve_script([{
            "conditions": [
                {"field": "from", "contains": "boss@work.com"},
                {"field": "subject", "contains": "urgent"},
            ],
            "match": "all",
            "actions": [{"type": "addflag", "flags": "\\\\Flagged"}, {"type": "keep"}],
        }])
        assert "allof" in script
        assert 'require "imap4flags";' in script

    def test_multiple_conditions_anyof(self):
        script = build_sieve_script([{
            "conditions": [
                {"field": "from", "contains": "alice@example.com"},
                {"field": "from", "contains": "bob@example.com"},
            ],
            "match": "any",
            "actions": [{"type": "fileinto", "folder": "Friends"}],
        }])
        assert "anyof" in script

    def test_no_conditions_uses_true(self):
        script = build_sieve_script([{
            "conditions": [],
            "actions": [{"type": "keep"}],
        }])
        assert "if true {" in script

    def test_redirect_action(self):
        script = build_sieve_script([{
            "conditions": [{"field": "to", "contains": "old@example.com"}],
            "actions": [{"type": "redirect", "address": "new@example.com"}],
        }])
        assert 'redirect "new@example.com";' in script

    def test_reject_action(self):
        script = build_sieve_script([{
            "conditions": [{"field": "from", "contains": "blocked@spam.com"}],
            "actions": [{"type": "reject", "reason": "Go away"}],
        }])
        assert 'require "reject";' in script
        assert 'reject "Go away";' in script

    def test_vacation_action(self):
        script = build_sieve_script([{
            "conditions": [{"field": "to", "contains": "me@example.com"}],
            "actions": [{"type": "vacation", "subject": "OOO", "body": "I am on vacation."}],
        }])
        assert 'require "vacation";' in script
        assert 'vacation :subject "OOO" "I am on vacation.";' in script

    def test_custom_header(self):
        script = build_sieve_script([{
            "conditions": [{"field": "header", "header_name": "X-Mailer", "contains": "PHPMailer"}],
            "actions": [{"type": "fileinto", "folder": "Suspect"}],
        }])
        assert 'header :contains "X-Mailer" "PHPMailer"' in script

    def test_multiple_rules(self):
        script = build_sieve_script([
            {
                "name": "Rule one",
                "conditions": [{"field": "from", "contains": "a@a.com"}],
                "actions": [{"type": "fileinto", "folder": "A"}, {"type": "stop"}],
            },
            {
                "name": "Rule two",
                "conditions": [{"field": "from", "contains": "b@b.com"}],
                "actions": [{"type": "fileinto", "folder": "B"}, {"type": "stop"}],
            },
        ])
        assert "# Rule one" in script
        assert "# Rule two" in script
        assert script.count("fileinto") == 3  # require + two fileinto actions
        # single require at top
        assert script.count('require "fileinto";') == 1

    def test_multiple_requires_sorted(self):
        script = build_sieve_script([{
            "conditions": [{"field": "body", "contains": "x"}],
            "actions": [
                {"type": "reject", "reason": "no"},
                {"type": "fileinto", "folder": "X"},
            ],
        }])
        lines = script.strip().split("\n")
        require_lines = [l for l in lines if l.startswith("require")]
        # should be sorted: body, fileinto, reject
        assert require_lines == [
            'require "body";',
            'require "fileinto";',
            'require "reject";',
        ]

    def test_escaping_quotes_in_value(self):
        script = build_sieve_script([{
            "conditions": [{"field": "subject", "contains": 'say "hello"'}],
            "actions": [{"type": "keep"}],
        }])
        assert r'say \"hello\"' in script

    def test_flag_action(self):
        script = build_sieve_script([{
            "conditions": [{"field": "from", "contains": "vip@company.com"}],
            "actions": [{"type": "flag", "flags": "\\\\Seen"}],
        }])
        assert 'require "imap4flags";' in script
        assert 'setflag' in script

    def test_single_condition_no_allof_anyof(self):
        script = build_sieve_script([{
            "conditions": [{"field": "from", "contains": "x@x.com"}],
            "actions": [{"type": "keep"}],
        }])
        assert "allof" not in script
        assert "anyof" not in script


# ---------------------------------------------------------------------------
# Integration tests: real ManageSieve server (skip if env not set)
# ---------------------------------------------------------------------------

HAVE_ENV = bool(os.environ.get("EMAIL_USER"))


@pytest.mark.skipif(not HAVE_ENV, reason="EMAIL_USER not set — no live server")
class TestSieveIntegration:
    """Integration tests against the live ManageSieve server.

    Run with:
        source .env && pytest test_sieve.py -v -k Integration
    """

    SCRIPT_NAME = "_pytest_test_script"

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    # -- cleanup helper --
    def _cleanup(self):
        import sieve_client
        try:
            self._run(sieve_client.deactivate_scripts("a"))
        except Exception:
            pass
        try:
            self._run(sieve_client.delete_script(self.SCRIPT_NAME, "a"))
        except Exception:
            pass

    def setup_method(self):
        self._cleanup()

    def teardown_method(self):
        self._cleanup()

    def test_list_scripts_returns_list(self):
        import sieve_client
        scripts = self._run(sieve_client.list_scripts("a"))
        assert isinstance(scripts, list)

    def test_put_get_delete_script(self):
        import sieve_client
        content = 'require "fileinto";\nif header :contains "From" "test" {\n  fileinto "Junk";\n}\n'

        # put
        result = self._run(sieve_client.put_script(self.SCRIPT_NAME, content, "a"))
        assert "uploaded" in result

        # list — should contain our script
        scripts = self._run(sieve_client.list_scripts("a"))
        names = [s["name"] for s in scripts]
        assert self.SCRIPT_NAME in names

        # get — content should match
        fetched = self._run(sieve_client.get_script(self.SCRIPT_NAME, "a"))
        assert "fileinto" in fetched
        assert "test" in fetched

        # delete
        result = self._run(sieve_client.delete_script(self.SCRIPT_NAME, "a"))
        assert "deleted" in result

        # list — should be gone
        scripts = self._run(sieve_client.list_scripts("a"))
        names = [s["name"] for s in scripts]
        assert self.SCRIPT_NAME not in names

    def test_activate_deactivate(self):
        import sieve_client
        content = 'keep;\n'

        self._run(sieve_client.put_script(self.SCRIPT_NAME, content, "a"))

        # activate
        result = self._run(sieve_client.activate_script(self.SCRIPT_NAME, "a"))
        assert "activated" in result

        scripts = self._run(sieve_client.list_scripts("a"))
        active = [s for s in scripts if s["name"] == self.SCRIPT_NAME]
        assert active[0]["active"] is True

        # deactivate
        result = self._run(sieve_client.deactivate_scripts("a"))
        assert "deactivated" in result.lower()

        scripts = self._run(sieve_client.list_scripts("a"))
        active = [s for s in scripts if s["name"] == self.SCRIPT_NAME]
        assert active[0]["active"] is False

    def test_create_filter_e2e(self):
        import sieve_client
        rules = [
            {
                "name": "Pytest rule",
                "conditions": [{"field": "from", "contains": "pytest@example.com"}],
                "actions": [{"type": "fileinto", "folder": "Junk"}, {"type": "stop"}],
            }
        ]
        result = self._run(sieve_client.create_filter(self.SCRIPT_NAME, rules, activate=True, account="a"))
        assert "uploaded and activated" in result
        assert "fileinto" in result

        # verify it's active
        scripts = self._run(sieve_client.list_scripts("a"))
        active = [s for s in scripts if s["name"] == self.SCRIPT_NAME and s["active"]]
        assert len(active) == 1

    def test_create_filter_no_activate(self):
        import sieve_client
        rules = [{"conditions": [], "actions": [{"type": "keep"}]}]
        result = self._run(sieve_client.create_filter(self.SCRIPT_NAME, rules, activate=False, account="a"))
        assert "uploaded" in result
        assert "activated" not in result.split("\n")[0]

    def test_delete_active_script_fails(self):
        import sieve_client
        content = 'keep;\n'
        self._run(sieve_client.put_script(self.SCRIPT_NAME, content, "a"))
        self._run(sieve_client.activate_script(self.SCRIPT_NAME, "a"))

        with pytest.raises(Exception, match="DELETESCRIPT failed"):
            self._run(sieve_client.delete_script(self.SCRIPT_NAME, "a"))

    def test_get_nonexistent_script_fails(self):
        import sieve_client
        with pytest.raises(Exception, match="GETSCRIPT failed"):
            self._run(sieve_client.get_script("_no_such_script_ever_", "a"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
