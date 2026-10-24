import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from rubric import apikey
from rubric.apikey import ApiKeyError, delete_key, get_key, set_key, valid_key

KEY = "sk-ant-api03-abc_DEF-123"


class FakeSecurity:
    """Stands in for the `security` tool: records calls, returns a canned status."""

    def __init__(self, returncode=0, stdout=""):
        self.calls = []
        self.returncode, self.stdout = returncode, stdout

    def __call__(self, args, stdin=None):
        self.calls.append((args, stdin))
        return subprocess.CompletedProcess(args, self.returncode, self.stdout, "")


class KeyFormatTests(unittest.TestCase):
    def test_accepts_real_looking_keys(self):
        self.assertTrue(valid_key(KEY))

    def test_rejects_empty_spaces_and_quotes(self):
        for bad in ("", "a b", 'a"b', "a'b", "a;b", "a\nb"):
            self.assertFalse(valid_key(bad), bad)


class KeychainTests(unittest.TestCase):
    def test_env_var_wins_without_touching_keychain(self):
        run = FakeSecurity(stdout="from-keychain\n")
        key = get_key("darwin", {apikey.ENV_VAR: f" {KEY} "}, run=run)
        self.assertEqual(key, KEY)
        self.assertEqual(run.calls, [])

    def test_reads_from_keychain(self):
        run = FakeSecurity(stdout=KEY + "\n")
        self.assertEqual(get_key("darwin", {}, run=run), KEY)
        args, _ = run.calls[0]
        self.assertIn("find-generic-password", args)
        self.assertIn("-w", args)

    def test_missing_item_is_none(self):
        self.assertIsNone(get_key("darwin", {}, run=FakeSecurity(apikey.NOT_FOUND)))

    def test_other_failure_raises(self):
        with self.assertRaises(ApiKeyError):
            get_key("darwin", {}, run=FakeSecurity(1))

    def test_set_passes_key_on_stdin_not_in_arguments(self):
        run = FakeSecurity()
        set_key(KEY, "darwin", {}, run=run)
        args, stdin = run.calls[0]
        self.assertEqual(args, [apikey.SECURITY, "-i"])
        self.assertNotIn(KEY, " ".join(args))
        self.assertIn(f"-w {KEY}", stdin)
        self.assertIn("-U", stdin)  # update in place if one exists

    def test_set_rejects_bad_key_before_running_anything(self):
        run = FakeSecurity()
        with self.assertRaises(ApiKeyError):
            set_key('bad key"', "darwin", {}, run=run)
        self.assertEqual(run.calls, [])

    def test_set_failure_raises_without_leaking_key(self):
        with self.assertRaises(ApiKeyError) as cm:
            set_key(KEY, "darwin", {}, run=FakeSecurity(1))
        self.assertNotIn(KEY, str(cm.exception))

    def test_delete_missing_item_is_fine(self):
        delete_key("darwin", {}, run=FakeSecurity(apikey.NOT_FOUND))

    def test_delete_failure_raises(self):
        with self.assertRaises(ApiKeyError):
            delete_key("darwin", {}, run=FakeSecurity(1))


class FileFallbackTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)

    def args(self):
        return {"platform": "linux", "env": {}, "home": self.home}

    def test_no_key_is_none(self):
        self.assertIsNone(get_key(**self.args()))

    @unittest.skipUnless(os.name == "posix", "Windows has no POSIX file modes")
    def test_round_trip_and_private_mode(self):
        set_key(KEY, **self.args())
        self.assertEqual(get_key(**self.args()), KEY)
        path = self.home / ".local" / "share" / "rubric" / apikey.KEY_FILE
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    @unittest.skipUnless(os.name == "posix", "Windows has no POSIX file modes")
    def test_overwrite_tightens_an_open_file(self):
        set_key(KEY, **self.args())
        path = self.home / ".local" / "share" / "rubric" / apikey.KEY_FILE
        path.chmod(0o644)
        set_key(KEY + "2", **self.args())
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(get_key(**self.args()), KEY + "2")

    def test_delete(self):
        set_key(KEY, **self.args())
        delete_key(**self.args())
        self.assertIsNone(get_key(**self.args()))
        delete_key(**self.args())  # already gone: fine


if __name__ == "__main__":
    unittest.main()
