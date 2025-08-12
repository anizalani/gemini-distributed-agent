import os
import csv
import json
import html
import pytz
import logging
import psycopg2
from psycopg2 import pool
from io import StringIO
from datetime import datetime
from contextlib import contextmanager
from markupsafe import Markup, escape as m_escape
from dotenv import load_dotenv
from flask import (
    Flask, request, Response, render_template_string,
    send_from_directory, url_for
)

# --------------------
# Configuration & Log
# --------------------
dotenv_path = os.path.join(os.path.dirname(__file__), '.postgres.env')
load_dotenv(dotenv_path=dotenv_path)

DB_NAME = os.getenv("POSTGRES_DB")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5432"))

TARGET_TZ = pytz.timezone(os.getenv("APP_TIMEZONE", "America/Chicago"))
UI_MAX_WIDTH = os.getenv("UI_MAX_WIDTH", "1100px")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
DB_MAX_CONN = int(os.getenv("DB_MAX_CONN", "10"))
STMT_TIMEOUT = os.getenv("DB_STMT_TIMEOUT", "30s")  # e.g. 30s

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("gemma.webui")

# ---------------
# Flask & Paths
# ---------------
app = Flask(__name__)

PRIMARY_LOGS_DIR = os.path.join(app.root_path, 'gemma_logs')
SECONDARY_LOGS_DIR = os.path.join(app.root_path, 'logs')
LOGS_DIR = PRIMARY_LOGS_DIR if os.path.isdir(PRIMARY_LOGS_DIR) else SECONDARY_LOGS_DIR

# ---------------
# DB Connections
# ---------------
db_pool = None
try:
    db_pool = pool.ThreadedConnectionPool(
        minconn=1, maxconn=DB_MAX_CONN,
        dbname=DB_NAME, user=DB_USER, password=DB_PASS,
        host=DB_HOST, port=DB_PORT
    )
    logger.info("DB pool initialized")
except Exception as e:
    logger.error("Failed to create DB pool: %s", e)

@contextmanager
def get_conn():
    """Yield a pooled connection."""
    if not db_pool:
        raise RuntimeError("DB pool not initialized")
    conn = None
    try:
        conn = db_pool.getconn()
        yield conn
    finally:
        if conn:
            db_pool.putconn(conn)

@contextmanager
def get_cursor():
    """Yield a cursor with a statement timeout set."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f"SET LOCAL statement_timeout = '{STMT_TIMEOUT}'")
            except Exception as e:
                logger.warning("Failed to set statement_timeout: %s", e)
            yield conn, cur

# -----------------
# Safe HTML helpers
# -----------------
def safe_html(text):
    return html.escape("" if text is None else str(text), quote=True)

def safe_pre(text):
    return f"<pre>{safe_html(text)}</pre>" if text else ""

def convert_to_local_time(dt):
    if dt and isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=pytz.utc)
        return dt.astimezone(TARGET_TZ).strftime('%Y-%m-%d %H:%M:%S %Z')
    return dt


def badge(text, color="#6c757d"):
    # mark as safe HTML so we don't need any string-contains hacks later
    return Markup(f'<span class="badge" style="background:{m_escape(color)};">{m_escape(text)}</span>')

def bool_badge(val):
    if val is True:  return badge("✓", "#28a745")
    if val is False: return badge("✗", "#dc3545")
    return badge("—", "#6c757d")

def status_badge(s):
    return {
        "completed": badge("completed", "#28a745"),
        "failed":    badge("failed", "#dc3545"),
        "running":   badge("running", "#ffc107"),
        "queued":    badge("queued", "#6c757d"),
    }.get(s or "", badge(s or "—"))

# --------------------------
# Detect command_output join
# --------------------------
CO_JOIN_KEY = None  # caches detected column name

def ensure_co_join_key(conn):
    global CO_JOIN_KEY
    if CO_JOIN_KEY is not None:
        return CO_JOIN_KEY
    candidates = ['command_id', 'command_log_id', 'cmd_id', 'cl_id']
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name='command_output'
                  AND column_name = ANY(%s)
            """, (candidates,))
            found = [r[0] for r in cur.fetchall()]
            for c in candidates:
                if c in found:
                    CO_JOIN_KEY = c
                    break
            logger.info("Detected command_output join key: %s", CO_JOIN_KEY)
    except Exception as e:
        logger.warning("join-key detection failed: %s", e)
        CO_JOIN_KEY = None
    return CO_JOIN_KEY

def co_select_fragments(co_key):
    if co_key:
        select = "co.success, co.return_code, co.stdout, co.stderr"
        join   = f"LEFT JOIN command_output co ON co.{co_key} = cl.id"
    else:
        select = "NULL::bool AS success, NULL::int AS return_code, NULL::text AS stdout, NULL::text AS stderr"
        join   = ""
    return select, join

