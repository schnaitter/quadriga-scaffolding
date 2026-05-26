# QUADRIGA scaffolding

This tool updates a QUADRIGA OER to contain common files (scripts, CSS, JS, ...) to the latest version.

## Installation (for development)

The project is a standard `pyproject.toml`-based package. The recommended way to set up a development environment is via [`just`](https://github.com/casey/just):

```console
$ git clone https://github.com/quadriga-dk/quadriga-scaffolding.git
$ cd quadriga-scaffolding
$ just install
```

If you don't have `just` yet, install it via your package manager (e.g. `brew install just`, `apt install just`, `cargo install just`) — see the [just installation docs](https://github.com/casey/just#installation) for more options.

`just install` will detect whether [`uv`](https://docs.astral.sh/uv/) is available and use it (`uv sync`) if so. Otherwise it falls back to creating a `.venv/` with `python3 -m venv` and installing the package in **editable** mode together with the development tools (`pytest`, `ruff`, `mypy`) via `pip`.

If you'd rather run the steps yourself:

With `uv`:

```console
$ uv sync
```

Or with plain `pip`:

```console
$ python3 -m venv .venv
$ source .venv/bin/activate
$ pip install -e ".[dev]"
```

### Running the development tools

With [`just`](https://github.com/casey/just):

```console
$ just check   # run all checks (ruff, mypy, pytest)
$ just ruff    # lint
$ just format  # auto-format
$ just mypy    # type-check
$ just test    # tests
```

Or with `uv`:

```console
$ uv run pytest          # tests
$ uv run ruff check .    # lint
$ uv run ruff format .   # auto-format
$ uv run mypy            # type-check
```

## Usage

The package installs a `scaffold` console script. The common files and the manifest ship with the package via `importlib.resources`, so the tool no longer depends on being run from inside the repository clone.

To compare the current state of an OER to the newest version of the common files:

```console
$ just scaffold ../path/to/oer/
```

To update the files to the newest version:

```console
$ just scaffold --update ../path/to/oer/
```

(`just scaffold` uses `uv run scaffold` when `uv` is available, and falls back to the `scaffold` entry point in `.venv/` otherwise.)

In `--update` mode the script overwrites files with their newest packaged version and removes files (and recursively-empty directories) that the manifest marks for deletion. Two kinds of drift are **never** resolved automatically:

- A directory marked for deletion (`- dir/`) that still contains files is **never** auto-deleted — remove its contents yourself first.
- Files found inside a managed directory (`+ dir/`) but not listed in the manifest are reported as **untracked** and **never** deleted.

Equivalent invocations:

```console
$ uv run python -m quadriga_scaffolding ../path/to/oer/
$ scaffold ../path/to/oer/        # if the venv is activated
```

Pass `--manifest PATH` to compare against a manifest other than the packaged one (useful for testing and local experimentation), and `-v`/`--verbose` to also print in-sync (`ok`) entries.

### Output

Each changed path is printed on its own line with a git-style status letter:

| Letter | Meaning |
|---|---|
| `A` | **add** — listed in the manifest but missing in the OER |
| `M` | **modify** — present but its bytes differ from the packaged version |
| `D` | **delete** — listed for deletion and removable |
| `?` | **untracked** — inside a managed `+ dir/` but not in the manifest |
| `!` | **blocked** — a `- dir/` that is not empty and so cannot be deleted |
| ` ` | **ok** — already in sync (only shown with `-v`) |

Comparison is byte-exact: no line-ending or whitespace normalization is applied.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | fully in sync (no `A`/`M`/`D`/`?`/`!` after the run) |
| `1` | drift detected; in `--update` mode this means `?`/`!` items remain after the update |
| `2` | the manifest is invalid (e.g. a path listed under both `+` and `-`) |

## Structure of the repo

The package lives under `src/quadriga_scaffolding/`:

- `scaffold.py` — core logic (parsing the manifest, resolving packaged resources, checking the data tree).
- `cli.py` — command-line entry point (`scaffold` console script).
- `data/` — the files and folders that are common amongst all OERs and that will be used to create or overwrite files in the target OER. **These ship with the installed package.**
- `data/scaffold.txt` — manifest listing files/directories to be created or overwritten (lines starting with `+ `) and deleted (lines starting with `- `). Every other line is treated as a comment.

Tests live under `tests/`.
