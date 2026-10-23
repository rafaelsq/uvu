import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEFAULT_MIN_AGE_DAYS = 3


def get_min_age_days():
    """Read the minimum release age (in days) from UVU_MIN_AGE_DAYS."""
    raw = os.environ.get("UVU_MIN_AGE_DAYS", str(DEFAULT_MIN_AGE_DAYS))
    try:
        days = float(raw)
    except ValueError:
        print(f"❌ Error: UVU_MIN_AGE_DAYS must be a number, got {raw!r}.")
        sys.exit(1)
    if days < 0:
        print("❌ Error: UVU_MIN_AGE_DAYS must not be negative.")
        sys.exit(1)
    return days


def clear_screen():
    """Clear terminal using subprocess instead of os.system."""
    command = "cls" if sys.platform == "win32" else "clear"
    try:
        subprocess.run([command], check=True)
    except FileNotFoundError:
        # Fallback for environments without a clear command
        print("\n" * 100)


def get_direct_dependencies():
    """Extract top-level dependencies from pyproject.toml."""

    path = Path("pyproject.toml")
    if not path.exists():
        print("❌ Error: pyproject.toml not found in the current directory.")
        sys.exit(1)

    with open(path, "rb") as f:
        data = tomllib.load(f)
        # Handle project dependencies or optional groups if needed
        return data.get("project", {}).get("dependencies", [])