# -----------------
# HTML Base Layout
# -----------------
HTML_BASE = """
<!DOCTYPE html>
<html lang="en" data-theme="light">
<head>
<meta charset="UTF-8">
<title>Gemini Agent - {{ title }}</title>
{% if refresh_seconds %}<meta http-equiv="refresh" content="{{ refresh_seconds }}">{% endif %}
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
:root { --bg:#f7f7fb; --card:#fff; --text:#222; --muted:#666; --accent:#2979ff; --border:#eaeaea; }
[data-theme="dark"] { --bg:#0f1115; --card:#171a21; --text:#e6e6e6; --muted:#aaa; --accent:#4c8dff; --border:#2a2f3a; }
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif; background:var(--bg); color:var(--text); margin:0; }
nav { background:#222; display:flex; gap:.5rem; padding:.65rem 1rem; position:sticky; top:0; z-index:10; }
nav a { color:#fff; text-decoration:none; font-weight:600; padding:.4rem .6rem; border-radius:.4rem; }
nav a.active, nav a:hover { background:#444; }
.nav-right { margin-left:auto; display:flex; gap:.5rem; align-items:center; }
.container { max-width: """ + UI_MAX_WIDTH + """; margin: 1rem auto; padding: 0 1rem; }
h1 { margin: .25rem 0 1rem 0; }
.card-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px,1fr)); gap: .75rem; }
.card { background:var(--card); border:1px solid var(--border); border-radius:.6rem; padding: .9rem; box-shadow:0 2px 12px rgba(0,0,0,.04); }
.card .metric { font-size:1.6rem; font-weight:700; margin-top:.25rem; }
.card .desc { color:var(--muted); font-size:.9rem; }
.toolbar { display:flex; flex-wrap:wrap; gap:.5rem; align-items:center; margin:.6rem 0 1rem; }
.toolbar input, .toolbar select { padding:.35rem .5rem; background:var(--card); color:var(--text); border:1px solid var(--border); border-radius:.35rem; }
.btn { padding:.4rem .6rem; border:none; background:var(--accent); color:#fff; border-radius:.35rem; cursor:pointer; text-decoration:none; display:inline-block; }
.btn.secondary { background:#6c757d; }
.btn.link { background:transparent; color:var(--accent); text-decoration:underline; }
.badge { padding:.12rem .5rem; border-radius:.5rem; color:#fff; font-weight:600; font-size:.85rem; }
.table-wrap { overflow:auto; border-radius:.6rem; border:1px solid var(--border); }
table { width:100%; border-collapse:collapse; background:var(--card); }
th, td { padding:10px 12px; border-bottom:1px solid var(--border); vertical-align:top; }
thead { position:sticky; top: calc(0.65rem + 40px); background:var(--card); z-index:5; }
tr:nth-child(even) td { background:rgba(0,0,0,.02); }
.no-data { padding:2rem; text-align:center; color:var(--muted); }
pre { background:#0c0f14; color:#e6e6e6; padding:.8rem; border-radius:.5rem; overflow:auto; }
.kv td { border:none; padding:.3rem .6rem; }
.meta { color:var(--muted); font-size:.9rem; }
.copy { cursor:pointer; margin-left:.35rem; font-size:.85rem; color:var(--accent); }
.row-expand { cursor:pointer; }
.small { font-size:.9rem; color:var(--muted); }
</style>
<script>
(function(){ const s=localStorage.getItem('ui-theme'); if(s) document.documentElement.setAttribute('data-theme', s);})();
function toggleTheme(){ const r=document.documentElement; const cur=r.getAttribute('data-theme')||'light'; const nxt=(cur==='light')?'dark':'light'; r.setAttribute('data-theme',nxt); localStorage.setItem('ui-theme',nxt); }
function copyText(txt){ navigator.clipboard.writeText(txt).then(()=>{}); }
function toggleRow(id){ const el=document.getElementById(id); if(!el) return; el.style.display=(el.style.display==='none'||!el.style.display)?'table-row':'none'; }
</script>
</head>
<body>
<nav>
  <a href="{{ url_for('dashboard') }}" class="{{ 'active' if active=='dash' else '' }}">Dashboard</a>
  <a href="{{ url_for('analytics') }}" class="{{ 'active' if active=='analytics' else '' }}">Analytics</a>
  <a href="{{ url_for('view_command_log') }}" class="{{ 'active' if active=='cmdlog' else '' }}">Command Log</a>
  <a href="{{ url_for('index') }}" class="{{ 'active' if active=='usage' else '' }}">Usage</a>
  <a href="{{ url_for('view_tasks') }}" class="{{ 'active' if active=='tasks' else '' }}">Tasks</a>
  <a href="{{ url_for('view_keys') }}" class="{{ 'active' if active=='keys' else '' }}">Keys</a>
  <a href="{{ url_for('view_interactions') }}" class="{{ 'active' if active=='interactions' else '' }}">Interactions</a>
  <a href="{{ url_for('view_gemma_logs') }}" class="{{ 'active' if active=='logs' else '' }}">Logs</a>
  <div class="nav-right">
    <a class="btn secondary" href="?refresh={{ 0 if refresh_seconds else 5 }}">{{ 'Stop Auto-Refresh' if refresh_seconds else 'Auto-Refresh 5s' }}</a>
    <a class="btn secondary" onclick="toggleTheme()">🌓 Theme</a>
  </div>
</nav>
<div class="container">
  <h1>{{ title }}</h1>
  {% if toolbar %}{{ toolbar|safe }}{% endif %}
  {% if top %}<div class="card-grid">{{ top|safe }}</div>{% endif %}
  {% if error %}
    <div class="no-data">Error: {{ error }}</div>
  {% elif table %}
    <div class="table-wrap">{{ table|safe }}</div>
  {% else %}
    <div class="no-data">No entries found.</div>
  {% endif %}
</div>
</body>
</html>
"""

def render_page(title, active, table_html=None, toolbar_html=None, top_html=None, error=None, refresh=None):
    return render_template_string(
        HTML_BASE,
        title=title, active=active,
        table=table_html, toolbar=toolbar_html, top=top_html,
        error=error, refresh_seconds=refresh
    )

