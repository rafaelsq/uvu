import json
import re
import subprocess
import sys
from pathlib import Path

import tomllib


def clear_screen():
    """Clear terminal using subprocess instead of os.system."""
    command = "cls" if sys.platform == "win32" else "clear"
    try:
        subprocess.run([command], check=True)
    except FileNotFoundError:
        # Fallback for environments without a clear command
        print("\n" * 100)


def get_project_dependencies():
    """Extract direct dependencies from pyproject.toml.

    This includes:
    - `project.dependencies`
    - all `project.optional-dependencies` groups
    - top-level `[dependency-groups]` as used by uv / PEP 735
    """

    path = Path("pyproject.toml")
    if not path.exists():
        print("❌ Error: pyproject.toml not found in the current directory.")
        sys.exit(1)

    with open(path, "rb") as f:
        data = tomllib.load(f)
        project = data.get("project", {}) or {}

        # Base project dependencies
        deps: list[str] = list(project.get("dependencies", []) or [])

        # PEP 621 optional dependencies (extras), e.g. [project.optional-dependencies]
        optional_deps = project.get("optional-dependencies", {}) or {}
        for group_deps in optional_deps.values():
            if group_deps:
                deps.extend(group_deps)

        # PEP 735 / uv dependency groups, e.g. [dependency-groups]
        dep_groups = data.get("dependency-groups", {}) or {}
        for group_deps in dep_groups.values():
            if group_deps:
                deps.extend(group_deps)

        # Return a deduplicated list while preserving order
        seen = set()
        unique_deps: list[str] = []
        for d in deps:
            if d not in seen:
                seen.add(d)
                unique_deps.append(d)

        return unique_deps


def get_package_url(pkg_name):
    """Fetch the project URL using 'uv pip show' metadata."""
    try:
        result = subprocess.run(
            ["uv", "pip", "show", pkg_name], capture_output=True, text=True, check=True
        )
        # Search for Home-page or Project-URL in the text output
        for line in result.stdout.splitlines():
            if line.startswith("Home-page:") or line.startswith("Project-URL:"):
                url = line.split(":", 1)[1].strip()
                if url.startswith("http"):
                    return url
    except subprocess.CalledProcessError:
        pass

    # Fallback to PyPI project page
    return f"https://pypi.org/project/{pkg_name}/"


def main():
    # 1. Initialization
    raw_deps = get_project_dependencies()
    direct_names = {re.split(r"[<>=!~]", d)[0].strip().lower() for d in raw_deps}

    print("🔍 Scanning for updates...")
    try:
        # Use uv pip list for stable JSON output
        res = subprocess.run(
            ["uv", "pip", "list", "--outdated", "--format", "json"],
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
        url = get_package_url(name)

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
            try:
                # Run uv add to update pyproject.toml and lockfile
                subprocess.run(
                    ["uv", "add", f"{name}=={latest}"], check=True, capture_output=True
                )
                upgraded_history.append((name, current, latest))
                index += 1
            except subprocess.CalledProcessError:
                input(
                    "\n❌ Upgrade failed (dependency conflict). Press Enter to continue..."
                )
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
