# Rubric

A small desktop app for scoring and comparing business ideas against a weighted rubric. Rate each idea from 1 to 5 on criteria such as market size, competition and founder fit, and explain each score. Criteria carry default percentage weights, which you can override per idea. Ideas are ranked by weighted total and shown side by side, with a small bar chart beside each total for visual comparison.

## Features

- Comparison table of all ideas with weighted total scores
- Per-criterion scores, with a description of what each level means
- Written reasons for each score
- Per-idea weight overrides
- Status tracking (considering, pursuing, dropped) and color labels
- Mini bar chart of the totals in the table, with each bar in the color chosen for the idea
- Data stored as a single JSON file in your OS's per-user data folder

## Requirements

- Python 3.10 or newer, with Tkinter (included in most Python installers; on some Linux distributions install `python3-tk`)
- No third-party runtime dependencies

## Run

```sh
git clone https://github.com/ftaisdeal/Rubric.git
cd Rubric
python3 -m rubric
```

Your ideas are saved to:

| OS | Location |
|---|---|
| macOS | `~/Library/Application Support/Rubric/ideas.json` |
| Windows | `%APPDATA%\Rubric\ideas.json` |
| Linux | `$XDG_DATA_HOME/rubric/ideas.json` (default `~/.local/share/rubric/`) |

## Customize the rubric

The criteria, default weights (which must total 100), and score-level descriptions live in [rubric/rubric.py](rubric/rubric.py). Don't rename a criterion id once you have scored ideas with it, because ids are stored in the data file.

## Build the macOS app

```sh
./build_mac.sh
```

This creates `dist/Rubric.app` using PyInstaller in a throwaway virtualenv.

## Test

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m pytest
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE)