# -----------
# Dashboard
# -----------
@app.route('/')
@app.route('/dashboard')
def dashboard():
    refresh = request.args.get('refresh', type=int)
    error = None; top_html = ""; table_html = ""
    try:
        with get_conn() as conn:
            co_key = ensure_co_join_key(conn)
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = '{STMT_TIMEOUT}'")
                if co_key:
                    cur.execute(f"""
                        SELECT
                          COUNT(*) AS total,
                          SUM(CASE WHEN co.success IS TRUE THEN 1 ELSE 0 END) AS success_cnt,
                          SUM(CASE WHEN co.success IS FALSE THEN 1 ELSE 0 END) AS fail_cnt,
                          ROUND(AVG(EXTRACT(EPOCH FROM (cl.command_end_timestamp - cl.command_start_timestamp)))::numeric, 2) AS avg_sec,
                          PERCENTILE_CONT(0.5) WITHIN GROUP (
                            ORDER BY EXTRACT(EPOCH FROM (cl.command_end_timestamp - cl.command_start_timestamp))
                          ) AS p50_sec
                        FROM command_log cl
                        LEFT JOIN command_output co ON co.{co_key} = cl.id
                        WHERE cl.command_start_timestamp >= NOW() - INTERVAL '24 hours'
                          AND cl.command_end_timestamp IS NOT NULL
                    """)
                    total, success_cnt, fail_cnt, avg_sec, p50_sec = cur.fetchone()
                    success_rate = (float(success_cnt or 0) / total * 100.0) if total else 0.0
                else:
                    cur.execute("""
                        SELECT COUNT(*) AS total,
                               ROUND(AVG(EXTRACT(EPOCH FROM (cl.command_end_timestamp - cl.command_start_timestamp)))::numeric, 2) AS avg_sec,
                               PERCENTILE_CONT(0.5) WITHIN GROUP (
                                 ORDER BY EXTRACT(EPOCH FROM (cl.command_end_timestamp - cl.command_start_timestamp))
                               ) AS p50_sec
                        FROM command_log cl
                        WHERE cl.command_start_timestamp >= NOW() - INTERVAL '24 hours'
                          AND cl.command_end_timestamp IS NOT NULL
                    """)
                    total, avg_sec, p50_sec = cur.fetchone()
                    success_rate = None

                try:
                    cur.execute("""
                        SELECT COUNT(*) AS requests, COALESCE(SUM(token_count),0) AS tokens
                        FROM usage_log
                        WHERE request_timestamp >= NOW() - INTERVAL '24 hours'
                    """)
                    req_24h, tokens_24h = cur.fetchone()
                except Exception:
                    req_24h, tokens_24h = None, None

                cur.execute("""
                    SELECT cl.command, COUNT(*) c
                    FROM command_log cl
                    WHERE cl.command_start_timestamp >= NOW() - INTERVAL '24 hours'
                      AND COALESCE(NULLIF(TRIM(cl.command), ''), '') <> ''
                    GROUP BY cl.command
                    ORDER BY c DESC
                    LIMIT 5
                """)
                top_cmds = cur.fetchall()

                if co_key:
                    cur.execute(f"""
                        SELECT cl.id, cl.command, cl.permissions, co.return_code,
                               COALESCE(cl.executed_at, cl.command_start_timestamp) AS ts
                        FROM command_log cl
                        LEFT JOIN command_output co ON co.{co_key} = cl.id
                        WHERE co.success IS FALSE
                        ORDER BY ts DESC NULLS LAST
                        LIMIT 10
                    """)
                else:
                    cur.execute("""
                        SELECT cl.id, cl.command, cl.permissions, NULL::int as return_code,
                               COALESCE(cl.executed_at, cl.command_start_timestamp) AS ts
                        FROM command_log cl
                        WHERE cl.status='failed'
                        ORDER BY ts DESC NULLS LAST
                        LIMIT 10
                    """)
                recent_fail = cur.fetchall()

        cards = []
        cards.append(f'<div class="card"><div class="desc">Commands (24h)</div><div class="metric">{int(total or 0)}</div></div>')
        if success_rate is not None:
            cards.append(f'<div class="card"><div class="desc">Success Rate (24h)</div><div class="metric">{success_rate:.1f}%</div></div>')
        cards.append(f'<div class="card"><div class="desc">Median Duration</div><div class="metric">{(p50_sec or 0):.0f}s</div></div>')
        if req_24h is not None:
            cards.append(f'<div class="card"><div class="desc">Requests (24h)</div><div class="metric">{int(req_24h)}</div></div>')
            cards.append(f'<div class="card"><div class="desc">Tokens (24h)</div><div class="metric">{int(tokens_24h)}</div></div>')
        top_html = "".join(cards)

        rows = []
        rows.append('<tr><th colspan="4">Top Commands (24h)</th></tr>')
        if top_cmds:
            for cmd, cnt in top_cmds:
                rows.append(f"<tr><td colspan='3'><code>{safe_html(cmd)}</code></td><td class='small'>{cnt}</td></tr>")
        else:
            rows.append("<tr><td colspan='4' class='small'>No command data.</td></tr>")

        rows.append('<tr><th colspan="4">Recent Failures</th></tr>')
        if recent_fail:
            for cid, cmd, perm, rc, ts in recent_fail:
                rows.append(
                    f"<tr>"
                    f"<td><a href='{url_for('command_detail', cmd_id=cid)}'>{cid}</a></td>"
                    f"<td><code>{safe_html(cmd)}</code></td>"
                    f"<td class='small'>perm: {safe_html(perm) if perm else '—'} | rc: {rc if rc is not None else '—'}</td>"
                    f"<td class='small'>{convert_to_local_time(ts) or '—'}</td>"
                    f"</tr>"
                )
        else:
            rows.append("<tr><td colspan='4' class='small'>No failures recorded.</td></tr>")

        table_html = f"<table><tbody>{''.join(rows)}</tbody></table>"

    except Exception as e:
        logger.exception("Dashboard error")
        error = f"DB error: {e}"

    return render_page("Dashboard", "dash", table_html=table_html, top_html=top_html, error=error, refresh=refresh)

