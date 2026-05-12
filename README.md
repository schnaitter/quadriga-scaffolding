# QUADRIGA scaffolding

This script updates a QUADRIGA OER to contain common files (scripts, CSS, JS, ...) to the latest version.

## Usage

To compare the current state of an OER to the newest version of the common files, make sure your clone of the `quadriga-dk/quadriga-scaffolding` repository is up to date. Then, from within the `quadriga-scaffolding` directory, run

```console
$ ./scaffold.py ../path/to/oer/
```

to get an overview of changed files. To update the files to the newest version run

```console
$ ./scaffold.py --update ../path/to/oer/
```

and the script will overwrite existing files with their newest version and possibly delete files that were marked as deleted in the scaffolding repo.

## Structure of the Repo

In the `data/` folder you can find a copy of the files and folders that are common amongst all OER and which will be used to create or overwrite files in the OER.

The file `scaffold.txt` contains the files and directories to be created or overwritten (lines starting with a `+ `) and deleted (lines starting with `- `). Every other line is a comment and thus ignored by the script.

The file `scaffold.py` is a Python script to handle the scaffolding and updating the scaffolding. The script is set up to use `uv` to run the script. You can also manually create a virtual environment, install the requirements listed at the top of the file and then run it with `python3 scaffold.py` if you don't have `uv` available.


