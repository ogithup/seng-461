"""Command line demo: write a generated site to a folder.

    python -m backend.generator blog "Travel Notes" out/blog
    python -m backend.generator --spec my_site.json out/my_site

This is the only place in the package that touches the filesystem; the application itself
writes files through the workspace executor, never through this script.
"""
import argparse
import json
import sys
from pathlib import Path

from backend.generator import SITE_TYPES, SpecError, WebsiteGenerator


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m backend.generator")
    parser.add_argument("--spec", type=Path, help="JSON file with a website spec")
    parser.add_argument("args", nargs="+", help="[site_type title] output_dir")
    options = parser.parse_args(argv)

    generator = WebsiteGenerator()
    if options.spec:
        if len(options.args) != 1:
            parser.error("with --spec, give only the output directory")
        spec = json.loads(options.spec.read_text(encoding="utf-8"))
        out = Path(options.args[0])
    else:
        if len(options.args) != 3 or options.args[0] not in SITE_TYPES:
            parser.error("expected: {%s} TITLE OUTPUT_DIR" % "|".join(SITE_TYPES))
        spec = generator.starter_spec(options.args[0], options.args[1])
        out = Path(options.args[2])

    try:
        files = generator.build(spec)
    except SpecError as exc:
        for problem in exc.problems:
            print("spec error: %s" % problem, file=sys.stderr)
        return 2
    out.mkdir(parents=True, exist_ok=True)
    for path, content in sorted(files.items()):
        (out / path).write_text(content, encoding="utf-8")
        print("wrote %s" % (out / path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