# -----------
# Analytics
# -----------
@app.route('/analytics')
def analytics():
    refresh = request.args.get('refresh', type=int)
    error, top_html, table_html = None, "", ""

    def to_hour_label(dt):
        if dt.tzinfo is None: dt = dt.replace(tzinfo=pytz.utc)
        return dt.astimezone(TARGET_TZ).strftime('%m-%d %H:%M')

    def to_day_label(dt):
        if dt.tzinfo is None: dt = dt.replace(tzinfo=pytz.utc)
        return dt.astimezone(TARGET_TZ).strftime('%m-%d')

    try:
        with get_cursor() as (conn, cur):
            cur.execute("""
                SELECT COUNT(*) AS requests, COALESCE(SUM(token_count),0) AS tokens
                FROM usage_log
                WHERE request_timestamp >= NOW() - INTERVAL '24 hours'
            """)
            req_24h, tokens_24h = cur.fetchone()

            cur.execute("""
                SELECT key_name, COALESCE(SUM(token_count),0) AS tokens
                FROM usage_log
                WHERE request_timestamp >= NOW() - INTERVAL '24 hours'
                GROUP BY key_name
                ORDER BY tokens DESC NULLS LAST
                LIMIT 1
            """)
            row = cur.fetchone()
            top_key = row[0] if row else None
            top_key_tokens = int(row[1]) if row else 0

            # keys table (optional)
            keys_rows = []
            try:
                cur.execute("""SELECT key_name, daily_request_count, daily_token_total, last_used,
                                      quota_exhausted, disabled_until
                               FROM api_keys ORDER BY key_name""")
                keys_rows = cur.fetchall()
            except Exception:
                keys_rows = []

            # keys for charts (7d)
            cur.execute("""
                SELECT DISTINCT key_name
                FROM usage_log
                WHERE request_timestamp >= NOW() - INTERVAL '7 days'
            """)
            keys = [r[0] for r in cur.fetchall() if r[0] is not None]
            keys.sort()

            # 24h hourly
            cur.execute("""
                WITH series AS (
                  SELECT generate_series(date_trunc('hour', NOW() - INTERVAL '23 hours'),
                                         date_trunc('hour', NOW()),
                                         INTERVAL '1 hour') AS hour_utc
                ),
                agg AS (
                  SELECT date_trunc('hour', request_timestamp) AS hour_utc,
                         key_name, COUNT(*) AS requests, COALESCE(SUM(token_count),0) AS tokens
                  FROM usage_log
                  WHERE request_timestamp >= NOW() - INTERVAL '24 hours'
                  GROUP BY 1,2
                )
                SELECT s.hour_utc, a.key_name, a.requests, a.tokens
                FROM series s
                LEFT JOIN agg a ON a.hour_utc = s.hour_utc
                ORDER BY s.hour_utc, a.key_name
            """)
            rows_24h = cur.fetchall()

            # 7d daily
            cur.execute("""
                WITH series AS (
                  SELECT generate_series(date_trunc('day', NOW() - INTERVAL '6 days'),
                                         date_trunc('day', NOW()),
                                         INTERVAL '1 day') AS day_utc
                ),
                agg AS (
                  SELECT date_trunc('day', request_timestamp) AS day_utc,
                         key_name, COUNT(*) AS requests, COALESCE(SUM(token_count),0) AS tokens
                  FROM usage_log
                  WHERE request_timestamp >= NOW() - INTERVAL '7 days'
                  GROUP BY 1,2
                )
                SELECT s.day_utc, a.key_name, a.requests, a.tokens
                FROM series s
                LEFT JOIN agg a ON a.day_utc = s.day_utc
                ORDER BY s.day_utc, a.key_name
            """)
            rows_7d = cur.fetchall()

        # Transform to Chart.js structures
        from collections import OrderedDict
        hours = OrderedDict()
        for hour_utc, _, _, _ in rows_24h:
            hours.setdefault(to_hour_label(hour_utc), None)
        hour_labels = list(hours.keys())

        days = OrderedDict()
        for day_utc, _, _, _ in rows_7d:
            days.setdefault(to_day_label(day_utc), None)
        day_labels = list(days.keys())

        per_key_req_24h = {k: [0]*len(hour_labels) for k in keys}
        per_key_tok_24h = {k: [0]*len(hour_labels) for k in keys}
        idx_hour = {lbl:i for i,lbl in enumerate(hour_labels)}
        for hour_utc, key, req, tok in rows_24h:
            if key is None: continue
            i = idx_hour[to_hour_label(hour_utc)]
            per_key_req_24h[key][i] = int(req or 0)
            per_key_tok_24h[key][i] = int(tok or 0)

        per_key_req_7d = {k: [0]*len(day_labels) for k in keys}
        per_key_tok_7d = {k: [0]*len(day_labels) for k in keys}
        idx_day = {lbl:i for i,lbl in enumerate(day_labels)}
        for day_utc, key, req, tok in rows_7d:
            if key is None: continue
            i = idx_day[to_day_label(day_utc)]
            per_key_req_7d[key][i] = int(req or 0)
            per_key_tok_7d[key][i] = int(tok or 0)

        cards = [
            f'<div class="card"><div class="desc">Requests (24h)</div><div class="metric">{int(req_24h or 0)}</div></div>',
            f'<div class="card"><div class="desc">Tokens (24h)</div><div class="metric">{int(tokens_24h or 0)}</div></div>',
        ]
        if top_key:
            cards.append(f'<div class="card"><div class="desc">Top Key (24h)</div><div class="metric">{safe_html(top_key)}</div><div class="desc">{top_key_tokens} tokens</div></div>')
        if keys_rows:
            cards.append(f'<div class="card"><div class="desc">Active Keys</div><div class="metric">{len(keys_rows)}</div></div>')
        top_html = "".join(cards)

        keys_table = ""
        if keys_rows:
            hdr = ["key_name","daily_requests","daily_tokens","last_used","quota","disabled_until"]
            rows_html = []
            for key_name, dr, dtok, last_used, qex, dis_until in keys_rows:
                rows_html.append(
                    "<tr>" +
                    f"<td>{safe_html(key_name)}</td>" +
                    f"<td>{dr}</td>" +
                    f"<td>{dtok}</td>" +
                    f"<td>{convert_to_local_time(last_used) if last_used else '—'}</td>" +
                    f"<td>{'exhausted' if qex else 'ok'}</td>" +
                    f"<td>{convert_to_local_time(dis_until) if dis_until else '—'}</td>" +
                    "</tr>"
                )
            keys_table = "<div class='table-wrap'><table><thead><tr>" + "".join(f"<th>{h}</th>" for h in hdr) + "</tr></thead><tbody>" + "".join(rows_html) + "</tbody></table></div>"

        import json as _json
        def build_ds(per_key): return _json.dumps([{"label":k,"data":per_key[k]} for k in keys])
        js_hour_labels = _json.dumps(hour_labels); js_day_labels = _json.dumps(day_labels)
        ds_req_24h = build_ds(per_key_req_24h); ds_tok_24h = build_ds(per_key_tok_24h)
        ds_req_7d  = build_ds(per_key_req_7d);  ds_tok_7d  = build_ds(per_key_tok_7d)

        charts_html = f"""
        <div class="card"><canvas id="req24"></canvas></div>
        <div class="card"><canvas id="tok24"></canvas></div>
        <div class="card"><canvas id="req7"></canvas></div>
        <div class="card"><canvas id="tok7"></canvas></div>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <script>
          const hourLabels = {js_hour_labels};
          const dayLabels  = {js_day_labels};
          const dsReq24 = {ds_req_24h};
          const dsTok24 = {ds_tok_24h};
          const dsReq7  = {ds_req_7d};
          const dsTok7  = {ds_tok_7d};
          function mkChart(elId, labels, datasets, title, stacked=true) {{
            const ctx = document.getElementById(elId).getContext('2d');
            const ds = datasets.map(d=>Object.assign({{borderWidth:1, fill: stacked}}, d));
            return new Chart(ctx, {{
              type: 'line',
              data: {{ labels, datasets: ds }},
              options: {{
                responsive: true, interaction: {{ mode: 'nearest', intersect: false }},
                plugins: {{ legend: {{ position: 'bottom' }}, title: {{ display: true, text: title }} }},
                scales: {{ y: {{ beginAtZero: true, stacked }} }}
              }}
            }});
          }}
          mkChart('req24', hourLabels, dsReq24, 'Requests by Key (24h)');
          mkChart('tok24', hourLabels, dsTok24, 'Tokens by Key (24h)');
          mkChart('req7',  dayLabels,  dsReq7,  'Requests by Key (7d)');
          mkChart('tok7',  dayLabels,  dsTok7,  'Tokens by Key (7d)');
        </script>
        """
        table_html = charts_html + (keys_table or "")

    except Exception as e:
        logger.exception("Analytics error")
        error = f"DB error: {e}"

    return render_page("Analytics", "analytics", table_html=table_html, top_html=top_html, error=error, refresh=refresh)

