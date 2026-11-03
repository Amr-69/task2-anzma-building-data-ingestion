/* Minimal SVG charts for the dashboard. No external libraries, works offline.
 *
 * Each function returns an SVG string. Hover text is provided by <title>
 * elements, so every bar and point has a native tooltip.
 */
(function (root) {
  "use strict";

  var W = 640, H = 230;
  var M = { left: 46, right: 12, top: 12, bottom: 30 };
  var PW = W - M.left - M.right;
  var PH = H - M.top - M.bottom;

  /* The SVG is drawn at the width it will be shown at, so text keeps its size. */
  function setLayout(width) {
    W = Math.max(320, Math.round(width || 640));
    PW = W - M.left - M.right;
  }

  function esc(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function niceNumber(x) {
    var exp = Math.pow(10, Math.floor(Math.log10(x)));
    var f = x / exp;
    var nf = f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10;
    return nf * exp;
  }

  function ticks(min, max, count, integersOnly) {
    var range = max - min;
    if (!(range > 0)) { range = Math.abs(max) || 1; min = max - range; }
    var step = niceNumber(range / count);
    if (integersOnly) step = Math.max(1, Math.round(step));
    var start = Math.floor(min / step) * step;
    var end = Math.ceil(max / step) * step;
    var list = [];
    for (var v = start; v <= end + step / 2; v += step) {
      list.push(Math.round(v * 1e6) / 1e6);
    }
    return list;
  }

  function labelText(labels, i) {
    var hhmm = labels[i].slice(11, 16);
    if (i === 0 || hhmm === "00:00") return labels[i].slice(5, 10) + " " + hhmm;
    return hhmm;
  }

  function empty(message) {
    return (
      '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' + esc(message) + '">' +
      '<text class="ax" x="' + W / 2 + '" y="' + H / 2 + '" text-anchor="middle">' +
      esc(message) + "</text></svg>"
    );
  }

  function frame(yTicks, yMin, yMax, labels, n, xAt, unit) {
    var out = "";
    yTicks.forEach(function (t) {
      var y = M.top + PH - ((t - yMin) / (yMax - yMin)) * PH;
      out += '<line class="grid" x1="' + M.left + '" x2="' + (W - M.right) +
             '" y1="' + y.toFixed(1) + '" y2="' + y.toFixed(1) + '"/>';
      out += '<text class="ax" x="' + (M.left - 6) + '" y="' + (y + 4).toFixed(1) +
             '" text-anchor="end">' + esc(t) + "</text>";
    });
    var every = Math.max(1, Math.ceil(n / 8));
    for (var i = 0; i < n; i += every) {
      out += '<text class="ax" x="' + xAt(i).toFixed(1) + '" y="' + (H - 10) +
             '" text-anchor="middle">' + esc(labelText(labels, i)) + "</text>";
    }
    if (unit) {
      out += '<text class="ax" x="' + M.left + '" y="9" text-anchor="start">' +
             esc(unit) + "</text>";
    }
    return out;
  }

  /* values: array of numbers or null. Gaps are drawn for null values. */
  function lineChart(opts) {
    setLayout(opts.width);
    var labels = opts.labels || [];
    var values = opts.values || [];
    var present = values.filter(function (v) { return v !== null && v !== undefined; });
    if (!labels.length || !present.length) {
      return empty(opts.emptyMessage || "No data for the selected filters");
    }

    var lo = Math.min.apply(null, present);
    var hi = Math.max.apply(null, present);
    var pad = (hi - lo) * 0.15 || Math.abs(hi) * 0.05 || 1;
    var t = ticks(lo - pad, hi + pad, 4, false);
    var yMin = t[0], yMax = t[t.length - 1];
    var n = labels.length;
    var xAt = function (i) { return n === 1 ? M.left + PW / 2 : M.left + (i / (n - 1)) * PW; };
    var yAt = function (v) { return M.top + PH - ((v - yMin) / (yMax - yMin)) * PH; };

    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' +
              esc(opts.ariaLabel || "Line chart") + '">';
    svg += frame(t, yMin, yMax, labels, n, xAt, opts.unit);

    var path = "", pen = false;
    values.forEach(function (v, i) {
      if (v === null || v === undefined) { pen = false; return; }
      path += (pen ? "L" : "M") + xAt(i).toFixed(1) + " " + yAt(v).toFixed(1) + " ";
      pen = true;
    });
    svg += '<path d="' + path + '" fill="none" stroke="' + esc(opts.color || "#1d4ed8") +
           '" stroke-width="2" stroke-linejoin="round"/>';

    var r = n > 80 ? 1.5 : 3;
    values.forEach(function (v, i) {
      if (v === null || v === undefined) return;
      svg += '<circle cx="' + xAt(i).toFixed(1) + '" cy="' + yAt(v).toFixed(1) +
             '" r="' + r + '" fill="' + esc(opts.color || "#1d4ed8") + '"><title>' +
             esc(labels[i] + ": " + v + " " + (opts.unit || "")) + "</title></circle>";
    });
    return svg + "</svg>";
  }

  /* series: [{name, color, values:[numbers]}], stacked in the given order. */
  function stackedBarChart(opts) {
    setLayout(opts.width);
    var labels = opts.labels || [];
    var series = opts.series || [];
    var n = labels.length;
    var totals = labels.map(function (_, i) {
      return series.reduce(function (sum, s) { return sum + (s.values[i] || 0); }, 0);
    });
    var max = Math.max.apply(null, totals.concat([0]));

    var yMax = max > 0 ? ticks(0, max, 4, true) : [0, 1];
    var yTop = yMax[yMax.length - 1];
    var xAt = function (i) { return M.left + ((i + 0.5) / n) * PW; };

    if (!n) return empty(opts.emptyMessage || "No data for the selected filters");

    var svg = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' +
              esc(opts.ariaLabel || "Bar chart") + '">';
    svg += frame(yMax, 0, yTop, labels, n, xAt, opts.unit);

    var slot = PW / n;
    var barW = Math.max(1, slot * 0.7);
    labels.forEach(function (label, i) {
      var base = 0;
      var tip = [label + ":"];
      series.forEach(function (s) {
        var v = s.values[i] || 0;
        tip.push(v + " " + s.name);
        if (v <= 0) return;
        var h = (v / yTop) * PH;
        var y = M.top + PH - ((base + v) / yTop) * PH;
        svg += '<rect x="' + (xAt(i) - barW / 2).toFixed(1) + '" y="' + y.toFixed(1) +
               '" width="' + barW.toFixed(1) + '" height="' + h.toFixed(1) +
               '" fill="' + esc(s.color) + '"><title>' + esc(tip.join(" ")) +
               "</title></rect>";
        base += v;
      });
    });
    if (max === 0) {
      svg += '<text class="ax" x="' + W / 2 + '" y="' + (M.top + PH / 2) +
             '" text-anchor="middle">No alerts in this period</text>';
    }
    return svg + "</svg>";
  }

  var api = { esc: esc, lineChart: lineChart, stackedBarChart: stackedBarChart, ticks: ticks };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.DashCharts = api;
})(typeof window !== "undefined" ? window : this);
