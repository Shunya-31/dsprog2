import flet as ft
import requests

AREA_URL = "https://www.jma.go.jp/bosai/common/const/area.json"
FORECAST_URL = "https://www.jma.go.jp/bosai/forecast/data/forecast/{code}.json"


def icons_from_weather(weather: str) -> list[str]:
    icons = []
    if "晴" in weather: icons.append("☀️")
    if "曇" in weather: icons.append("☁️")
    if "雨" in weather: icons.append("🌧️")
    if "雪" in weather: icons.append("❄️")
    if "雷" in weather: icons.append("⛈️")
    return icons if icons else ["🌤️"]


def is_prefecture_like(name: str) -> bool:
    return ("都" in name) or ("道" in name) or ("府" in name) or ("県" in name)


def main(page: ft.Page):
    page.title = "天気予報アプリ"
    page.padding = 0
    page.bgcolor = "#BFE9FF"

    area = requests.get(AREA_URL).json()
    centers = area.get("centers", {})
    offices = area.get("offices", {})

    bar_title = ft.Text("地方を選択", color="white", weight=ft.FontWeight.BOLD)

    center_bar = ft.Row()

    top_bar = ft.Container(
        bgcolor="#3F474D",
        padding=12,
        content=ft.Column(
            [
                bar_title,
                ft.Container(height=6),
                center_bar
            ],
            spacing=0,
        ),
    )

    prefecture_list = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)

    left_panel = ft.Container(
        width=360,
        padding=12,
        bgcolor="#D9F3FF",
        content=ft.Column(
            [
                ft.Text("都道府県", weight=ft.FontWeight.BOLD),
                ft.Divider(),
                prefecture_list,
            ],
            expand=True,
        ),
    )

    big_icons = ft.Row(spacing=8)
    title_text = ft.Text("上の地方バーから選んでね", size=22, weight=ft.FontWeight.BOLD)
    sub_text = ft.Text("", size=14)

    cards = ft.Column(spacing=12)

    right_panel = ft.Container(
        expand=True,
        padding=20,
        content=ft.Column(
            [
                ft.Container(
                    padding=16,
                    border_radius=14,
                    bgcolor="white",
                    content=ft.Row(
                        [big_icons, ft.Container(width=12), ft.Column([title_text, sub_text], spacing=4)],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ),
                ft.Container(height=10),
                cards,
            ],
            expand=True,
        ),
    )

    def show_forecast(code: str, name: str):
        try:
            data = requests.get(FORECAST_URL.format(code=code)).json()
            weathers = data[0]["timeSeries"][0]["areas"][0]["weathers"]
        except Exception:
            big_icons.controls = [ft.Text("❓", size=44)]
            title_text.value = f"{name}（{code}）"
            sub_text.value = "取得失敗（ネットワーク/データ形式）"
            cards.controls = []
            page.update()
            return

        today = weathers[0] if weathers else "情報なし"
        big_icons.controls = [ft.Text(ic, size=44) for ic in icons_from_weather(today)]

        title_text.value = f"{name}（{code}）"
        sub_text.value = today

        labels = ["今日", "明日", "明後日"]
        cards.controls = []

        for i in range(min(3, len(weathers))):
            w = weathers[i]
            row_icons = ft.Row([ft.Text(ic, size=26) for ic in icons_from_weather(w)], spacing=6)

            cards.controls.append(
                ft.Container(
                    padding=14,
                    border_radius=14,
                    bgcolor="white",
                    content=ft.Row(
                        [
                            ft.Text(labels[i], width=60, weight=ft.FontWeight.BOLD),
                            row_icons,
                            ft.Container(width=10),
                            ft.Text(w, expand=True),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                )
            )

        page.update()

    def build_prefecture_list(center_code: str):
        prefecture_list.controls = []

        center_info = centers.get(center_code, {})
        children = center_info.get("children", [])

        items = []
        for code in children:
            if code not in offices:
                continue
            name = offices[code].get("name", code)
            if not is_prefecture_like(name):
                continue
            items.append((name, code))

        items.sort(key=lambda x: x[0])
        items = items[:30]

        for name, code in items:
            prefecture_list.controls.append(
                ft.ListTile(
                    title=ft.Text(name),
                    subtitle=ft.Text(code),
                    on_click=lambda e, c=code, n=name: show_forecast(c, n),
                )
            )

        if not items:
            prefecture_list.controls.append(ft.Text("表示できる都道府県がありません"))

        page.update()

        if items:
            show_forecast(items[0][1], items[0][0])

    center_items = sorted(centers.items(), key=lambda x: x[1].get("name", x[0]))

    def select_center(center_code: str):
        build_prefecture_list(center_code)

    for ccode, info in center_items:
        cname = info.get("name", ccode)

        center_bar.controls.append(
            ft.ElevatedButton(
                text=cname,
                on_click=lambda e, c=ccode: select_center(c),
            )
        )

    page.add(
        ft.Column(
            [
                top_bar,
                ft.Row([left_panel, right_panel], expand=True),
            ],
            expand=True,
        )
    )

    if center_items:
        select_center(center_items[0][0])


ft.app(main)
