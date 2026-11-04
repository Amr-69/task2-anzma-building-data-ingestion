
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
  var currentScenario = "baseline";
  var currentIncidents = [];
  var selectedIncident = null;

  function $(id) { return document.getElementById(id); }

  // ---------- Page navigation ----------

  function showPage(pageName) {
    var operations = $("page-operations");
    var monitoring = $("page-monitoring");
    var buttons = document.querySelectorAll(".page-nav button[data-page]");

    operations.hidden = pageName !== "operations";
    monitoring.hidden = pageName !== "monitoring";

    buttons.forEach(function (button) {
      var active = button.getAttribute("data-page") === pageName;
      button.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  function initNavigation() {
    var buttons = document.querySelectorAll(".page-nav button[data-page]");

    buttons.forEach(function (button) {
      button.addEventListener("click", function () {
        showPage(button.getAttribute("data-page"));
      });
    });

    showPage("operations");
  }

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
    var s = STATUS[status] || STATUS.no_data;
    var safeStatus = STATUS[status] ? status : "no_data";

    return '<span class="badge ' + safeStatus + '"><span aria-hidden="true">' +
           s.icon + "</span> " + s.label + "</span>";
  }

  function formatValue(kpi) {
    if (!kpi.applicable || kpi.value === null || kpi.value === undefined) return "N/A";
    return String(kpi.value);
  }

  function unitLabel(unit) {
    return unit === "C" ? "°C" : unit;
  }

  // ---------- Day 3 period filters ----------

  function currentQuery() {
    var params = [];
    var system = $("sel-system").value;
    var building = $("sel-building").value;

    if (system) params.push("system_type=" + encodeURIComponent(system));
    if (building) params.push("building_id=" + encodeURIComponent(building));

    var period = $("sel-period").value;

    if (period === "custom") {
      var a = $("custom-start").value;
      var b = $("custom-end").value;

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

  // ---------- Day 3 rendering ----------

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

    if (onlyIssues) {
      list = list.filter(function (a) { return a.status !== "normal"; });
    }

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

  // ---------- Shared API helper ----------

  function fetchJson(url) {
    return fetch(url).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (!response.ok) {
          var detail = body && body.detail;

          throw new Error(
            typeof detail === "string" ? detail :
            "Request failed (" + response.status + ")."
          );
        }

        return body;
      });
    });
  }

  // ---------- Day 3 loading ----------

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
      .catch(function (err) {
        showError(err.message);
      })
      .then(function () {
        $("apply").disabled = false;
      });
  }

  // ---------- Day 4 alert rendering ----------

  function alertStatus(message) {
    $("alert-status").textContent = message;
  }

  function clearAlertDetail() {
    selectedIncident = null;
    $("alert-detail").innerHTML = "";
    $("alert-detail").hidden = true;
  }

  function renderIncidents(data) {
    currentIncidents = data.incidents || [];
    clearAlertDetail();

    $("alert-scenario-description").textContent = data.scenario_name || "";

    if (!currentIncidents.length) {
      $("alert-incidents-body").innerHTML =
        '<tr><td colspan="8" class="alert-empty">No incidents detected in this scenario.</td></tr>';

      alertStatus("No incidents found. This is expected for the baseline dataset.");
      return;
    }

    $("alert-incidents-body").innerHTML = currentIncidents.map(function (incident) {
      return (
        '<tr data-incident="' + incident.incident_index + '">' +
        "<td>" + esc(incident.asset_code) + "</td>" +
        "<td>" + esc(incident.metric) + "</td>" +
        "<td>" + badge(incident.severity) + "</td>" +
        "<td>" + esc(incident.status) + "</td>" +
        '<td class="nowrap">' + esc(incident.start_ts) + "</td>" +
        "<td>" + esc(String(incident.peak_value)) + "</td>" +
        "<td>" + incident.readings_count + "</td>" +
        '<td><button type="button" data-detail="' + incident.incident_index + '">View</button></td>' +
        "</tr>"
      );
    }).join("");

    alertStatus(
      currentIncidents.length + " incident(s) detected. Select View to inspect evidence and explanation."
    );
  }

  function renderList(items, renderItem) {
    if (!items || !items.length) {
      return '<p class="muted">None recorded.</p>';
    }

    return "<ul>" + items.map(renderItem).join("") + "</ul>";
  }

  function renderIncidentDetail(result) {
    var ev = result.evidence;
    var explanation = result.explanation;
    var asset = ev.asset;
    var normal = ev.normal_before;
    var thresholds = ev.thresholds;

    var readingsById = {};
    (ev.key_readings || []).forEach(function (reading) {
      readingsById[String(reading.telemetry_id)] = reading;
    });

    var actionsById = {};
    (ev.candidate_actions || []).forEach(function (action) {
      actionsById[action.id] = action.text;
    });

    var citations = renderList(
      explanation.cited_readings,
      function (id) {
        var reading = readingsById[String(id)];

        if (!reading) {
          return "<li>Telemetry ID " + esc(String(id)) + " (reading details unavailable)</li>";
        }

        return (
          "<li><strong>ID " + esc(String(id)) + "</strong>: " +
          esc(String(reading.value)) + " " + esc(ev.unit) +
          " at " + esc(reading.ts) +
          " (Z-score: " + esc(String(reading.z)) + ")</li>"
        );
      }
    );

    var actions = renderList(
      explanation.recommended_action_ids,
      function (id) {
        var text = actionsById[id];

        return (
          "<li><strong>" + esc(id) + "</strong>: " +
          esc(text || "Action description unavailable.") + "</li>"
        );
      }
    );

    var causes = renderList(
      explanation.possible_causes,
      function (cause) { return "<li>" + esc(cause) + "</li>"; }
    );

    var events = renderList(
      ev.related_events,
      function (event) {
        return (
          "<li><strong>" + esc(event.type) + "</strong> — " +
          esc(event.severity) + " at " + esc(event.ts) +
          (event.details ? ": " + esc(event.details) : "") +
          " (event ID " + esc(String(event.event_id)) + ")</li>"
        );
      }
    );

    var normalHtml = normal
      ? (
        "<p>Median: " + esc(String(normal.median)) + " " + esc(ev.unit) + "</p>" +
        "<p>Minimum: " + esc(String(normal.min)) + " " + esc(ev.unit) + "</p>" +
        "<p>Maximum: " + esc(String(normal.max)) + " " + esc(ev.unit) + "</p>" +
        "<p>Samples: " + esc(String(normal.count)) + "</p>"
      )
      : '<p class="muted">No preceding baseline readings available.</p>';

    var sourceLabel = result.source === "llm"
      ? "LLM-generated possible causes"
      : "Template fallback — AI explanation unavailable";

    var detail = $("alert-detail");

    detail.innerHTML =
      '<div class="detail-grid">' +
        '<div class="detail-block">' +
          "<h3>Incident</h3>" +
          "<p><strong>" + esc(asset.code) + " — " + esc(asset.name) + "</strong></p>" +
          "<p>Metric: " + esc(ev.metric) + " (" + esc(ev.unit) + ")</p>" +
          "<p>Location: " + esc(asset.location) + ", floor " + esc(String(asset.floor)) + "</p>" +
          "<p>System: " + esc(asset.system) + "</p>" +
          "<p>Severity: " + badge(ev.severity) + "</p>" +
          "<p>Status: " + esc(ev.status) + "</p>" +
          "<p>Readings: " + esc(String(ev.readings_in_incident)) +
          " · Duration: " + esc(String(ev.duration_minutes)) + " minutes</p>" +
        "</div>" +

        '<div class="detail-block">' +
          "<h3>Explanation</h3>" +
          "<p>" + esc(explanation.summary) + "</p>" +
          '<p class="muted">' + esc(sourceLabel) +
          (result.model ? " · " + esc(result.model) : "") + "</p>" +
          "<h3>Severity justification</h3>" +
          "<p>" + esc(ev.severity_explanation) + "</p>" +
        "</div>" +
      "</div>" +

      '<div class="detail-grid" style="margin-top:12px">' +
        '<div class="detail-block">' +
          "<h3>Thresholds</h3>" +
          "<p>Direction: " + esc(thresholds.direction) + "</p>" +
          "<p>Warning: " + esc(String(thresholds.warning)) + " " + esc(ev.unit) + "</p>" +
          "<p>Critical: " + esc(String(thresholds.critical)) + " " + esc(ev.unit) + "</p>" +
        "</div>" +
        '<div class="detail-block">' +
          "<h3>Normal readings before incident</h3>" +
          normalHtml +
        "</div>" +
      "</div>" +

      "<h3>Evidence readings</h3>" + citations +
      "<h3>Possible causes</h3>" + causes +
      "<h3>Recommended corrective actions</h3>" + actions +
      "<h3>Evidence limitations</h3>" +
      "<p>" + esc(explanation.evidence_limits) + "</p>" +
      "<h3>Related events</h3>" + events;

    detail.hidden = false;
  }

  function loadIncidentDetail(index) {
    selectedIncident = index;
    alertStatus("Loading incident evidence and generating explanation…");

    var scenario = encodeURIComponent(currentScenario);
    var url = API + "/alerts/" + encodeURIComponent(index) + "?scenario=" + scenario;

    var buttons = $("alert-incidents-body").querySelectorAll("button[data-detail]");

    buttons.forEach(function (button) {
      button.disabled = true;
    });

    clearAlertDetail();
    selectedIncident = index;

    return fetchJson(url)
      .then(function (result) {
        if (selectedIncident !== index) return;

        renderIncidentDetail(result);
        alertStatus(
          "Incident details loaded. Explanation source: " +
          (result.source === "llm" ? "Ollama" : "template fallback") +
          ". Generation time: " + result.seconds + " seconds."
        );
      })
      .catch(function (err) {
        if (selectedIncident !== index) return;

        alertStatus("Unable to load incident details: " + err.message);
        $("alert-detail").hidden = false;
        $("alert-detail").textContent = "Incident detail could not be loaded.";
      })
      .then(function () {
        buttons.forEach(function (button) {
          button.disabled = false;
        });
      });
  }

  function loadAlerts() {
    var scenario = $("alert-scenario").value;

    currentScenario = scenario;
    currentIncidents = [];
    clearAlertDetail();

    $("alert-refresh").disabled = true;
    $("alert-incidents-body").innerHTML =
      '<tr><td colspan="8" class="alert-empty">Loading incidents…</td></tr>';

    alertStatus("Analyzing scenario…");

    return fetchJson(API + "/alerts?scenario=" + encodeURIComponent(scenario))
      .then(function (data) {
        renderIncidents(data);
      })
      .catch(function (err) {
        $("alert-incidents-body").innerHTML =
          '<tr><td colspan="8" class="alert-empty">Unable to load incidents.</td></tr>';

        $("alert-scenario-description").textContent = "";
        alertStatus("Alert loading failed: " + err.message);
      })
      .then(function () {
        $("alert-refresh").disabled = false;
      });
  }

  // ---------- Initialization ----------

  function init() {
    initNavigation();

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

      $("alert-refresh").addEventListener("click", loadAlerts);
      $("alert-scenario").addEventListener("change", loadAlerts);

      $("alert-incidents-body").addEventListener("click", function (event) {
        var button = event.target.closest("button[data-detail]");

        if (!button || button.disabled) return;

        loadIncidentDetail(Number(button.getAttribute("data-detail")));
      });

      toggleCustom();

      load();
      loadAlerts();
    }).catch(function (err) {
      showError(err.message);
      alertStatus("Dashboard initialization failed: " + err.message);
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
