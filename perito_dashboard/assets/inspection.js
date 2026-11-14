/* Optional mouse enhancement; the rendered chart/table remain the source of truth. */
(() => {
  "use strict";
  const svg = document.querySelector("#history-chart");
  const plot = document.querySelector("#history-plot");
  const table = document.querySelector("#history-values");
  if (!svg || !plot || !table) return;
  const months = Array.from(table.tBodies[0].rows);
  const bounds = plot.getBBox();
  const tooltip = document.createElement("div");
  tooltip.className = "inspection-tooltip";
  tooltip.setAttribute("role", "tooltip");
  tooltip.hidden = true;
  document.body.append(tooltip);
  const guide = document.createElementNS("http://www.w3.org/2000/svg", "line");
  guide.classList.add("inspection-guide");
  guide.setAttribute("y1", bounds.y);
  guide.setAttribute("y2", bounds.y + bounds.height);
  guide.style.display = "none";
  guide.setAttribute("aria-hidden", "true");
  svg.append(guide);
  plot.style.pointerEvents = "all";
  let pointer = null;
  function clear() {
    pointer = null;
    tooltip.hidden = true;
    guide.style.display = "none";
  }
  plot.addEventListener("mouseleave", clear);
  plot.addEventListener("mousemove", (event) => {
    pointer = {clientX: event.clientX, clientY: event.clientY};
    inspect(pointer);
  });
  // A stationary mouse still inspects the month now underneath it after scrolling.
  window.addEventListener("scroll", () => { if (pointer) inspect(pointer); }, true);
  window.addEventListener("resize", () => { if (pointer) inspect(pointer); });
  new ResizeObserver(() => { if (pointer) inspect(pointer); }).observe(svg);

  function inspect(event) {
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const local = point.matrixTransform(svg.getScreenCTM().inverse());
    if (document.elementFromPoint(event.clientX, event.clientY) !== plot) {
      clear();
      return;
    }
    // Equal-distance boundaries choose the later calendar month.
    const index = Math.max(0, Math.min(months.length - 1,
      Math.round((local.x - bounds.x) / bounds.width * (months.length - 1))));
    const row = months[index];
    const value = row.cells.length === 2 ? "dados indisponíveis"
      : `Cargos vagos: ${row.cells[2].textContent}`;
    tooltip.textContent = `${row.cells[0].textContent} — ${value}`;
    tooltip.hidden = false;
    const clip = svg.parentElement.getBoundingClientRect();
    const left = Math.max(8, clip.left);
    const right = Math.min(document.documentElement.clientWidth - 8, clip.right);
    tooltip.style.maxWidth = `${right - left}px`;
    // Measure at a stable origin: edge positioning must not squeeze/wrap the text.
    tooltip.style.left = `${left}px`;
    tooltip.style.top = "8px";
    const box = tooltip.getBoundingClientRect();
    tooltip.style.left = `${Math.max(left, Math.min(event.clientX + 12, right - box.width))}px`;
    const top = event.clientY + 12 + box.height > innerHeight - 8
      ? event.clientY - box.height - 12 : event.clientY + 12;
    tooltip.style.top = `${Math.max(8, Math.min(top, innerHeight - box.height - 8))}px`;
    const x = months.length === 1 ? bounds.x + bounds.width / 2
      : bounds.x + index * bounds.width / (months.length - 1);
    guide.setAttribute("x1", x);
    guide.setAttribute("x2", x);
    guide.style.display = "";
  }
})();
