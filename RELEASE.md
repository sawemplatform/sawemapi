# Releasing

Releases are manual: CI runs the tests and lint, but does not version, build or publish
this package. A released version cannot be replaced on PyPI, so check each step before
uploading.

## 1. Prepare

1. Choose the version number. Until 1.0.0, breaking changes bump the minor number.
2. Set `__version__` in `src/sawemapi/_version.py`. This is the only place the version is
   kept; `pyproject.toml` reads it from there.
3. In `CHANGELOG.md`, move the entries to a heading for the new version with today's date,
   and start a fresh `Unreleased` section if there are further changes planned.
4. Update `ROADMAP.md` if the release delivers anything listed there.

## 2. Check

From the `sawemapi` directory, in the dev container (`dev-packagedev-1`):

```
eskmanage test unit
eskmanage lint
```

Both must pass. Then test against a real API instance, since the unit tests use mocked
responses only.

## 3. Commit and tag

Commit the version and changelog, merge to `main`, and tag the merge commit:

```
git tag sawemapi-vX.Y.Z
git push <remote> sawemapi-vX.Y.Z
```

Nothing in CI reads the tag; it records which commit was released.

## 4. Build

Build from the tagged commit, with no uncommitted changes:

```
rm -rf dist build src/*.egg-info
eskmanage build
```

Check that `dist/` holds exactly one wheel and one sdist, both for the new version, and
that the wheel contains no tests:

```
unzip -l dist/*.whl
```

## 5. Upload

The build servers have no internet access, so upload from a machine that has. Use a
virtual environment with `twine`, and a PyPI API token (username `__token__`).

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
