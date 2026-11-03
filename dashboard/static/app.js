/* Dashboard page logic. Talks only to /api/v1/dashboard/*. */
(function () {
  "use strict";

  var C = window.DashCharts;
  var esc = C.esc;
  var API = "/api/v1/dashboard";

  var STATUS = {
    critical: { label: "Critical", icon: "■", rank: 0 },
    no_data:  { label: "No data",  icon: "○", rank: 1 },
    warning:  { label: "Warning",  icon: "▲", rank: 2 },
    normal:   { label: "Normal",   icon: "●", rank: 3 }
  };

  var SYSTEM_LABELS = {
    HVAC: "HVAC",
    NETWORKING: "Networking",
    ACCESS_CONTROL: "Access control",
    CCTV: "CCTV",
    FIRE_ALARM: "Fire alarm"
  };

  var options = null;
  var lastAssets = [];

  function $(id) { return document.getElementById(id); }

  function isoUtc(date) {
    return date.toISOString().replace(/\.\d{3}Z$/, "Z");
  }

  function systemLabel(code) { return SYSTEM_LABELS[code] || code; }

  function showError(message) {
    var box = $("banner");
    box.textContent = message;
    box.hidden = !message;
  }

  function badge(status) {
    var s = STATUS[status];
    return '<span class="badge ' + status + '"><span aria-hidden="true">' +
           s.icon + "</span> " + s.label + "</span>";
  }

  function formatValue(kpi) {
    if (!kpi.applicable || kpi.value === null || kpi.value === undefined) return "N/A";
    return String(kpi.value);
  }

  function unitLabel(unit) {
    return unit === "C" ? "°C" : unit;
  }

  // ---------- period ----------

  function currentQuery() {
    var params = [];
    var system = $("sel-system").value;
    var building = $("sel-building").value;
    if (system) params.push("system_type=" + encodeURIComponent(system));
    if (building) params.push("building_id=" + encodeURIComponent(building));

    var period = $("sel-period").value;
    if (period === "custom") {
      var a = $("custom-start").value, b = $("custom-end").value;
      if (a) params.push("start_time=" + encodeURIComponent(customToIso(a)));
      if (b) params.push("end_time=" + encodeURIComponent(customToIso(b)));
    } else if (period !== "full") {
      var end = new Date(Date.parse(options.data_end_exclusive));
      var start = new Date(end.getTime() - Number(period) * 3600 * 1000);
      params.push("start_time=" + encodeURIComponent(isoUtc(start)));
      params.push("end_time=" + encodeURIComponent(isoUtc(end)));
    }
    return params.join("&");
  }

  function customToIso(value) {
    var v = value.length === 16 ? value + ":00" : value;
    return v + "Z";
  }

  function toggleCustom() {
    $("custom-range").hidden = $("sel-period").value !== "custom";
  }

  // ---------- rendering ----------

  function renderMeta(data) {
    var p = data.period;
    $("meta").textContent =
      "Period (UTC): " + p.start + " to " + p.end_exclusive + " (end exclusive) · " +
      p.hours + " h · " + p.telemetry_records.toLocaleString() + " telemetry readings · " +
      p.event_records.toLocaleString() + " events";
  }

  function renderKpis(kpis) {
    $("kpis").innerHTML = kpis.map(function (k) {
      var na = !k.applicable || k.value === null || k.value === undefined;
      return (
        '<article class="card" data-kpi="' + esc(k.key) + '">' +
        '<h3>' + esc(k.name) + "</h3>" +
        '<p class="value' + (na ? " na" : "") + '">' + esc(formatValue(k)) +
        (na ? "" : ' <span class="unit">' + esc(unitLabel(k.unit)) + "</span>") + "</p>" +
        '<p class="detail">' + esc(k.detail || "") + "</p>" +
        "</article>"
      );
    }).join("");

    $("definitions").innerHTML = kpis.map(function (k) {
      return "<dt>" + esc(k.name) + " (" + esc(unitLabel(k.unit)) + ")</dt><dd>" +
             esc(k.definition) + '<br><span class="src">Source tables: ' +
             esc(k.source) + "</span></dd>";
    }).join("");
  }

  function segment(count, total, status) {
    if (!count) return "";
    return '<span class="seg ' + status + '" style="width:' +
           (count * 100 / total).toFixed(2) + '%" title="' + count + " " +
           STATUS[status].label + '"></span>';
  }

  function renderHealth(health) {
    var rows = health.by_system.slice();
    if (health.overall && rows.length > 1) rows.push(health.overall);

    $("health-body").innerHTML = rows.map(function (r) {
      var label = r.system_type === "ALL" ? "All systems" : systemLabel(r.system_type);
      return (
        '<tr class="' + (r.system_type === "ALL" ? "total" : "") + '">' +
        "<th scope=\"row\">" + esc(label) + "</th>" +
        "<td>" + r.assets + "</td>" +
        '<td><div class="bar" role="img" aria-label="' + esc(label) + ": " +
        r.normal + " normal, " + r.warning + " warning, " + r.critical + " critical, " +
        r.no_data + ' no data">' +
        segment(r.normal, r.assets, "normal") + segment(r.warning, r.assets, "warning") +
        segment(r.critical, r.assets, "critical") + segment(r.no_data, r.assets, "no_data") +
        "</div></td>" +
        "<td>" + r.normal + "</td><td>" + r.warning + "</td><td>" + r.critical +
        "</td><td>" + r.no_data + "</td>" +
        "<td><strong>" + r.healthy_pct + " %</strong></td></tr>"
      );
    }).join("");
  }

  function renderAssets() {
    var onlyIssues = $("only-issues").checked;
    var list = lastAssets.slice().sort(function (a, b) {
      return STATUS[a.status].rank - STATUS[b.status].rank ||
             a.asset_code.localeCompare(b.asset_code);
    });
    if (onlyIssues) list = list.filter(function (a) { return a.status !== "normal"; });

    $("assets-body").innerHTML = list.length ? list.map(function (a) {
      return (
        "<tr><th scope=\"row\">" + esc(a.asset_code) + "<br><span class=\"sub\">" +
        esc(a.name) + "</span></th>" +
        "<td>" + esc(systemLabel(a.system_type)) + "</td>" +
        "<td>" + esc(a.location_name) + "</td>" +
        "<td>" + badge(a.status) + "</td>" +
        "<td>" + a.warnings + " / " + a.criticals + "</td>" +
        '<td class="nowrap">' + esc(a.last_seen || "—") + "</td>" +
        '<td class="sub">' + esc(a.status_reason) + "</td></tr>"
      );
    }).join("") : '<tr><td colspan="7" class="sub">No assets to show.</td></tr>';
  }

  function renderTrends(t) {
    $("chart-alerts").innerHTML = C.stackedBarChart({
      labels: t.hours,
      width: 1140,
      unit: "alerts",
      ariaLabel: "Alerts per hour by severity",
      series: [
        { name: "warning", color: "#b45309", values: t.warnings },
        { name: "critical", color: "#b91c1c", values: t.criticals }
      ]
    });

    $("chart-temp").innerHTML = C.lineChart({
      labels: t.hours,
      width: 560,
      values: t.zone_temp.values,
      unit: "°C",
      color: "#1d4ed8",
      ariaLabel: "Average zone temperature per hour",
      emptyMessage: t.zone_temp.applicable
        ? "No zone temperature readings in this period"
        : "Not applicable to the selected system"
    });

    $("chart-bw").innerHTML = C.lineChart({
      labels: t.hours,
      width: 560,
      values: t.bandwidth.values,
      unit: "Mbps",
      color: "#0f766e",
      ariaLabel: "Average network bandwidth per hour",
      emptyMessage: t.bandwidth.applicable
        ? "No bandwidth readings in this period"
        : "Not applicable to the selected system"
    });
  }

  // ---------- loading ----------

  function fetchJson(url) {
    return fetch(url).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (!response.ok) {
          var detail = body && body.detail;
          throw new Error(typeof detail === "string" ? detail :
                          "Request failed (" + response.status + ").");
        }
        return body;
      });
    });
  }

  function load() {
    showError("");
    $("apply").disabled = true;
    var query = currentQuery();

    return fetchJson(API + "/overview" + (query ? "?" + query : ""))
      .then(function (data) {
        renderMeta(data);
        renderKpis(data.kpis);
        renderHealth(data.health);
        renderTrends(data.trends);
        lastAssets = data.assets;
        renderAssets();
      })
      .catch(function (err) { showError(err.message); })
      .then(function () { $("apply").disabled = false; });
  }

  function init() {
    fetchJson(API + "/filters").then(function (data) {
      options = data;

      var sys = $("sel-system");
      sys.innerHTML = '<option value="">All systems</option>' +
        data.systems.map(function (s) {
          return '<option value="' + esc(s.code) + '">' + esc(systemLabel(s.code)) +
                 " (" + s.assets + ")</option>";
        }).join("");

      var bld = $("sel-building");
      bld.innerHTML = '<option value="">All buildings</option>' +
        data.buildings.map(function (b) {
          return '<option value="' + b.building_id + '">' + esc(b.name) + "</option>";
        }).join("");

      $("custom-start").value = data.data_start.slice(0, 19);
      $("custom-end").value = data.data_end_exclusive.slice(0, 19);

      ["sel-system", "sel-building"].forEach(function (id) {
        $(id).addEventListener("change", load);
      });
      $("sel-period").addEventListener("change", function () {
        toggleCustom();
        if ($("sel-period").value !== "custom") load();
      });
      $("apply").addEventListener("click", load);
      $("only-issues").addEventListener("change", renderAssets);

      toggleCustom();
      return load();
    }).catch(function (err) { showError(err.message); });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
