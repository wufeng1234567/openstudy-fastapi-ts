"""Fail CI when a Vue <script setup> calls a composable that is neither imported nor locally defined.

This catches the class of bug where a refactor moves a composable call into a component but forgets the import.
Vue/vue-router auto-import names are whitelisted.
"""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "openstudy-vue3-ts" / "src"
AUTO_IMPORTS = {"useRoute", "useRouter", "useStore"}


def main() -> int:
    problems = []
    for path in SRC.rglob("*.vue"):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"<script setup[^>]*>(.*?)</script>", text, re.S)
        if not match:
            continue
        script = match.group(1)
        calls = sorted(set(re.findall(r"(?<![\w.$])(use[A-Z][A-Za-z0-9_]*)\s*\(", script)))
        if not calls:
            continue
        imports = set()
        for item in re.finditer(
            r"import\s+(?:type\s+)?(?:([\w$]+)\s*,?\s*)?(?:\{([^}]*)\})?\s*from", script
        ):
            if item.group(1):
                imports.add(item.group(1))
            if item.group(2):
                for part in item.group(2).split(","):
                    name = part.strip().split(" as ")[-1].strip()
                    if name:
                        imports.add(name)
        local_defs = set(
            re.findall(r"\b(?:function|const|let|var)\s+(use[A-Z][A-Za-z0-9_]*)", script)
        )
        missing = [name for name in calls if name not in imports and name not in local_defs and name not in AUTO_IMPORTS]
        if missing:
            problems.append((path.relative_to(ROOT), missing))

    if problems:
        print("Composable import check failed:")
        for path, names in problems:
            print(f"  {path}: {', '.join(names)}")
        return 1
    print(f"Composable import check passed ({len(list(SRC.rglob('*.vue')))} Vue files scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
