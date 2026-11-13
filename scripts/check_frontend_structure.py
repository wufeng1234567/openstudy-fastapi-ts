"""Check the frontend component-package layout.

The project keeps one public entry at ``components/<Feature>/``; child
components, composables, pure helpers and styles live in their own subfolders.
This guard catches the "everything flat in one folder" pattern before review.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "openstudy-vue3-ts" / "src" / "components"
ALLOWED_SUBDIRS = {
    "components": {".vue"},
    "composables": {".ts"},
    "utils": {".ts"},
    "styles": {".css", ".scss"},
}
ROOT_ALLOWED_FILES = {"README.md"}


def main() -> int:
    problems: list[str] = []
    checked = 0

    for feature in sorted(path for path in COMPONENTS.iterdir() if path.is_dir()):
        checked += 1
        root_vues = sorted(feature.glob("*.vue"))
        if len(root_vues) > 1:
            problems.append(
                f"{feature.relative_to(ROOT)}: root must contain at most one .vue entry (found {len(root_vues)})"
            )

        for child in feature.iterdir():
            if child.is_file():
                if child.suffix == ".vue" or child.name in ROOT_ALLOWED_FILES or child.suffix == ".md":
                    continue
                problems.append(f"{feature.relative_to(ROOT)}: unexpected root file {child.name}")
                continue
            if child.name not in ALLOWED_SUBDIRS:
                problems.append(f"{feature.relative_to(ROOT)}: unexpected subdirectory {child.name}/")
                continue
            allowed_ext = ALLOWED_SUBDIRS[child.name]
            for file in child.rglob("*"):
                if file.is_dir():
                    problems.append(f"{feature.relative_to(ROOT)}/{child.name}: nested directory not allowed")
                    continue
                if file.suffix not in allowed_ext:
                    problems.append(
                        f"{feature.relative_to(ROOT)}/{child.name}: unexpected file {file.name} (allowed: {', '.join(sorted(allowed_ext))})"
                    )

    if problems:
        print("Frontend structure check failed:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"Frontend structure check passed ({checked} component packages scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
