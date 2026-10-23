# UV Interactive Upgrader 🚀

A lightweight CLI tool to interactively review and upgrade your Python project dependencies using `uv`.

<img width="458" height="231" alt="image" src="https://github.com/user-attachments/assets/d6d1bd0b-f1f0-4f33-a49a-f8acb35121d9" />


## Features
- 🔍 **Smart Filtering**: Only shows updates for direct dependencies listed in your `pyproject.toml`.
- 📊 **Interactive Navigation**: Step through packages one-by-one with `Next`, `Back`, and `Skip` options.
- 🔗 **Direct Changelogs**: Provides clickable links to PyPI/GitHub for every package.
- 🎨 **Visual Feedback**: Clean, color-coded terminal interface with a live session history.
- ⚡ **Powered by uv**: Fast, reliable dependency resolution and locking.
- 🛡️ **Release Cooldown**: Ignores releases newer than `UVU_MIN_AGE_DAYS` days (default `3`, `0` disables).

## Configuration

| Env var            | Default | Description                                                     |
| ------------------ | ------- | --------------------------------------------------------------- |
| `UVU_MIN_AGE_DAYS` | `3`     | Only offer versions uploaded at least this many days ago. `0` disables the filter. |

```bash
UVU_MIN_AGE_DAYS=7 uvu
```

## Installation

### Globally via `uv`
If you have `uv` installed, the easiest way to use this anywhere is:

```bash
uv tool install git+https://github.com/rafaelsq/uvu

# dev
uv tool install --editable .
```
