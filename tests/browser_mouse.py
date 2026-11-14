"""Optional real-mouse acceptance via Orca, not a headless/CI test.

Prepare uses the public refresh/build seam with controlled official documents.
Check accepts an explicitly owned page and local preview; never creates/closes tabs.
DOM evaluation only measures/reads the page or changes scroll position. Inspection
itself must be caused by `orca mouse move`, never synthetic events or handlers.
See docs/operations.md for the local recipe.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from urllib.parse import urlsplit

from perito_dashboard import refresh_and_build
from tests.sources import CHECK_TIME, ControlledArchive, national_resources, resource_url
from tests.test_dashboard import monthly_resource


class Browser:
    def __init__(self, executable, page, url):
        self.executable, self.page, self.url = executable, page, url

    def command(self, *args):
        command = [self.executable, *args, "--page", self.page, "--json"]
        if args[0] not in {"viewport", "wait"}:  # No URL guard on these in this Orca.
            command.extend(["--expect-url", self.url])
        completed = subprocess.run(command, text=True, capture_output=True)
        if completed.returncode:
            raise AssertionError((command, completed.stdout, completed.stderr))
        receipt = json.loads(completed.stdout)
        if receipt.get("error"):
            raise AssertionError(receipt)
        return receipt["result"]

    def evaluate(self, expression):
        result = self.command("eval", "--expression", expression)["result"]
        try:
            return json.loads(result) if result is not None else None
        except json.JSONDecodeError:  # Orca returns strings without JSON quoting.
            return result

    def move(self, x, y):
        return self.command("mouse", "move", "--x", str(x), "--y", str(y))

    def setup(self, width=1440, height=1000):
        self.command("viewport", "--width", str(width), "--height", str(height))
        self.evaluate("document.querySelector('#history-chart').scrollIntoView({block:'center'}); "
                      "document.querySelector('.chart-scroll').scrollLeft = 0")

    def point(self, fraction, height):
        # Ordinary visible grid geometry, not application metadata or a helper API.
        return self.evaluate(f"""(() => {{
          const svg = document.querySelector('#history-chart');
          const lines = svg.querySelectorAll('.grid-line');
          const first = lines[0], last = lines[lines.length - 1];
          const p = svg.createSVGPoint();
          p.x = first.x1.baseVal.value + {fraction} *
                (first.x2.baseVal.value - first.x1.baseVal.value);
          p.y = last.y1.baseVal.value + {height} *
                (first.y1.baseVal.value - last.y1.baseVal.value);
          const screen = p.matrixTransform(svg.getScreenCTM());
          return {{x: screen.x, y: screen.y}};
        }})()""")

    def tooltip(self):
        return self.evaluate("""(() => {
          const tooltip = document.querySelector('[role="tooltip"]');
          return tooltip && !tooltip.hidden && getComputedStyle(tooltip).display !== 'none'
            ? tooltip.textContent.trim() : null;
        })()""")

    def inspect(self, fraction, height, expected):
        point = self.point(fraction, height)
        self.move(point["x"], point["y"])
        observed = self.tooltip()
        assert observed == expected, (expected, observed, point)
        print(f"PASS mouse ({point['x']:.2f}, {point['y']:.2f}): {observed}")

    def contained(self):
        geometry = self.evaluate("""(() => {
          const tip = document.querySelector('[role="tooltip"]').getBoundingClientRect();
          const clip = document.querySelector('.chart-scroll').getBoundingClientRect();
          return {left: tip.left, right: tip.right, top: tip.top, bottom: tip.bottom,
                  clipLeft: Math.max(0, clip.left),
                  clipRight: Math.min(innerWidth, clip.right), height: innerHeight,
                  pageWidth: document.documentElement.scrollWidth, width: innerWidth};
        })()""")
        assert geometry["left"] >= geometry["clipLeft"], geometry
        assert geometry["right"] <= geometry["clipRight"], geometry
        assert 0 <= geometry["top"] <= geometry["bottom"] <= geometry["height"], geometry
        assert geometry["pageWidth"] == geometry["width"], geometry
        print("PASS tooltip contained/readable without page overflow", geometry)

    def leave(self):
        point = self.point(.5, -.03)
        point["x"] = self.evaluate("""(() => {
          const clip = document.querySelector('.chart-scroll').getBoundingClientRect();
          return (clip.left + clip.right) / 2;
        })()""")
        self.move(point["x"], point["y"])
        assert self.tooltip() is None, ("Stale inspection after leaving plot", self.tooltip())
        print("PASS leaving plot clears inspection")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--root", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("--orca", required=True, help="Executable resolved by the Orca skill")
    check.add_argument("--page", required=True, help="Your explicitly owned browser page ID")
    check.add_argument("--base-url", required=True, help="Local preview root, ending in /")
    check.add_argument("--case", choices=["nearest", "gap", "leave", "clamp", "scroll", "resize",
                                         "edges", "zero", "narrow", "formatted", "fallback", "allzero"],
                       default="nearest")
    args = parser.parse_args()
    if args.command == "prepare":
        refresh_and_build(args.root / "data-national",
                          args.root / "www/national/monitorar-vacancias-perito-pf",
                          source=ControlledArchive(national_resources()), clock=lambda: CHECK_TIME)
        refresh_and_build(args.root / "data-zero",
                          args.root / "www/zero/monitorar-vacancias-perito-pf",
                          source=ControlledArchive({resource_url("2025-06"):
                                                    monthly_resource("2025-06", 1195, 0)}),
                          clock=lambda: CHECK_TIME)
        refresh_and_build(args.root / "data-formatted",
                          args.root / "www/formatted/monitorar-vacancias-perito-pf",
                          source=ControlledArchive({
                              resource_url("2025-06"): monthly_resource("2025-06", 50, 12345),
                              resource_url("2025-08"): monthly_resource("2025-08", 1195, 0),
                          }), clock=lambda: CHECK_TIME)
        refresh_and_build(args.root / "data-allzero",
                          args.root / "www/allzero/monitorar-vacancias-perito-pf",
                          source=ControlledArchive({resource_url(month): monthly_resource(month, 0, 0)
                                                    for month in ("2025-06", "2025-08", "2025-09")}),
                          clock=lambda: CHECK_TIME)
        fallback = args.root / "www/fallback/monitorar-vacancias-perito-pf"
        shutil.copytree(args.root / "www/national/monitorar-vacancias-perito-pf",
                        fallback, dirs_exist_ok=True)
        (fallback / "assets/inspection.js").unlink()  # Simulate an unavailable optional asset.
        print(args.root / "www")
        return
    assert urlsplit(args.base_url).hostname in {"127.0.0.1", "localhost"}, "Local preview only"
    assert args.page != "fff658ce-af08-4721-b944-f11fa526a5c0", "Protected user page"
    fixture = args.case if args.case in {"zero", "formatted", "fallback", "allzero"} else "national"
    url = args.base_url.rstrip("/") + f"/{fixture}/monitorar-vacancias-perito-pf/"
    browser = Browser(args.orca, args.page, url)
    browser.setup(width=320 if args.case == "narrow" else 1440,
                  height=800 if args.case == "narrow" else 1000)
    if args.case == "narrow":
        browser.inspect(0, .08, "junho de 2025 — Cargos vagos: 79")
        browser.inspect(1 / 15 - .002, .92, "julho de 2025 — dados indisponíveis")
        browser.contained()
        browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 99999")
        browser.command("wait", "--text", "setembro de 2026 — Cargos vagos: 87")
        assert browser.tooltip() == "setembro de 2026 — Cargos vagos: 87", browser.tooltip()
        browser.inspect(1, .08, "setembro de 2026 — Cargos vagos: 87")
        browser.contained()
        # Move the plot near the bottom of the viewport through ordinary page scrolling.
        bottom = browser.point(1, .92)
        browser.evaluate(f"window.scrollBy(0, {bottom['y']} - (innerHeight - 12))")
        browser.inspect(1, .92, "setembro de 2026 — Cargos vagos: 87")
        browser.contained()
        browser.leave()
        return
    if args.case == "fallback":
        point = browser.point(3 / 15, .08)
        browser.move(point["x"], point["y"])
        assert browser.tooltip() is None, "Optional script should be unavailable"
        static = browser.evaluate("""(() => {
          const chart = document.querySelector('#history-chart');
          const table = document.querySelector('#history-values');
          return {title: chart.querySelector('title').textContent,
                  markers: chart.querySelectorAll('.vacant-point').length,
                  descriptions: chart.querySelector('desc').textContent,
                  rows: table.tBodies[0].rows.length, table: table.textContent,
                  scrollers: Array.from(document.querySelectorAll('[role="region"]'))
                    .map(region => region.tabIndex)};
        })()""")
        assert static["title"] == "Histórico de cargos vagos", static
        assert static["markers"] == 15 and static["rows"] == 16, static
        assert "julho de 2025: indisponível" in static["descriptions"], static
        assert "setembro de 2026" in static["table"] and "87" in static["table"], static
        assert static["scrollers"] == [0, 0], static
        print("PASS unavailable JS leaves useful static chart, equivalent table and scroll regions")
        return
    if args.case == "allzero":
        browser.inspect(0, .08, "junho de 2025 — Cargos vagos: 0")
        browser.inspect(1 / 3, .92, "julho de 2025 — dados indisponíveis")
        browser.inspect(2 / 3, .08, "agosto de 2025 — Cargos vagos: 0")
        browser.inspect(1, .92, "setembro de 2025 — Cargos vagos: 0")
        browser.contained()
        browser.leave()
        return
    if args.case == "formatted":
        browser.inspect(0, .08, "junho de 2025 — Cargos vagos: 12.345")
        browser.inspect(.5, .92, "julho de 2025 — dados indisponíveis")
        browser.inspect(1, .08, "agosto de 2025 — Cargos vagos: 0")
        browser.contained()
        browser.command("viewport", "--width", "1000", "--height", "1000")
        browser.inspect(.5, .08, "julho de 2025 — dados indisponíveis")
        browser.inspect(0, .92, "junho de 2025 — Cargos vagos: 12.345")
        browser.contained()
        browser.leave()
        return
    if args.case == "zero":
        for fraction, height in ((0, .08), (.5, .92), (1, .08)):
            browser.inspect(fraction, height, "junho de 2025 — Cargos vagos: 0")
            browser.contained()
        browser.leave()
        return
    # September 2025 is slot 3 of 16, away from every marker/line vertically.
    browser.inspect(3 / 15, .08, "setembro de 2025 — Cargos vagos: 87")
    if args.case == "gap":
        browser.inspect(1 / 15, .08, "julho de 2025 — dados indisponíveis")
        browser.inspect(1 / 15, .92, "julho de 2025 — dados indisponíveis")
        browser.inspect(2 / 15, .92, "agosto de 2025 — Cargos vagos: 84")
    if args.case == "leave":
        browser.leave()
    if args.case == "clamp":
        browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 99999")
        browser.inspect(1, .92, "setembro de 2026 — Cargos vagos: 87")
        browser.contained()
    if args.case == "scroll":
        browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 341.333333")
        browser.command("wait", "--text", "janeiro de 2026 — Cargos vagos: 101")
        assert browser.tooltip() == "janeiro de 2026 — Cargos vagos: 101", browser.tooltip()
        browser.contained()
        browser.inspect(14 / 15, .08, "agosto de 2026 — Cargos vagos: 128")
    if args.case == "edges":
        browser.inspect(0, .08, "junho de 2025 — Cargos vagos: 79")
        browser.inspect(7.5 / 15 - .001, .92, "janeiro de 2026 — Cargos vagos: 101")
        browser.inspect(7.5 / 15, .08, "fevereiro de 2026 — Cargos vagos: 105")
        browser.inspect(7.5 / 15 + .001, .92, "fevereiro de 2026 — Cargos vagos: 105")
        browser.evaluate("document.querySelector('.chart-scroll').scrollLeft = 99999")
        browser.inspect(1, .08, "setembro de 2026 — Cargos vagos: 87")
        browser.leave()
    if args.case == "resize":
        browser.command("viewport", "--width", "1200", "--height", "1000")
        browser.command("wait", "--text", "outubro de 2025 — Cargos vagos: 93")
        assert browser.tooltip() == "outubro de 2025 — Cargos vagos: 93", browser.tooltip()
        browser.contained()
        browser.inspect(0, .92, "junho de 2025 — Cargos vagos: 79")


if __name__ == "__main__":
    main()