def get_sub_dependencies(pkg_name):
    """List the transitive dependencies of a package from the lockfile via 'uv tree'."""
    try:
        result = subprocess.run(
            ["uv", "tree", "--package", pkg_name, "--frozen"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return set()

    names = set()
    # Skip the root line; children look like "├── certifi v2024.8.30"
    for line in result.stdout.splitlines()[1:]:
        match = re.match(r"^[\s│├└─]*([A-Za-z0-9][A-Za-z0-9._-]*)\s", line)
        if match:
            names.add(match.group(1).lower())
    return names


def url_exists(url):
    """Return True if the URL answers a HEAD request with a 2xx status."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def get_github_release_url(repo_url, pkg_name, version):
    """Find the GitHub release page for a version, trying common tag styles."""
    match = re.search(r"github\.com/([^/\s]+)/([^/\s#?]+)", repo_url)
    if not match:
        return None

    owner, repo = match.group(1), match.group(2).removesuffix(".git")
    base = f"https://github.com/{owner}/{repo}/releases/tag"
    for tag in (f"v{version}", version, f"{pkg_name}-{version}"):
        url = f"{base}/{urllib.parse.quote(tag)}"
        if url_exists(url):
            return url
    return None


def get_package_url(pkg_name, version=None):
    """Fetch the project URL from PyPI metadata ('uv pip show' omits project URLs)."""
    fallback_url = None
    github_urls = []
    try:
        api_url = f"https://pypi.org/pypi/{urllib.parse.quote(pkg_name)}/json"
        with urllib.request.urlopen(api_url, timeout=5) as resp:
            info = json.load(resp).get("info", {})
        # Search Home-page and Project-URL entries
        urls = [info.get("home_page"), *(info.get("project_urls") or {}).values()]
        for url in urls:
            if url and url.startswith("http"):
                if "github.com" in url:
                    github_urls.append(url)
                elif not fallback_url:
                    fallback_url = url
    except (urllib.error.URLError, TimeoutError, ValueError):
        pass

    if github_urls:
        # Use the shortest GitHub URL (likely the main repo, not issues/pulls)
        repo_url = sorted(github_urls, key=len)[0]
        if version:
            release_url = get_github_release_url(repo_url, pkg_name, version)
            if release_url:
                return release_url
        return repo_url

    if fallback_url:
        return fallback_url

    # Fallback to PyPI project page
    return f"https://pypi.org/project/{pkg_name}/"


def main():
    # 1. Initialization
    raw_deps = get_direct_dependencies()
    direct_names = {re.split(r"[<>=!~]", d)[0].strip().lower() for d in raw_deps}

    min_age_days = get_min_age_days()
    cmd = ["uv", "pip", "list", "--outdated", "--format", "json"]
    cutoff = None
    if min_age_days > 0:
        # Ignore releases uploaded within the last N days
        cutoff = (datetime.now(timezone.utc) - timedelta(days=min_age_days)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        cmd += ["--exclude-newer", cutoff]
        print(f"🔍 Scanning for updates older than {min_age_days:g} days...")
    else:
        print("🔍 Scanning for updates...")
    try:
        # Use uv pip list for stable JSON output
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
        outdated = [
            p for p in json.loads(res.stdout) if p["name"].lower() in direct_names
        ]
    except Exception as e:
        print(f"❌ Error: {e}")
        return

    if not outdated:
        print("✅ All direct dependencies are up to date!")
        return

    index = 0
    # upgraded_history stores tuples of (name, old_version, new_version)
    upgraded_history = []

    while 0 <= index < len(outdated):
        clear_screen()
        pkg = outdated[index]
        name, current, latest = pkg["name"], pkg["version"], pkg["latest_version"]
        url = get_package_url(name, latest)

        # --- Dashboard Header ---
        print("\033[1;36mUV INTERACTIVE UPGRADER\033[0m")
        print(f"Progress: [{index + 1}/{len(outdated)}]")

        if upgraded_history:
            print("\n\033[1;32mSession Upgrades:\033[0m")
            for h_name, h_old, h_new in upgraded_history:
                print(
                    f"  ✓ {h_name}: \033[90m{h_old}\033[0m → \033[1;32m{h_new}\033[0m"
                )
        else:
            print("\n\033[90mNo upgrades performed yet.\033[0m")

        print("\n" + "─" * 55)

        # --- Current Package Focus ---
        print(f"Current Package: \033[1;34m{name}\033[0m")
        print(f"Update: \033[91m{current}\033[0m  ➜  \033[1;32m{latest}\033[0m")
        print(f"Release Info: \033[4;34m{url}\033[0m")
        print("─" * 55)

        choice = input("\n[y] Upgrade | [n] Skip | [p] Back | [q] Quit: ").lower()

        if choice == "y":
            print(f"\n🚀 Installing {name} {latest}...")
            # Also upgrade its sub-dependencies, leaving other direct deps to the user
            to_upgrade = [name, *sorted(get_sub_dependencies(name) - direct_names)]
            upgrade_args = [arg for dep in to_upgrade for arg in ("-P", dep)]
            if cutoff:
                # Apply the cooldown only to the packages being upgraded
                upgrade_args += [
                    arg
                    for dep in to_upgrade
                    for arg in ("--exclude-newer-package", f"{dep}={cutoff}")
                ]
            try:
                # Run uv add to update pyproject.toml and lockfile
                subprocess.run(
                    ["uv", "add", f"{name}=={latest}", *upgrade_args],
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError:
                input(
                    "\n❌ Upgrade failed (dependency conflict). Press Enter to continue..."
                )
                continue

            if cutoff:
                # uv persists --exclude-newer-package in uv.lock; a plain relock
                # drops it again while keeping the versions just resolved
                try:
                    subprocess.run(["uv", "lock"], check=True, capture_output=True)
                except subprocess.CalledProcessError:
                    input(
                        "\n⚠️ Upgraded, but 'uv lock' failed; uv.lock may still hold the "
                        "cooldown cutoff. Press Enter to continue..."
                    )
            upgraded_history.append((name, current, latest))
            index += 1
        elif choice == "p":
            index = max(0, index - 1)
        elif choice == "q":
            break
        else:
            index += 1

    # --- Final Summary ---
    clear_screen()
    print("✨ \033[1;32mUpdate Session Finished\033[0m")
    if upgraded_history:
        print("\n\033[1mFinal Change Log:\033[0m")
        print("─" * 45)
        for h_name, h_old, h_new in upgraded_history:
            # Consistent coloring: Dim/Red for old, Bright Green for new
            print(
                f"  • \033[1;34m{h_name.ljust(18)}\033[0m : \033[91m{h_old}\033[0m → \033[1;32m{h_new}\033[0m"
            )
        print("─" * 45)
    else:
        print("\nNo packages were upgraded.")


if __name__ == "__main__":
    main()
