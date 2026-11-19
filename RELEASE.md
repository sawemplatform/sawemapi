# Releasing

Releases are manual: nothing automated versions, builds or publishes this package. A released version cannot be replaced on PyPI, so check each step before
uploading.

## 1. Prepare

1. Choose the version number. Until 1.0.0, breaking changes bump the minor number.
2. Set `__version__` in `src/sawemapi/_version.py`. This is the only place the version is
   kept; `pyproject.toml` reads it from there.
3. In `CHANGELOG.md`, move the entries to a heading for the new version with today's date,
   and start a fresh `Unreleased` section if there are further changes planned. The
   changelog is newest first, so put the new version at the top, above the previous release.
4. Update `ROADMAP.md` if the release delivers anything listed there.

## 2. Check

From the repository root, in a virtual environment with the package installed in editable
mode along with `pytest` and `pylint`:

```
pip install -e ".[pandas]" pytest pylint
python -m pytest src/sawemapi/tests
pylint --rcfile conf/pylintrc src/sawemapi
```

Both must pass. Then test against a real API instance, since the unit tests use mocked
responses only.

## 3. Commit and tag

Commit the version and changelog, merge to `main` (via pull request if you work on a
branch), and tag the resulting commit on `main`:

```
git tag vX.Y.Z
git push origin vX.Y.Z
```

The tag records which commit was released. Optionally, create a GitHub release from it
(`gh release create vX.Y.Z --notes-from-tag` or via the web UI) using the changelog entry.

## 4. Build

Build from the tagged commit, with no uncommitted changes:

```
rm -rf dist build src/*.egg-info
pip install build
python -m build
```

Check that `dist/` holds exactly one wheel and one sdist, both for the new version, and
that the wheel contains no tests:

```
unzip -l dist/*.whl
```

## 5. Upload

Use a virtual environment with `twine`, and a PyPI API token (username `__token__`).

```
twine check dist/*
twine upload --repository testpypi dist/*
```

Install from TestPyPI in a clean virtual environment and make a call:

```
python -m venv /tmp/check && . /tmp/check/bin/activate
pip install --index-url https://test.pypi.org/simple/ \
            --extra-index-url https://pypi.org/simple/ sawemapi==X.Y.Z
python -c "import sawemapi; print(sawemapi.__version__)"
```

When that works, upload to PyPI:

```
twine upload dist/*
```

Then install from PyPI in a clean environment to confirm.

## If something is wrong

A published version cannot be deleted and re-uploaded. Yank it on PyPI, which keeps it
available to anyone who pinned it but stops it being chosen by default, and release the
fix under a new version number.