# -------
# Usage
# -------
@app.route('/usage')
def index():
    refresh = request.args.get('refresh', type=int)
    error, table_html = None, ""
    try:
        with get_cursor() as (conn, cur):
            cur.execute("""SELECT id, key_name, task_id, request_timestamp, token_count, request_type
                           FROM usage_log ORDER BY request_timestamp DESC LIMIT 1000;""")
            headers = [d[0] for d in cur.description]
            rows_html = []
            for row in cur.fetchall():
                row = list(row)
                row[3] = convert_to_local_time(row[3])
                cells = [safe_html(x) if not isinstance(x,(int,float)) else str(x) for x in row]
                rows_html.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            table_html = "<table><thead><tr>" + "".join(f"<th>{safe_html(h)}</th>" for h in headers) + "</tr></thead><tbody>" + "".join(rows_html) + "</tbody></table>"
    except Exception as e:
        logger.exception("Usage error")
        error = f"Database query failed: {e}"
    return render_page("Database Usage Logs", "usage", table_html=table_html, error=error, refresh=refresh)

# -------
# Tasks
# -------
@app.route('/tasks')
def view_tasks():
    refresh = request.args.get('refresh', type=int)
    error, table_html = None, ""
    try:
        with get_cursor() as (conn, cur):
            cur.execute("""SELECT id, status, last_updated, context FROM tasks ORDER BY last_updated DESC LIMIT 1000;""")
            headers = [d[0] for d in cur.description]
            rows_html = []
            for row in cur.fetchall():
                row = list(row)
                row[2] = convert_to_local_time(row[2])
                row[3] = f"<pre>{safe_html(json.dumps(row[3], indent=2))}</pre>"
                cells = [row[0], row[1], row[2], row[3]]
                rows_html.append("<tr>" + "".join(f"<td>{c if i==3 else safe_html(c)}</td>" for i,c in enumerate(cells)) + "</tr>")
            table_html = "<table><thead><tr>" + "".join(f"<th>{safe_html(h)}</th>" for h in headers) + "</tr></thead><tbody>" + "".join(rows_html) + "</tbody></table>"
    except Exception as e:
        logger.exception("Tasks error")
        error = f"Database query failed: {e}"
    return render_page("Tasks", "tasks", table_html=table_html, error=error, refresh=refresh)

