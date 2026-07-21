# Third-Party Notices

This report identifies the software distributed with Aqua Essence, including the
fully resolved Python runtime graph. It is generated from `requirements.txt`,
`requirements-runtime-lock.txt`, `desktop/package.json`,
`desktop/package-lock.json`, and the pinned vendored web assets under
`frontend/vendor/` and `frontend/xai_dashboard/static/vendor/`; do not edit the
table manually. Aqua Essence itself is
MIT-licensed under the repository's `LICENSE` file.

| Boundary | Package | Pinned version | License | Homepage/source | Required notice pointer |
| --- | --- | --- | --- | --- | --- |
| Python transitive | `absl-py` | `2.5.0` | Apache-2.0 | [source](https://pypi.org/project/absl-py/2.5.0/) | `licenses/python/absl-py-2.5.0/` |
| Python transitive | `annotated-doc` | `0.0.4` | MIT | [source](https://pypi.org/project/annotated-doc/0.0.4/) | `licenses/python/annotated-doc-0.0.4/` |
| Python transitive | `annotated-types` | `0.7.0` | MIT | [source](https://pypi.org/project/annotated-types/0.7.0/) | `licenses/python/annotated-types-0.7.0/` |
| Python transitive | `anyio` | `4.14.2` | MIT | [source](https://pypi.org/project/anyio/4.14.2/) | `licenses/python/anyio-4.14.2/` |
| Python transitive | `charset-normalizer` | `3.4.9` | MIT | [source](https://pypi.org/project/charset-normalizer/3.4.9/) | `licenses/python/charset-normalizer-3.4.9/` |
| Python transitive | `click` | `8.4.2` | BSD-3-Clause | [source](https://pypi.org/project/click/8.4.2/) | `licenses/python/click-8.4.2/` |
| Python transitive | `colorama` | `0.4.6` | BSD-3-Clause | [source](https://pypi.org/project/colorama/0.4.6/) | `licenses/python/colorama-0.4.6/` |
| Python direct | `fastapi` | `0.135.1` | MIT | [source](https://pypi.org/project/fastapi/0.135.1/) | `licenses/python/fastapi-0.135.1/` |
| Python transitive | `h11` | `0.16.0` | MIT | [source](https://pypi.org/project/h11/0.16.0/) | `licenses/python/h11-0.16.0/` |
| Python transitive | `idna` | `3.18` | BSD-3-Clause | [source](https://pypi.org/project/idna/3.18/) | `licenses/python/idna-3.18/` |
| Python transitive | `immutabledict` | `4.3.1` | MIT | [source](https://pypi.org/project/immutabledict/4.3.1/) | `licenses/python/immutabledict-4.3.1/` |
| Python direct | `jinja2` | `3.1.6` | BSD-3-Clause | [source](https://pypi.org/project/jinja2/3.1.6/) | `licenses/python/jinja2-3.1.6/` |
| Python transitive | `markupsafe` | `3.0.3` | BSD-3-Clause | [source](https://pypi.org/project/markupsafe/3.0.3/) | `licenses/python/markupsafe-3.0.3/` |
| Python transitive | `numpy` | `2.5.1` | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | [source](https://pypi.org/project/numpy/2.5.1/) | `licenses/python/numpy-2.5.1/` |
| Python direct | `ortools` | `9.15.6755` | Apache-2.0 | [source](https://pypi.org/project/ortools/9.15.6755/) | `licenses/python/ortools-9.15.6755/` |
| Python direct | `pandas` | `2.3.3` | BSD-3-Clause | [source](https://pypi.org/project/pandas/2.3.3/) | `licenses/python/pandas-2.3.3/` |
| Python transitive | `pillow` | `12.3.0` | MIT-CMU | [source](https://pypi.org/project/pillow/12.3.0/) | `licenses/python/pillow-12.3.0/` |
| Python transitive | `protobuf` | `6.33.6` | BSD-3-Clause | [source](https://pypi.org/project/protobuf/6.33.6/) | `licenses/python/protobuf-6.33.6/` |
| Python transitive | `pydantic` | `2.13.4` | MIT | [source](https://pypi.org/project/pydantic/2.13.4/) | `licenses/python/pydantic-2.13.4/` |
| Python transitive | `pydantic-core` | `2.46.4` | MIT | [source](https://pypi.org/project/pydantic-core/2.46.4/) | `licenses/python/pydantic-core-2.46.4/` |
| Python transitive | `python-dateutil` | `2.9.0.post0` | BSD-3-Clause OR Apache-2.0 | [source](https://pypi.org/project/python-dateutil/2.9.0.post0/) | `licenses/python/python-dateutil-2.9.0.post0/` |
| Python direct | `python-multipart` | `0.0.20` | Apache-2.0 | [source](https://pypi.org/project/python-multipart/0.0.20/) | `licenses/python/python-multipart-0.0.20/` |
| Python transitive | `pytz` | `2026.2` | MIT | [source](https://pypi.org/project/pytz/2026.2/) | `licenses/python/pytz-2026.2/` |
| Python direct | `reportlab` | `4.4.10` | BSD-3-Clause | [source](https://pypi.org/project/reportlab/4.4.10/) | `licenses/python/reportlab-4.4.10/` |
| Python transitive | `six` | `1.17.0` | MIT | [source](https://pypi.org/project/six/1.17.0/) | `licenses/python/six-1.17.0/` |
| Python transitive | `starlette` | `1.3.1` | BSD-3-Clause | [source](https://pypi.org/project/starlette/1.3.1/) | `licenses/python/starlette-1.3.1/` |
| Python transitive | `typing-extensions` | `4.16.0` | PSF-2.0 | [source](https://pypi.org/project/typing-extensions/4.16.0/) | `licenses/python/typing-extensions-4.16.0/` |
| Python transitive | `typing-inspection` | `0.4.2` | MIT | [source](https://pypi.org/project/typing-inspection/0.4.2/) | `licenses/python/typing-inspection-0.4.2/` |
| Python transitive | `tzdata` | `2026.3` | Apache-2.0 | [source](https://pypi.org/project/tzdata/2026.3/) | `licenses/python/tzdata-2026.3/` |
| Python direct | `uvicorn` | `0.42.0` | BSD-3-Clause | [source](https://pypi.org/project/uvicorn/0.42.0/) | `licenses/python/uvicorn-0.42.0/` |
| Vendored web asset | `chart.js` | `4.5.1` | MIT | [source](https://github.com/chartjs/Chart.js) | `frontend/xai_dashboard/static/vendor/chartjs/LICENSE.md` |
| Vendored web asset | `@fontsource/outfit` | `5.3.0` | OFL-1.1 | [source](https://github.com/fontsource/font-files) | `frontend/vendor/fonts/outfit/LICENSE` |
| Vendored web asset | `@fontsource/jetbrains-mono` | `5.3.0` | OFL-1.1 | [source](https://github.com/fontsource/font-files) | `frontend/vendor/fonts/jetbrains-mono/LICENSE` |
| Desktop runtime | `electron` | `43.1.1` | MIT | [source](https://github.com/electron/electron) | Electron `LICENSE` and `LICENSES.chromium.html` |

## Distribution obligations

- Preserve this project's `LICENSE` in source and binary releases.
- Preserve each Python wheel's license file when its code or native libraries are
  collected into the backend executable. Apache-2.0 packages also require any
  upstream `NOTICE` file that is present in the artifact being redistributed.
- Electron is MIT-licensed, but its binary embeds Chromium, Node.js, and other
  components. Ship Electron's version-matched `LICENSE` and
  `LICENSES.chromium.html` beside the desktop executable; the latter is the
  authoritative component-by-component notice bundle and must not be replaced by
  this short report.
- Preserve ReportLab's license and the individual license files for any ReportLab
  fonts actually collected into the backend bundle (including Bitstream Vera or
  DarkGarden when present).
- OR-Tools contains compiled native code. Preserve the license material delivered
  in its wheel and verify the final frozen application for additional native
  notices before publishing.
- PyInstaller is a build-time tool, not an application runtime dependency. Its
  GPL bootloader exception permits distributing an unmodified,
  PyInstaller-generated application under this project's license. PyInstaller
  itself remains GPL-licensed; review its `COPYING.txt` before modifying its
  bootloader or redistributing the build tool. Record the pinned PyInstaller
  version in build metadata before the first release.

## Scope and artifact verification

`requirements-runtime-lock.txt` is the reproducible Python dependency boundary for
the Windows/Python 3.14 package. Every backend build validates the installed
versions against that lock, creates `SBOM.cdx.json`, and copies every license,
copying, and notice file exposed by those installed distributions into
`licenses/python/`. Package verification rejects a missing SBOM, component, or
license directory. Python's own license is bundled separately because the frozen
application distributes the interpreter and standard library.

The Electron npm package is included even though it is a `devDependency`, because
its binary becomes the desktop runtime. Its npm download/extraction helpers are
not shipped in the packaged application and are excluded. Python packages from
`requirements-dev.txt` (including pytest, HTTPX, Faker, and Ruff) are also excluded.

Regenerate with:

```console
python scripts/generate_third_party_notices.py
```

CI/release verification can check for drift without modifying files:

```console
python scripts/generate_third_party_notices.py --check
```
