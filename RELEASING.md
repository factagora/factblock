# Releasing

Maintainers only. Releases go to PyPI from GitHub Actions through
[trusted publishing](https://docs.pypi.org/trusted-publishers/); no token lives on a laptop.

## One-time setup

1. On pypi.org, signed in as the Factagora account: **Your projects → Publishing → Add a new pending publisher**
   with project name `factblock`, owner `factagora`, repository `factblock`, workflow `release.yml`, environment `pypi`.
2. In the GitHub repository: **Settings → Environments → New environment** named `pypi`. Optionally require a reviewer.
3. Add the workflow below as `.github/workflows/release.yml`.

```yaml
name: release
on:
  push:
    tags: ["v*"]
jobs:
  pypi:
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync
      - run: for t in tests/test_*.py; do uv run python $t; done
      - run: uv build
      - uses: pypa/gh-action-pypi-publish@release/v1
```

## Each release

1. `CHANGELOG.md`: a dated heading for the version. `pyproject.toml`: bump `version`. Until the format
   reaches 1.0.0 (SPEC.md section 10: a reader or writer maintained outside this repository), the
   package stays on `1.0.0aN` pre-releases.
2. Commit, then tag and push the tag:

   ```bash
   git tag v1.0.0a1 && git push origin v1.0.0a1
   ```

3. The `release` workflow runs the tests, builds the sdist and wheel, and publishes. Check
   https://pypi.org/project/factblock/ and `pip install factblock==1.0.0a1` in a clean environment.

The wheel carries `factblock/profiles/claims/*` (the extraction profile is data, not code); the sdist
also carries `SPEC.md`, `samples/`, `duckdb/` and `tests/`. `uv build` then listing the archives is the
check if packaging changes.
