import json
import tempfile
import unittest
from pathlib import Path

from rubric.storage import SCHEMA_VERSION, Idea, Storage, StorageError


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
            status="pursuing",
            scores={"market_size": 4},
            reasons={"market_size": "big"},
        )
        self.storage.save([idea])
        [loaded] = self.storage.load()
        self.assertEqual(vars(loaded), vars(idea))

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


if __name__ == "__main__":
    unittest.main()
