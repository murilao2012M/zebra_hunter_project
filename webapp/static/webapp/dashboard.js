(function () {
  "use strict";

  const chartStore = {};

  function byId(id) {
    return document.getElementById(id);
  }

  function nowStamp() {
    return new Date().toLocaleString("pt-BR");
  }

  function setLastUpdate(text) {
    const el = byId("lastUpdateAt");
    if (el) el.textContent = text || nowStamp();
  }

  function parseInitialChartData() {
    const node = byId("dashboard-chart-data");
    if (!node) return {};
    try {
      return JSON.parse(node.textContent || "{}");
    } catch (err) {
      return {};
    }
  }

  function destroyCharts() {
    Object.values(chartStore).forEach((instance) => {
      if (instance && typeof instance.destroy === "function") {
        instance.destroy();
      }
    });
    chartStore.bankroll = null;
    chartStore.daily = null;
    chartStore.league = null;
    chartStore.status = null;
  }

  function chartDefaults() {
    if (!window.Chart) return;
    window.Chart.defaults.color = "#d4e4ff";
    window.Chart.defaults.borderColor = "#244a78";
    window.Chart.defaults.font.family = "Segoe UI, Inter, sans-serif";
  }

  function createChart(ctxId, config) {
    const node = byId(ctxId);
    if (!node || !window.Chart) return null;
    const ctx = node.getContext("2d");
    return new window.Chart(ctx, config);
  }

  function renderCharts(charts) {
    if (!window.Chart || !charts) return;
    chartDefaults();
    destroyCharts();

    const bankroll = charts.bankroll_curve || { labels: [], values: [] };
    const daily = charts.daily_pnl || { labels: [], values: [] };
    const league = charts.roi_by_league || { labels: [], values: [] };
    const status = charts.status_dist || { labels: ["G", "P", "E", "V"], values: [0, 0, 0, 0] };

    chartStore.bankroll = createChart("bankrollChart", {
      type: "line",
      data: {
        labels: bankroll.labels || [],
        datasets: [
          {
            label: "Banca",
            data: bankroll.values || [],
            borderColor: "#2e7bff",
            backgroundColor: "#2e7bff33",
            fill: true,
            borderWidth: 2,
            tension: 0.25,
            pointRadius: 0,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
      },
    });

    chartStore.daily = createChart("dailyPnlChart", {
      type: "bar",
      data: {
        labels: daily.labels || [],
        datasets: [
          {
            label: "Lucro diario",
            data: daily.values || [],
            borderWidth: 1,
            backgroundColor: (daily.values || []).map((v) => (v >= 0 ? "#16c5a4aa" : "#ff5f7daa")),
            borderColor: (daily.values || []).map((v) => (v >= 0 ? "#16c5a4" : "#ff5f7d")),
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
      },
    });

    chartStore.league = createChart("leagueRoiChart", {
      type: "bar",
      data: {
        labels: league.labels || [],
        datasets: [
          {
            label: "ROI %",
            data: league.values || [],
            backgroundColor: (league.values || []).map((v) => (v >= 0 ? "#2e7bffaa" : "#ff5f7daa")),
            borderColor: (league.values || []).map((v) => (v >= 0 ? "#2e7bff" : "#ff5f7d")),
            borderWidth: 1,
          },
        ],
      },
      options: {
        indexAxis: "y",
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
      },
    });

    chartStore.status = createChart("statusChart", {
      type: "doughnut",
      data: {
        labels: status.labels || ["G", "P", "E", "V"],
        datasets: [
          {
            data: status.values || [0, 0, 0, 0],
            backgroundColor: ["#16c5a4", "#ff5f7d", "#ffbc54", "#7aa6e8"],
            borderColor: "#16335d",
            borderWidth: 2,
          },
        ],
      },
      options: {
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "bottom",
            labels: { boxWidth: 12, boxHeight: 12 },
          },
        },
      },
    });
  }

  function fmtNumber(value, digits) {
    const n = Number(value);
    if (Number.isNaN(n)) return "0";
    return n.toFixed(digits);
  }

  function setKpi(key, value) {
    const el = document.querySelector(`[data-kpi="${key}"]`);
    if (!el) return;

    if (["hit_rate", "roi", "avg_edge", "avg_ev"].includes(key)) {
      el.textContent = `${fmtNumber(value, 2)}%`;
      return;
    }
    if (["bankroll", "profit_total"].includes(key)) {
      el.textContent = `$${fmtNumber(value, 2)}`;
      return;
    }
    if (["max_drawdown"].includes(key)) {
      el.textContent = fmtNumber(value, 2);
      return;
    }
    el.textContent = `${value ?? 0}`;
  }

  function replaceTableRows(tableId, rowsHtml) {
    const table = byId(tableId);
    if (!table) return;
    const tbody = table.querySelector("tbody");
    if (!tbody) return;
    tbody.innerHTML = rowsHtml;
  }

  function updateTables(data) {
    const leagues = data.top_leagues || [];
    const leaguesRows = leagues.length
      ? leagues
          .map(
            (r) =>
              `<tr><td>${r.league}</td><td>${r.picks}</td><td>${fmtNumber(r.profit, 2)}</td><td>${fmtNumber(
                r.roi,
                2
              )}%</td><td>${fmtNumber(r.hit_rate, 2)}%</td></tr>`
          )
          .join("")
      : '<tr><td colspan="5">Sem dados de ligas ainda.</td></tr>';
    replaceTableRows("topLeaguesTable", leaguesRows);

    const opps = data.latest_opportunities || [];
    const oppRows = opps.length
      ? opps
          .map(
            (o) =>
              `<tr><td>${o.match}</td><td>${o.underdog}</td><td>${fmtNumber(o.ev, 2)}%</td><td>${fmtNumber(
                o.edge,
                2
              )}%</td><td>${fmtNumber(o.conf, 2)}%</td></tr>`
          )
          .join("")
      : '<tr><td colspan="5">Sem oportunidades registradas.</td></tr>';
    replaceTableRows("latestOppsTable", oppRows);

    const jobs = data.latest_jobs || [];
    const jobsRows = jobs.length
      ? jobs.map((j) => `<tr><td>${j.kind}</td><td>${j.status}</td><td>${j.created_at}</td></tr>`).join("")
      : '<tr><td colspan="3">Sem jobs ainda.</td></tr>';
    replaceTableRows("jobsTable", jobsRows);

    const scans = data.latest_scans || [];
    const scansRows = scans.length
      ? scans.map((s) => `<tr><td>${s.id}</td><td>${s.status}</td><td>${s.started_at}</td><td>${s.top}</td></tr>`).join("")
      : '<tr><td colspan="4">Sem scans ainda.</td></tr>';
    replaceTableRows("scansTable", scansRows);
  }

  function updateKpis(kpis) {
    if (!kpis) return;
    Object.keys(kpis).forEach((key) => setKpi(key, kpis[key]));
  }

  async function refreshDashboard() {
    try {
      const res = await fetch("/api/dashboard/summary/", { credentials: "same-origin" });
      if (!res.ok) return;
      const body = await res.json();
      if (!body || !body.ok || !body.data) return;
      updateKpis(body.data.kpis || {});
      updateTables(body.data);
      renderCharts(body.data.charts || {});
      setLastUpdate(nowStamp());
    } catch (err) {
      setLastUpdate(`${nowStamp()} (falha ao atualizar)`);
    }
  }

  function bindEvents() {
    const refreshBtn = byId("refreshDashboardBtn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", refreshDashboard);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    renderCharts(parseInitialChartData());
    bindEvents();
    setLastUpdate(nowStamp());
    window.setInterval(refreshDashboard, 60000);
  });
})();
