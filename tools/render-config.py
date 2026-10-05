"""Render only explicitly supplied placeholders. No shell evaluation."""
from pathlib import Path
import string
import sys

source, target = map(Path, sys.argv[1:3])
values = dict(arg.split("=", 1) for arg in sys.argv[3:])
content = string.Template(source.read_text(encoding="utf-8")).substitute(values)
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(content, encoding="utf-8")