# -----
# Keys
# -----
@app.route('/keys')
def view_keys():
    refresh = request.args.get('refresh', type=int)
    error, table_html = None, ""
    try:
        with get_cursor() as (conn, cur):
            cur.execute("""SELECT key_name, daily_request_count, daily_token_total, last_used,
                                  quota_exhausted, disabled_until
                           FROM api_keys ORDER BY last_used DESC NULLS LAST;""")
            headers = [d[0] for d in cur.description]
            rows_html = []
            for row in cur.fetchall():
                key_name, dr, dtok, last_used, qex, dis_until = row
                last_used = convert_to_local_time(last_used)
                dis_until = convert_to_local_time(dis_until)
                quota = badge("exhausted", "#dc3545") if qex else badge("ok", "#28a745")
                rows_html.append("<tr>" +
                    f"<td>{safe_html(key_name)}</td>" +
                    f"<td>{dr}</td><td>{dtok}</td>" +
                    f"<td>{last_used or '—'}</td><td>{quota}</td><td>{dis_until or '—'}</td>" +
                    "</tr>")
            table_html = "<table><thead><tr>" + "".join(f"<th>{safe_html(h)}</th>" for h in headers) + "</tr></thead><tbody>" + "".join(rows_html) + "</tbody></table>"
    except Exception as e:
        logger.exception("Keys error")
        error = f"Database query failed: {e}"
    return render_page("API Key Status", "keys", table_html=table_html, error=error, refresh=refresh)

# ---------------
# Interactions
# ---------------
@app.route('/interactions')
def view_interactions():
    refresh = request.args.get('refresh', type=int)
    error, table_html = None, ""
    try:
        with get_cursor() as (conn, cur):
            cur.execute("""SELECT id, task_id, prompt, response, request_timestamp
                           FROM interactions ORDER BY request_timestamp DESC LIMIT 1000;""")
            headers = [d[0] for d in cur.description]
            rows_html = []
            for row in cur.fetchall():
                row = list(row)
                row[4] = convert_to_local_time(row[4])
                row[2] = safe_pre(row[2])
                row[3] = safe_pre(row[3])
                # cells: id, task_id, prompt(pre), response(pre), ts
                cells = [row[0], row[1], row[2], row[3], row[4]]
                rows_html.append("<tr>" + "".join(
                    f"<td>{cells[i] if i in (2,3) else safe_html(cells[i])}</td>" for i in range(5)
                ) + "</tr>")
            table_html = "<table><thead><tr>" + "".join(f"<th>{safe_html(h)}</th>" for h in headers) + "</tr></thead><tbody>" + "".join(rows_html) + "</tbody></table>"
    except Exception as e:
        logger.exception("Interactions error")
        error = f"Database query failed: {e}"
    return render_page("All Interactions", "interactions", table_html=table_html, error=error, refresh=refresh)

