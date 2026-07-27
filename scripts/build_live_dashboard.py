"""
Build a small interactive HTML dashboard for GitHub Pages.
Uses the cleaned scored customer table (no raw Telco file needed after build).
"""

from pathlib import Path
import json

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "02_clean" / "customer_churn_master.csv"
OUT = ROOT / "docs" / "live-dashboard" / "index.html"


def main() -> None:
    df = pd.read_csv(CSV)
    cols = [
        "customerID",
        "Contract",
        "TechSupport",
        "InternetService",
        "Tenure_Band",
        "PaymentMethod",
        "tenure",
        "MonthlyCharges",
        "Churn_Risk_Score",
        "Churn_Prob",
        "Focus_Flag",
        "Churn",
    ]
    table = df[cols].copy()
    table["MonthlyCharges"] = table["MonthlyCharges"].round(2)
    table["Churn_Risk_Score"] = table["Churn_Risk_Score"].round(1)
    table["Churn_Prob"] = table["Churn_Prob"].round(3)

    focus = table[table["Focus_Flag"] != "Ok / monitor"]
    kpis = {
        "customers": int(table.shape[0]),
        "churn_rate": round(float((df["Churn_Flag"] == 1).mean() * 100), 1),
        "avg_monthly": round(float(df["MonthlyCharges"].mean()), 2),
        "avg_risk": round(float(df["Churn_Risk_Score"].mean()), 1),
        "focus": int(len(focus)),
    }

    # Live page uses a sample of focus + random monitor rows so the HTML stays small
    focus_rows = table[table["Focus_Flag"] != "Ok / monitor"]
    monitor = table[table["Focus_Flag"] == "Ok / monitor"].sample(
        n=min(800, (table["Focus_Flag"] == "Ok / monitor").sum()),
        random_state=42,
    )
    page = pd.concat([focus_rows, monitor], ignore_index=True)

    records = json.loads(page.to_json(orient="records"))
    contracts = sorted(table["Contract"].dropna().unique().tolist())
    supports = sorted(table["TechSupport"].dropna().unique().tolist())
    internets = sorted(table["InternetService"].dropna().unique().tolist())
    bands = ["0-12", "13-24", "25-48", "49-72"]
    flags = [
        "High risk / high value",
        "Elevated risk (top 20%)",
        "Ok / monitor",
    ]

    # Full-population segment rates for the bar chart (not just the page sample)
    by_contract = (
        df.groupby("Contract", dropna=False)["Churn_Flag"]
        .mean()
        .mul(100)
        .round(1)
        .to_dict()
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Customer Churn Retention Scorecard</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body {{ margin: 0; font-family: Segoe UI, Tahoma, sans-serif; background: #f7f5f1; color: #1f1f1f; }}
    header {{ padding: 24px 28px; background: #efeae2; border-bottom: 1px solid #d9d4cb; }}
    h1 {{ margin: 0 0 6px; font-size: 26px; color: #1f4e5f; }}
    header p {{ margin: 0; color: #5c5c5c; max-width: 860px; line-height: 1.4; }}
    .wrap {{ padding: 18px 28px 36px; }}
    .filters {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 14px; align-items: end; }}
    label {{ display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #5c5c5c; }}
    select, input, button {{ padding: 8px 10px; border: 1px solid #d9d4cb; border-radius: 4px; background: #fff; font-size: 14px; }}
    button {{ background: #1f4e5f; color: #fff; border-color: #1f4e5f; cursor: pointer; }}
    .kpis {{ display: grid; grid-template-columns: repeat(5, minmax(110px, 1fr)); gap: 10px; margin-bottom: 14px; }}
    .kpi {{ background: #fff; border: 1px solid #d9d4cb; padding: 12px 14px; }}
    .kpi .lbl {{ font-size: 12px; color: #5c5c5c; }}
    .kpi .val {{ font-size: 22px; margin-top: 4px; color: #1f4e5f; font-weight: 650; }}
    .grid {{ display: grid; grid-template-columns: 1.1fr 0.9fr; gap: 12px; margin-bottom: 12px; }}
    .panel {{ background: #fff; border: 1px solid #d9d4cb; padding: 6px; }}
    .table-wrap {{ max-height: 420px; overflow: auto; border: 1px solid #d9d4cb; background: #fff; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #d9d4cb; padding: 7px 9px; text-align: left; white-space: nowrap; }}
    th {{ position: sticky; top: 0; background: #f3efe8; }}
    .note {{ margin-top: 10px; color: #5c5c5c; font-size: 12px; }}
    @media (max-width: 980px) {{ .grid, .kpis {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Customer Churn Retention Scorecard</h1>
    <p>Who is likely to leave, which accounts are worth saving first, and which contract / support patterns drive churn. Risk score = logistic regression churn probability × 100.</p>
  </header>
  <div class="wrap">
    <div class="filters">
      <label>Contract<select id="contract"><option value="">All contracts</option></select></label>
      <label>Tech support<select id="support"><option value="">All</option></select></label>
      <label>Internet<select id="internet"><option value="">All</option></select></label>
      <label>Tenure band<select id="band"><option value="">All bands</option></select></label>
      <label>Focus flag<select id="flag"><option value="">All flags</option></select></label>
      <label>Search<input id="q" type="text" placeholder="Customer ID" /></label>
      <button id="reset" type="button">Reset</button>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="lbl">Customers (view)</div><div class="val" id="kN">-</div></div>
      <div class="kpi"><div class="lbl">Churn rate %</div><div class="val" id="kC">-</div></div>
      <div class="kpi"><div class="lbl">Avg monthly $</div><div class="val" id="kM">-</div></div>
      <div class="kpi"><div class="lbl">Avg risk score</div><div class="val" id="kR">-</div></div>
      <div class="kpi"><div class="lbl">On focus list</div><div class="val" id="kF">-</div></div>
    </div>
    <div class="grid">
      <div class="panel"><div id="scatter"></div></div>
      <div class="panel"><div id="bars"></div></div>
    </div>
    <div class="panel">
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Customer</th><th>Contract</th><th>TechSupport</th><th>Internet</th>
              <th>Tenure</th><th>Monthly $</th><th>Risk</th><th>Flag</th><th>Churn</th>
            </tr>
          </thead>
          <tbody id="tbody"></tbody>
        </table>
      </div>
      <p class="note">Baseline roster: {kpis['customers']} customers, churn rate {kpis['churn_rate']}%, avg monthly ${kpis['avg_monthly']}, {kpis['focus']} on the focus list. Table shows all focus customers plus a sample of Ok / monitor. Source: IBM Telco Customer Churn public sample.</p>
    </div>
  </div>
  <script>
    const DATA = {json.dumps(records)};
    const CONTRACTS = {json.dumps(contracts)};
    const SUPPORTS = {json.dumps(supports)};
    const INTERNETS = {json.dumps(internets)};
    const BANDS = {json.dumps(bands)};
    const FLAGS = {json.dumps(flags)};
    const CONTRACT_RATES = {json.dumps(by_contract)};
    const BASE = {json.dumps(kpis)};
    const contract = document.getElementById('contract');
    const support = document.getElementById('support');
    const internet = document.getElementById('internet');
    const band = document.getElementById('band');
    const flag = document.getElementById('flag');
    const q = document.getElementById('q');
    CONTRACTS.forEach(s => {{ const o=document.createElement('option'); o.value=s; o.textContent=s; contract.appendChild(o); }});
    SUPPORTS.forEach(s => {{ const o=document.createElement('option'); o.value=s; o.textContent=s; support.appendChild(o); }});
    INTERNETS.forEach(s => {{ const o=document.createElement('option'); o.value=s; o.textContent=s; internet.appendChild(o); }});
    BANDS.forEach(s => {{ const o=document.createElement('option'); o.value=s; o.textContent=s; band.appendChild(o); }});
    FLAGS.forEach(s => {{ const o=document.createElement('option'); o.value=s; o.textContent=s; flag.appendChild(o); }});
    const num = v => (v===null || v===undefined || v==='') ? null : Number(v);
    const avg = arr => {{ const a=arr.filter(v => v!==null && !Number.isNaN(v)); return a.length ? a.reduce((x,y)=>x+y,0)/a.length : null; }};
    const fmt = (v,d=1) => (v===null || Number.isNaN(v)) ? '-' : Number(v).toFixed(d);
    function hasFilter() {{
      return !!(contract.value || support.value || internet.value || band.value || flag.value || q.value.trim());
    }}
    function filtered() {{
      const c=contract.value, s=support.value, i=internet.value, b=band.value, f=flag.value, qq=q.value.trim().toLowerCase();
      return DATA.filter(r => {{
        if (c && r.Contract !== c) return false;
        if (s && r.TechSupport !== s) return false;
        if (i && r.InternetService !== i) return false;
        if (b && r.Tenure_Band !== b) return false;
        if (f && r.Focus_Flag !== f) return false;
        if (qq && !((r.customerID||'').toLowerCase().includes(qq))) return false;
        return true;
      }});
    }}
    function refresh() {{
      const rows = filtered();
      // Unfiltered view uses full-roster baselines (table itself is a sample).
      if (!hasFilter()) {{
        document.getElementById('kN').textContent = BASE.customers;
        document.getElementById('kC').textContent = fmt(BASE.churn_rate, 1);
        document.getElementById('kM').textContent = fmt(BASE.avg_monthly, 2);
        document.getElementById('kR').textContent = fmt(BASE.avg_risk, 1);
        document.getElementById('kF').textContent = BASE.focus;
      }} else {{
        document.getElementById('kN').textContent = rows.length;
        document.getElementById('kC').textContent = fmt(100 * rows.filter(r => r.Churn === 'Yes').length / Math.max(rows.length,1), 1);
        document.getElementById('kM').textContent = fmt(avg(rows.map(r => num(r.MonthlyCharges))), 2);
        document.getElementById('kR').textContent = fmt(avg(rows.map(r => num(r.Churn_Risk_Score))), 1);
        document.getElementById('kF').textContent = rows.filter(r => r.Focus_Flag !== 'Ok / monitor').length;
      }}
      const body = document.getElementById('tbody');
      body.innerHTML = '';
      rows.slice(0, 400).forEach(r => {{
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${{r.customerID||''}}</td><td>${{r.Contract||''}}</td><td>${{r.TechSupport||''}}</td><td>${{r.InternetService||''}}</td><td>${{r.tenure||''}}</td><td>${{fmt(num(r.MonthlyCharges),2)}}</td><td>${{fmt(num(r.Churn_Risk_Score),1)}}</td><td>${{r.Focus_Flag||''}}</td><td>${{r.Churn||''}}</td>`;
        body.appendChild(tr);
      }});
      Plotly.newPlot('scatter', [{{
        x: rows.map(r => num(r.MonthlyCharges)),
        y: rows.map(r => num(r.Churn_Risk_Score)),
        text: rows.map(r => r.customerID),
        type: 'scattergl', mode: 'markers',
        marker: {{ size: 7, opacity: 0.65, color: rows.map(r => r.Focus_Flag === 'Ok / monitor' ? '#8aa3b0' : '#1f4e5f') }},
        hovertemplate: '%{{text}}<br>Monthly: $%{{x:.2f}}<br>Risk: %{{y:.1f}}<extra></extra>'
      }}], {{
        title: 'Churn risk vs monthly charges',
        xaxis: {{ title: 'Monthly charges ($)' }},
        yaxis: {{ title: 'Churn risk score (0-100)' }},
        height: 400, margin: {{ t: 40, r: 20, b: 50, l: 50 }},
        paper_bgcolor: '#fff', plot_bgcolor: '#fff'
      }}, {{responsive: true}});
      const keys = Object.keys(CONTRACT_RATES);
      Plotly.newPlot('bars', [{{
        type: 'bar',
        x: keys,
        y: keys.map(k => CONTRACT_RATES[k]),
        marker: {{ color: '#2a6f97' }},
        hovertemplate: '%{{x}}: %{{y:.1f}}%<extra></extra>'
      }}], {{
        title: 'Actual churn rate by contract (full roster)',
        xaxis: {{ title: 'Contract' }}, yaxis: {{ title: 'Churn rate %' }},
        height: 400, margin: {{ t: 40, r: 20, b: 80, l: 50 }}
      }}, {{responsive: true}});
    }}
    contract.onchange = support.onchange = internet.onchange = band.onchange = flag.onchange = q.oninput = refresh;
    document.getElementById('reset').onclick = () => {{
      contract.value=''; support.value=''; internet.value=''; band.value=''; flag.value=''; q.value=''; refresh();
    }};
    refresh();
  </script>
</body>
</html>
""",
        encoding="utf-8",
    )
    print("Wrote", OUT, "bytes", OUT.stat().st_size)


if __name__ == "__main__":
    main()
