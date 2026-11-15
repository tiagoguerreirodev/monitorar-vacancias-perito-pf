/* Optional mouse enhancement; the rendered chart/table remain the source of truth. */
(() => {
  "use strict";
  const svg = document.querySelector("#history-chart");
  const plot = document.querySelector("#history-plot");
  const table = document.querySelector("#history-values");
  if (!svg || !plot || !table) return;
  const months = Array.from(table.tBodies[0].rows);
  const bounds = plot.getBBox();
  const readout = document.createElement("p");
  readout.className = "inspection-readout";
  const label = document.createElement("strong");
  label.textContent = "Última inspeção: ";
  const valueText = document.createElement("span");
  valueText.className = "inspection-value";
  valueText.textContent = "Mova o ponteiro sobre o gráfico para inspecionar um mês, ou consulte a tabela abaixo.";
  readout.append(label, valueText);
  svg.parentElement.after(readout);
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
    valueText.textContent = `${row.cells[0].textContent} — ${value}`;
    const x = months.length === 1 ? bounds.x + bounds.width / 2
      : bounds.x + index * bounds.width / (months.length - 1);
    guide.setAttribute("x1", x);
    guide.setAttribute("x2", x);
    guide.style.display = "";
  }
})();