# -------------------------------
# Command Log (filters/pager/CSV)
# -------------------------------
@app.route('/command_log')
def view_command_log():
    page = max(request.args.get('page', default=1, type=int), 1)
    page_size = max(min(request.args.get('page_size', default=50, type=int), 500), 1)
    offset = (page - 1) * page_size

    status = request.args.get('status')
    agent_mode = request.args.get('agent_mode')
    confirmed = request.args.get('confirmed')
    permissions = request.args.get('permissions')
    search = request.args.get('search')
    refresh = request.args.get('refresh', type=int)

    where, params = [], []
    if status:
        where.append("cl.status = %s"); params.append(status)
    if agent_mode:
        where.append("cl.agent_mode = %s"); params.append(agent_mode)
    if confirmed in ('true', 'false'):
        where.append("cl.user_confirmation = %s"); params.append(confirmed == 'true')
    if permissions:
        where.append("cl.permissions = %s"); params.append(permissions)
    if search:
        where.append("(cl.task_id ILIKE %s OR cl.command ILIKE %s OR cl.prompt ILIKE %s)")
        like = f"%{search}%"; params.extend([like, like, like])
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    order_sql = "ORDER BY COALESCE(cl.executed_at, cl.command_start_timestamp) DESC NULLS LAST, cl.id DESC"

    error, table_html, toolbar_html = None, "", ""
    try:
        with get_conn() as conn:
            co_key = ensure_co_join_key(conn)
            co_fields, co_join = co_select_fragments(co_key)
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = '{STMT_TIMEOUT}'")
                cur.execute(f"SELECT COUNT(*) FROM command_log cl {where_sql}", params)
                total = cur.fetchone()[0]

                cur.execute(f"""
                    SELECT
                        cl.id,
                        cl.task_id,
                        COALESCE(cl.executed_at, cl.command_start_timestamp) AS at,
                        cl.command,
                        cl.permissions,
                        cl.user_confirmation,
                        cl.agent_mode,
                        cl.status,
                        cl.command_start_timestamp,
                        cl.command_end_timestamp,
                        (EXTRACT(EPOCH FROM (cl.command_end_timestamp - cl.command_start_timestamp)))::INT AS duration_sec,
                        {co_fields},
                        cl.prompt
                    FROM command_log cl
                    {co_join}
                    {where_sql}
                    {order_sql}
                    LIMIT %s OFFSET %s
                """, params + [page_size, offset])
                rows = cur.fetchall()

        def opt(val, cur): return 'selected' if val == cur else ''
        toolbar_html = f"""
        <form method="get" class="toolbar">
          <input type="text" name="search" placeholder="search task/command/prompt" value="{safe_html(search or '')}">
          <select name="status">
            <option value="">status</option>
            <option value="queued"   {opt('queued', status)}>queued</option>
            <option value="running"  {opt('running', status)}>running</option>
            <option value="completed"{opt('completed', status)}>completed</option>
            <option value="failed"   {opt('failed', status)}>failed</option>
          </select>
          <select name="agent_mode">
            <option value="">agent mode</option>
            <option value="Interactive" {opt('Interactive', agent_mode)}>Interactive</option>
            <option value="Agentic"     {opt('Agentic', agent_mode)}>Agentic</option>
            <option value="ReAct"       {opt('ReAct', agent_mode)}>ReAct</option>
          </select>
          <select name="confirmed">
            <option value="">confirmed?</option>
            <option value="true"  {opt('true', confirmed)}>true</option>
            <option value="false" {opt('false', confirmed)}>false</option>
          </select>
          <input type="text" name="permissions" placeholder="permissions" value="{safe_html(permissions or '')}">
          <input type="number" min="1" max="500" name="page_size" value="{page_size}">
          <input type="number" min="1" name="page" value="{page}">
          <input type="number" min="0" name="refresh" placeholder="autorefresh (s)" value="{safe_html(str(refresh) if refresh else '')}">
          <button class="btn" type="submit">Apply</button>
          <a class="btn secondary" href="{url_for('view_command_log')}">Reset</a>
          <a class="btn" href="{url_for('command_log_csv')}?{request.query_string.decode('utf-8')}">Download CSV</a>
        </form>
        <div class="meta">Total: {total} · Page {page}</div>
        """

        header = ["id","time","command","permissions","confirmed","agent","status","duration","rc","stdout/err","task"]
        body_html = []
        for r in rows:
            (cid, task_id, at, command, perm, confirmed_b, agent, status, start_ts, end_ts, dur,
             success, rc, stdout, stderr, prompt) = r

            at_local = convert_to_local_time(at)
            dur_txt = f"{dur}s" if dur is not None else "—"
            cmd_disp = safe_html(command)
            task_disp = safe_html(task_id or "—")
            s_out = safe_html((stdout or "")[:200])
            s_err = safe_html((stderr or "")[:200])
            rowid = f"rowx-{cid}"
            cmd_json = json.dumps(command or "")
            prompt_html = safe_html(prompt or "")

            body_html.append(
                "<tr class='row-expand' onclick=\"toggleRow('%s')\">" % rowid +
                f"<td><a href='{url_for('command_detail', cmd_id=cid)}' onclick='event.stopPropagation();'>{cid}</a></td>" +
                f"<td class='small'>{at_local or '—'}</td>" +
                f"<td><code>{cmd_disp}</code> <span class='copy' onclick='event.stopPropagation();copyText({cmd_json})'>copy</span></td>" +
                f"<td class='small'>{safe_html(perm) if perm else '—'}</td>" +
                f"<td class='small'>{bool_badge(confirmed_b)}</td>" +
                f"<td class='small'>{safe_html(agent or '—')}</td>" +
                f"<td class='small'>{status_badge(status)}</td>" +
                f"<td class='small'>{dur_txt}</td>" +
                f"<td class='small'>{rc if rc is not None else '—'}</td>" +
                f"<td class='small'>{('<pre>'+s_out+'</pre>' if s_out else '')}{('<pre>'+s_err+'</pre>' if s_err else '')}</td>" +
                f"<td class='small'>{task_disp}</td>" +
                "</tr>" +
                f"<tr id='{rowid}' style='display:none;'><td colspan='11'>" +
                f"<div class='meta'><strong>Prompt:</strong> {prompt_html}</div>" +
                f"<h4>STDOUT</h4>{safe_pre(stdout)}" +
                f"<h4>STDERR</h4>{safe_pre(stderr)}" +
                "</td></tr>"
            )

        table_html = "<table><thead><tr>" + "".join(f"<th>{h}</th>" for h in header) + "</tr></thead><tbody>" + "".join(body_html) + "</tbody></table>" if body_html else ""

    except Exception as e:
        logger.exception("Command log error")
        error = f"Database query failed: {e}"

    return render_page("Command Log", "cmdlog", table_html=table_html, toolbar_html=toolbar_html, refresh=refresh)

# ---------------
# CSV Export
# ---------------
@app.route('/command_log.csv')
def command_log_csv():
    status = request.args.get('status')
    agent_mode = request.args.get('agent_mode')
    confirmed = request.args.get('confirmed')
    permissions = request.args.get('permissions')
    search = request.args.get('search')

    where, params = [], []
    if status:
        where.append("cl.status = %s"); params.append(status)
    if agent_mode:
        where.append("cl.agent_mode = %s"); params.append(agent_mode)
    if confirmed in ('true', 'false'):
        where.append("cl.user_confirmation = %s"); params.append(confirmed == 'true')
    if permissions:
        where.append("cl.permissions = %s"); params.append(permissions)
    if search:
        where.append("(cl.task_id ILIKE %s OR cl.command ILIKE %s OR cl.prompt ILIKE %s)")
        like = f"%{search}%"; params.extend([like, like, like])
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    order_sql = "ORDER BY COALESCE(cl.executed_at, cl.command_start_timestamp) DESC NULLS LAST, cl.id DESC"

    try:
        with get_conn() as conn:
            co_key = ensure_co_join_key(conn)
            co_fields, co_join = co_select_fragments(co_key)
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = '{STMT_TIMEOUT}'")
                cur.execute(f"""
                    SELECT
                        cl.id, cl.task_id, COALESCE(cl.executed_at, cl.command_start_timestamp) AS at,
                        cl.command, cl.permissions, cl.user_confirmation, cl.agent_mode, cl.status,
                        cl.command_start_timestamp, cl.command_end_timestamp,
                        (EXTRACT(EPOCH FROM (cl.command_end_timestamp - cl.command_start_timestamp)))::INT AS duration_sec,
                        {co_fields}, cl.prompt
                    FROM command_log cl
                    {co_join}
                    {where_sql}
                    {order_sql}
                    LIMIT 5000
                """, params)
                headers = [d[0] for d in cur.description]
                buf = StringIO(); w = csv.writer(buf); w.writerow(headers)
                for row in cur.fetchall():
                    r = list(row)
                    r[2] = convert_to_local_time(r[2])
                    r[8] = convert_to_local_time(r[8])
                    r[9] = convert_to_local_time(r[9])
                    w.writerow(r)
        return Response(buf.getvalue(), mimetype='text/csv',
                        headers={"Content-Disposition": "attachment; filename=command_log.csv"})
    except Exception as e:
        logger.exception("CSV export error")
        return Response(f"error: {e}", status=500, mimetype='text/plain')

