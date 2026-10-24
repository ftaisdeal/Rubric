import json
import tempfile
import unittest
from pathlib import Path

from rubric.storage import SCHEMA_VERSION, Idea, Storage, StorageError, data_dir


class StorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "sub" / "ideas.json"
        self.storage = Storage(self.path)

    def test_missing_file_loads_empty(self):
        self.assertEqual(self.storage.load(), [])

    def test_round_trip(self):
        idea = Idea(
            name="Widget",
            description="d",
            strengths="s",
            weaknesses="w",
            opportunities="o",
            threats="t",
            status="pursuing",
            scores={"market_size": 4},
            reasons={"market_size": "big"},
        )
        self.storage.save([idea])
        [loaded] = self.storage.load()
        self.assertEqual(vars(loaded), vars(idea))

    def test_old_file_without_swot_loads_with_empty_defaults(self):
        self.storage.save([Idea(name="old")])
        data = json.loads(self.path.read_text())
        for f in ("strengths", "weaknesses", "opportunities", "threats"):
            del data["ideas"][0][f]
        self.path.write_text(json.dumps(data))
        [loaded] = self.storage.load()
        self.assertEqual(
            (loaded.strengths, loaded.weaknesses, loaded.opportunities, loaded.threats),
            ("", "", "", ""),
        )

    def test_writes_schema_version(self):
        self.storage.save([])
        data = json.loads(self.path.read_text())
        self.assertEqual(data["schema_version"], SCHEMA_VERSION)

    def test_backup_keeps_previous_version(self):
        self.storage.save([Idea(name="one")])
        self.storage.save([Idea(name="one"), Idea(name="two")])
        backup = json.loads(self.storage.backup_path.read_text())
        self.assertEqual([i["name"] for i in backup["ideas"]], ["one"])

    def test_no_temp_files_left_behind(self):
        self.storage.save([Idea(name="x")])
        self.storage.save([Idea(name="y")])
        names = sorted(p.name for p in self.path.parent.iterdir())
        self.assertEqual(names, ["ideas.json", "ideas.json.bak"])

    def test_corrupt_file_raises_and_is_untouched(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json")
        with self.assertRaises(StorageError):
            self.storage.load()
        self.assertEqual(self.path.read_text(), "{not json")

    def test_wrong_shape_raises(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"schema_version": 1, "ideas": {}}')
        with self.assertRaises(StorageError):
            self.storage.load()

    def test_newer_schema_raises(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"schema_version": 999, "ideas": []}))
        with self.assertRaises(StorageError):
            self.storage.load()

    def test_unknown_criterion_ids_survive_round_trip(self):
        self.storage.save([Idea(name="a", scores={"gone": 3})])
        [loaded] = self.storage.load()
        self.assertEqual(loaded.scores, {"gone": 3})


class DataDirTests(unittest.TestCase):
    home = Path("/home/u")

    def test_macos(self):
        self.assertEqual(
            data_dir("darwin", {}, self.home),
            self.home / "Library" / "Application Support" / "Rubric",
        )

    def test_windows_uses_appdata(self):
        self.assertEqual(
            data_dir("win32", {"APPDATA": "C:/Users/u/AppData/Roaming"}, self.home),
            Path("C:/Users/u/AppData/Roaming") / "Rubric",
        )

    def test_windows_without_appdata(self):
        self.assertEqual(
            data_dir("win32", {}, self.home),
            self.home / "AppData" / "Roaming" / "Rubric",
        )

    def test_linux_default(self):
        self.assertEqual(
            data_dir("linux", {}, self.home), self.home / ".local" / "share" / "rubric"
        )

    def test_linux_xdg_data_home(self):
        self.assertEqual(
            data_dir("linux", {"XDG_DATA_HOME": "/x/data"}, self.home),
            Path("/x/data/rubric"),
        )

    def test_linux_ignores_relative_xdg(self):
        self.assertEqual(
            data_dir("linux", {"XDG_DATA_HOME": "rel"}, self.home),
            self.home / ".local" / "share" / "rubric",
        )


if __name__ == "__main__":
    unittest.main()
