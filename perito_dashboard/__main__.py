"""python3 -m perito_dashboard --data-dir data --site-dir site"""
import argparse
import sys
from xml.etree.ElementTree import ParseError
from zipfile import BadZipFile

from . import refresh_and_build


def main():
    parser = argparse.ArgumentParser(description="Refresh official PF/PCF aggregates and build a static site.")
    parser.add_argument("--data-dir", default="data", help="Dedicated persisted aggregate directory (default: data)")
    parser.add_argument("--site-dir", default="site", help="Dedicated generated artifact directory (default: site)")
    args = parser.parse_args()
    try:
        refresh_and_build(args.data_dir, args.site_dir)
    except (ValueError, OSError, BadZipFile, ParseError, KeyError) as exc:
        print(f"Refresh/build failed; no candidate published: {exc}", file=sys.stderr)
        return 1
    print(f"Refresh/build succeeded: aggregates in {args.data_dir}; static artifact in {args.site_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