# ----------------
# Command detail
# ----------------
@app.route('/command/<int:cmd_id>')
def command_detail(cmd_id):
    refresh = request.args.get('refresh', type=int)
    error = None; table_html = ""
    try:
        with get_conn() as conn:
            co_key = ensure_co_join_key(conn)
            co_fields, co_join = co_select_fragments(co_key)
            with conn.cursor() as cur:
                cur.execute(f"SET LOCAL statement_timeout = '{STMT_TIMEOUT}'")
                cur.execute(f"""
                    SELECT
                        cl.id, cl.task_id, cl.prompt, cl.command, cl.permissions, cl.user_confirmation,
                        cl.agent_mode, cl.status, cl.executed_at, cl.command_start_timestamp,
                        cl.command_end_timestamp, (EXTRACT(EPOCH FROM (cl.command_end_timestamp - cl.command_start_timestamp)))::INT AS duration_sec,
                        cl.thought, cl.observation, cl.parent_command_id,
                        {co_fields}
                    FROM command_log cl
                    {co_join}
                    WHERE cl.id = %s
                """, (cmd_id,))
                row = cur.fetchone()
                if not row:
                    return render_page(f"Command {cmd_id}", "cmdlog", error="Not found", refresh=refresh)

        (rid, task_id, prompt, command, permissions, confirmed, agent_mode, status,
         executed_at, start_ts, end_ts, duration_sec, thought, observation, parent_id,
         success, return_code, stdout, stderr) = row

        meta_rows = [
            ("id", rid), ("task_id", task_id), ("permissions", permissions),
            ("confirmed", bool_badge(confirmed)), ("agent_mode", agent_mode or "—"),
            ("status", status_badge(status)), ("return_code", return_code if return_code is not None else "—"),
            ("success", bool_badge(success) if success is not None else "—"),
            ("executed_at", convert_to_local_time(executed_at) if executed_at else "—"),
            ("start", convert_to_local_time(start_ts) if start_ts else "—"),
            ("end", convert_to_local_time(end_ts) if end_ts else "—"),
            ("duration_sec", duration_sec if duration_sec is not None else "—"),
            ("parent_command_id", parent_id if parent_id is not None else "—"),
        ]
        def render_meta_value(value):
	    # pass through HTML only if it's explicitly Markup; otherwise escape
    	    return value if isinstance(value, Markup) else safe_html(value)

        kv = "<table class='kv'>" + "".join(
            f"<tr><td class='meta'>{safe_html(k)}</td><td>{render_meta_value(v)}</td></tr>"
            for k, v in meta_rows
        ) + "</table>"


        html_block = f"""
        <div class="card">{kv}</div>
        <div class="card">
          <h3>Prompt <span class="copy" onclick="copyText({json.dumps(prompt or '')})">copy</span></h3>
          {safe_pre(prompt or '')}
          <h3>Command <span class="copy" onclick="copyText({json.dumps(command or '')})">copy</span></h3>
          {safe_pre(command or '')}
          <h3>Thought</h3>
          {safe_pre(thought or '—')}
          <h3>Observation</h3>
          {safe_pre(observation or '—')}
          <h3>STDOUT <span class="copy" onclick="copyText({json.dumps(stdout or '')})">copy</span></h3>
          {safe_pre(stdout or '')}
          <h3>STDERR <span class="copy" onclick="copyText({json.dumps(stderr or '')})">copy</span></h3>
          {safe_pre(stderr or '')}
        </div>
        """
        table_html = html_block

    except Exception as e:
        logger.exception("Command detail error")
        error = f"DB error: {e}"

    return render_page(f"Command {cmd_id}", "cmdlog", table_html=table_html, error=error, refresh=refresh)

# -----------
# Logs view
# -----------
@app.route('/gemma_logs', defaults={'filename': None})
@app.route('/gemma_logs/<path:filename>')
def view_gemma_logs(filename):
    if filename:
        if not os.path.isdir(LOGS_DIR):
            return "Log directory not found.", 404
        return send_from_directory(LOGS_DIR, filename)
    files = []
    if os.path.isdir(LOGS_DIR):
        files = [f for f in os.listdir(LOGS_DIR) if os.path.isfile(os.path.join(LOGS_DIR, f))]
        files.sort(reverse=True)
    items = "".join(f'<li><a href="{url_for("view_gemma_logs", filename=f)}">{safe_html(f)}</a></li>' for f in files) or "<li>No log files found.</li>"
    table_html = f"<div class='card'><ul>{items}</ul></div>"
    return render_page("Gemma Logs", "logs", table_html=table_html)

# -------------
# Health checks
# -------------
@app.route('/healthz')
def healthz():
    return Response("ok", 200)

@app.route('/health')
def health_detailed():
    status = {"status": "healthy", "timestamp": datetime.utcnow().isoformat() + "Z", "checks": {}}
    # DB
    try:
        with get_cursor() as (_, cur):
            cur.execute("SELECT 1")
            status["checks"]["database"] = "ok"
    except Exception as e:
        status["checks"]["database"] = f"error: {str(e)}"
        status["status"] = "unhealthy"
    # Logs dir
    status["checks"]["logs_directory"] = "ok" if os.path.isdir(LOGS_DIR) else "missing"
    code = 200 if status["status"] == "healthy" else 503
    return Response(json.dumps(status), status=code, mimetype='application/json')

# -----------
# Entrypoint
# -----------
if __name__ == '__main__':
    port = int(os.getenv('WEB_UI_PORT', '5002'))
    debug = os.getenv('WEB_UI_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=False)
