#!/usr/bin/env python3
"""Turn the MeltWise slide files into print-ready HTML for headless Chrome.

Reads deck.json and slides/<id>.html and writes build/:
  deck_print.html   every slide as one 1920x1080 page (for the PDF)
  slide_NN.html     one slide per file (for PNG screenshots)
  contact.html      thumbnail grid of the PNGs (for a quick visual check)
  notes.json        speaker notes per slide, in deck order
"""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE
BUILD = HERE / "build"

FONTS = ("https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400..700"
         "&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap")

# Line icons (24x24, stroked) standing in for the slide format's <x-icon> names.
ICONS = {
    "Activity": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
    "Search": '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    "Chat": '<path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"/>',
    "Chart": '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    "Lightning": '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    "Clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "Globe": '<circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/>',
    "Users": '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>'
             '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    "Wrench": '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94'
              'l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>',
    "Verified": '<path d="M3.85 8.62a4 4 0 0 1 4.78-4.77 4 4 0 0 1 6.74 0 4 4 0 0 1 4.78 4.78 4 4 0 0 1 0 6.74'
                ' 4 4 0 0 1-4.77 4.78 4 4 0 0 1-6.75 0 4 4 0 0 1-4.78-4.77 4 4 0 0 1 0-6.76Z"/><path d="m9 12 2 2 4-4"/>',
    "Link": '<path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/>'
            '<path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/>',
    "Key": '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>',
    "Warning": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>'
               '<path d="M12 9v4"/><path d="M12 17h.01"/>',
    "Star": '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
}

# Defaults the slide runtime applies that plain HTML does not.
BASE_CSS = """
@page { size: 1920px 1080px; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { background: #16181D; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
section { position: relative; width: 1920px; height: 1080px; overflow: hidden; break-after: page; }
section:last-of-type { break-after: auto; }
section > * { position: relative; }  /* flow content paints above a pinned backdrop listed before it */
h1 { font-weight: 600; line-height: 1.1; }
h2 { font-weight: 600; line-height: 1.15; }
h3 { font-weight: 600; line-height: 1.2; }
p, li { line-height: 1.4; }
ul { padding-left: 1.1em; }
table { border-collapse: collapse; }
th, td { padding: 0.35em 0.6em; border-bottom: 1px solid rgba(128, 128, 128, 0.35); vertical-align: middle; }
th { font-weight: 600; }
aside { display: none; }
"""


def style_value(style, prop):
    match = re.search(rf"(?:^|;)\s*{prop}\s*:\s*([^;]+)", style)
    return match.group(1).strip() if match else None


def px(value, default):
    match = re.match(r"(\d+(?:\.\d+)?)px", value or "")
    return float(match.group(1)) if match else default


def render_icon(match):
    name, style = match.group(1), match.group(2)
    width = px(style_value(style, "width"), 24)
    height = px(style_value(style, "height"), 24)
    color = style_value(style, "color") or "currentColor"
    return (f'<svg viewBox="0 0 24 24" width="{width:g}" height="{height:g}" fill="none" stroke="{color}" '
            f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex:none">{ICONS[name]}</svg>')


def render_shape(match):
    kind, style = match.group(1), match.group(2)
    if kind != "arrow-right":
        raise ValueError(f"unsupported shape: {kind}")
    w = px(style_value(style, "width"), 40)
    h = px(style_value(style, "height"), 24)
    fill = style_value(style, "background") or "#000000"
    points = (f"0,{h * 0.3:g} {w * 0.6:g},{h * 0.3:g} {w * 0.6:g},0 {w:g},{h / 2:g} "
              f"{w * 0.6:g},{h:g} {w * 0.6:g},{h * 0.7:g} 0,{h * 0.7:g}")
    return (f'<svg width="{w:g}" height="{h:g}" viewBox="0 0 {w:g} {h:g}" style="flex:none; align-self:center">'
            f'<polygon points="{points}" fill="{fill}"/></svg>')


def align_table_columns(html):
    """The slide format aligns a whole column from its header cell; plain HTML only aligns that cell."""
    def fix_table(table_match):
        table = table_match.group(0)
        rows = re.findall(r"<tr\b.*?</tr>", table, flags=re.S)
        if not rows:
            return table
        aligns = [style_value(s, "text-align") for s in re.findall(r'<th\b[^>]*style="([^"]*)"', rows[0])]

        def fix_row(row):
            index = -1

            def fix_cell(cell_match):
                nonlocal index
                index += 1
                align = aligns[index] if index < len(aligns) else None
                attrs = cell_match.group(1)
                if not align:
                    return cell_match.group(0)
                if 'style="' in attrs:
                    return "<td" + attrs.replace('style="', f'style="text-align:{align}; ', 1) + ">"
                return f'<td{attrs} style="text-align:{align}">'

            return re.sub(r"<td\b([^>]*)>", fix_cell, row)

        for row in rows[1:]:
            table = table.replace(row, fix_row(row), 1)
        return table

    return re.sub(r"<table\b.*?</table>", fix_table, html, flags=re.S)


def convert(section):
    notes_match = re.search(r"<aside>(.*?)</aside>", section, flags=re.S)
    notes = notes_match.group(1).strip() if notes_match else ""
    html = re.sub(r'<x-icon name="(\w+)" style="([^"]*)"></x-icon>', render_icon, section)
    html = re.sub(r'<x-shape kind="([\w-]+)" style="([^"]*)"></x-shape>', render_shape, html)
    html = align_table_columns(html)
    if "<x-" in html:
        raise ValueError("a custom element was left unconverted")
    return html, notes


def page(title, body):
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>'
            f'<link rel="stylesheet" href="{FONTS}"><style>{BASE_CSS}</style></head><body>{body}</body></html>')


def main():
    deck = json.loads((PROJECT / "deck.json").read_text())
    BUILD.mkdir(exist_ok=True)
    sections, notes = [], []
    for number, slide_id in enumerate(deck["order"], start=1):
        html, note = convert((PROJECT / "slides" / f"{slide_id}.html").read_text())
        sections.append(html)
        notes.append({"id": slide_id, "notes": note})
        (BUILD / f"slide_{number:02d}.html").write_text(page(f"Slide {number}", html))
    (BUILD / "deck_print.html").write_text(page("MeltWise - Yuva Yodha 2026", "\n".join(sections)))
    (BUILD / "notes.json").write_text(json.dumps(notes, indent=2, ensure_ascii=False) + "\n")
    thumbs = "".join(f'<img src="slide_{n:02d}.png" style="width:464px; height:261px; border:1px solid #555">'
                     for n in range(1, len(sections) + 1))
    (BUILD / "contact.html").write_text(
        '<!doctype html><html><body style="margin:0; background:#333; display:flex; flex-wrap:wrap; '
        f'gap:8px; padding:8px; width:1920px">{thumbs}</body></html>')
    print(f"Built {len(sections)} slides into {BUILD}")


if __name__ == "__main__":
    main()
