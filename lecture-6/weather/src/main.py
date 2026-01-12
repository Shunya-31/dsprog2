import flet as ft
import requests
import sqlite3
from datetime import date, datetime

AREA_URL = "https://www.jma.go.jp/bosai/common/const/area.json"
FORECAST_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/{code}.json"
DB = "weather_min.db"


def icons(w: str) -> list[str]:
    out = []
    if "晴" in w: out.append("☀️")
    if "曇" in w: out.append("☁️")
    if "雨" in w: out.append("🌧️")
    if "雪" in w: out.append("❄️")
    if "雷" in w: out.append("⛈️")
    return out or ["🌤️"]


def is_pref(name: str) -> bool:
    return any(x in name for x in ("都", "道", "府", "県"))


def con():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def db_init():
    c = con(); cur = c.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS centers(code TEXT PRIMARY KEY, name TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS offices(code TEXT PRIMARY KEY, name TEXT, center_code TEXT)")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS snapshots(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      office_code TEXT,
      office_name TEXT,
      saved_date TEXT,
      saved_at TEXT,
      idx INTEGER,
      forecast_date TEXT,
      weather TEXT
    )""")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_snap ON snapshots(office_code, saved_date)")
    c.commit(); c.close()


def load_area():
    c = con(); cur = c.cursor()
    n = cur.execute("SELECT COUNT(*) n FROM centers").fetchone()["n"]
    if n > 0:
        centers = {}
        offices = {}
        for r in cur.execute("SELECT code,name FROM centers"):
            centers[r["code"]] = {"name": r["name"], "children": []}
        for r in cur.execute("SELECT code,name,center_code FROM offices"):
            offices[r["code"]] = {"name": r["name"]}
            if r["center_code"] in centers:
                centers[r["center_code"]]["children"].append(r["code"])
        c.close()
        return centers, offices

    c.close()
    area = requests.get(AREA_URL, timeout=10).json()
    centers = area.get("centers", {})
    offices = area.get("offices", {})

    c = con(); cur = c.cursor()
    for cc, info in centers.items():
        cur.execute("INSERT OR REPLACE INTO centers VALUES(?,?)", (cc, info.get("name", cc)))
    for cc, info in centers.items():
        for oc in info.get("children", []):
            if oc in offices:
                cur.execute(
                    "INSERT OR REPLACE INTO offices VALUES(?,?,?)",
                    (oc, offices[oc].get("name", oc), cc),
                )
    c.commit(); c.close()
    return load_area()


def fetch_forecast(office_code: str) -> tuple[list[str], list[str]]:
    data = requests.get(FORECAST_URL.format(code=office_code), timeout=10).json()
    ts = data[0]["timeSeries"][0]
    dates = [t[:10] for t in ts.get("timeDefines", [])]
    weathers = ts["areas"][0]["weathers"]
    return dates, weathers


def save_snapshot(office_code: str, office_name: str, dates: list[str], weathers: list[str]):
    sd = date.today().isoformat()
    sa = datetime.now().isoformat(timespec="seconds")
    c = con(); cur = c.cursor()
    for i in range(min(3, len(weathers), len(dates))):
        cur.execute(
            """INSERT INTO snapshots
            (office_code,office_name,saved_date,saved_at,idx,forecast_date,weather)
            VALUES(?,?,?,?,?,?,?)""",
            (office_code, office_name, sd, sa, i, dates[i], weathers[i]),
        )
    c.commit(); c.close()


def load_snapshot(office_code: str, saved_date: str):
    c = con(); cur = c.cursor()
    rows = cur.execute("""
      SELECT office_name,saved_at,forecast_date,idx,weather
      FROM snapshots
      WHERE office_code=? AND saved_date=?
      ORDER BY idx
    """, (office_code, saved_date)).fetchall()
    c.close()
    if not rows:
        return None
    name = rows[0]["office_name"]
    saved_at = rows[0]["saved_at"]
    dates = [r["forecast_date"] for r in rows]
    weathers = [r["weather"] for r in rows]
    return name, saved_at, dates, weathers


def saved_dates(office_code: str) -> list[str]:
    c = con(); cur = c.cursor()
    rows = cur.execute("""
      SELECT DISTINCT saved_date
      FROM snapshots
      WHERE office_code=?
      ORDER BY saved_date DESC
    """, (office_code,)).fetchall()
    c.close()
    return [r["saved_date"] for r in rows]


def main(page: ft.Page):
    db_init()
    centers, offices = load_area()

    page.title = "天気（DB版）"
    page.padding = 10

    center_bar = ft.Row(wrap=True, spacing=6)
    pref_list = ft.Column(width=320, scroll=ft.ScrollMode.AUTO)

    big = ft.Row()
    title = ft.Text("選んでね", size=20, weight=ft.FontWeight.BOLD)
    sub = ft.Text("")
    cards = ft.Column()

    cur_code = {"v": None}
    cur_name = {"v": None}

    def render(name: str, code: str, note: str, dates: list[str], weathers: list[str]):
        big.controls = [ft.Text(ic, size=40) for ic in icons(weathers[0] if weathers else "")]
        title.value = f"{name}（{code}）"
        sub.value = note

        cards.controls = []
        labels = ["今日", "明日", "明後日"]
        for i in range(min(3, len(weathers))):
            cards.controls.append(
                ft.Row([
                    ft.Text(labels[i], width=50),
                    ft.Text(dates[i] if i < len(dates) else "", width=110),
                    ft.Text("".join(icons(weathers[i])), width=50),
                    ft.Text(weathers[i], expand=True),
                ])
            )
        page.update()

    def refresh_dd():
        if not cur_code["v"]:
            dd.options = []
            dd.value = None
            page.update()
            return

        ds = saved_dates(cur_code["v"])
        dd.options = [ft.dropdown.Option(d) for d in ds]
        dd.value = ds[0] if ds else None
        page.update()

    def show_latest(code: str, name: str):
        cur_code["v"], cur_name["v"] = code, name
        try:
            dates, weathers = fetch_forecast(code)

            save_snapshot(code, name, dates, weathers)

            sd = date.today().isoformat()
            res = load_snapshot(code, sd)

            if res:
                n2, saved_at, d2, w2 = res
                render(n2, code, f"DB保存: {sd} / {saved_at}", d2, w2)
            else:
                render(name, code, "保存後のDB読込失敗", [], [])

        except Exception:
            render(name, code, "取得失敗", [], [])

        refresh_dd()

    def show_saved(saved_date: str):
        if not (cur_code["v"] and saved_date):
            return
        res = load_snapshot(cur_code["v"], saved_date)
        if not res:
            render(cur_name["v"] or "", cur_code["v"], f"{saved_date} の保存なし", [], [])
            return
        name, saved_at, dates, weathers = res
        render(name, cur_code["v"], f"DB保存: {saved_date} / {saved_at}", dates, weathers)

    dd = ft.Dropdown(label="保存日", width=220, on_change=lambda e: show_saved(dd.value))

    picker = ft.DatePicker(
        on_change=lambda e: show_saved(e.control.value.isoformat() if e.control.value else None)
    )
    page.overlay.append(picker)

    right = ft.Column([
        ft.Row([
            dd,
            ft.ElevatedButton("日付選択", on_click=lambda e: picker.pick_date()),
            ft.FilledButton("最新取得", on_click=lambda e: show_latest(cur_code["v"], cur_name["v"]) if cur_code["v"] else None),
        ], wrap=True),
        ft.Row([big, ft.Column([title, sub])]),
        ft.Divider(),
        cards,
    ], expand=True)

    def build_prefs(center_code: str):
        pref_list.controls = []
        children = centers.get(center_code, {}).get("children", [])

        items = []
        for oc in children:
            if oc in offices:
                nm = offices[oc].get("name", oc)
                if is_pref(nm):
                    items.append((nm, oc))

        items.sort()
        for nm, oc in items:
            pref_list.controls.append(
                ft.ListTile(
                    title=ft.Text(nm),
                    subtitle=ft.Text(oc),
                    on_click=lambda e, c=oc, n=nm: show_latest(c, n),
                )
            )

        page.update()
        if items:
            show_latest(items[0][1], items[0][0])

    for cc, info in sorted(centers.items(), key=lambda x: x[1].get("name", x[0])):
        center_bar.controls.append(
            ft.ElevatedButton(info.get("name", cc), on_click=lambda e, c=cc: build_prefs(c))
        )

    page.add(
        ft.Column(
            [
                center_bar,
                ft.Row([pref_list, ft.VerticalDivider(), right], expand=True),
            ],
            expand=True,
        )
    )

    first = next(iter(centers.keys()), None)
    if first:
        build_prefs(first)


ft.app(main)
