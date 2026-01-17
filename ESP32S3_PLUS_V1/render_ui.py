# render_ui.py — Alles was "zeichnet" (Layout/Full-Render)
from helper import split_string, normalize_text
from display_driver import print_text

def draw_hline(pix, x0, x1, y, color=0):
    for x in range(x0, x1 + 1):
        pix(x, y, color)

def render_card(epd, pix, line_no, countdown, direction, planned, real, delay, y_offset):
    print_text(epd.fb, pix, line_no, 0, 5 + y_offset, size=3, bold=True)

    direction = normalize_text(direction)
    s1, s2 = split_string(direction, 23)
    print_text(epd.fb, pix, s1, 100, 5 + y_offset, size=1, bold=False)
    if s2:
        print_text(epd.fb, pix, s2, 100, 20 + y_offset, size=1, bold=False)

    print_text(epd.fb, pix, real, 0, 35 + y_offset, size=2, bold=False)
    print_text(epd.fb, pix, "-> {} min".format(countdown), 100, 35 + y_offset, size=2, bold=False)

def render_none_card(epd, pix, line_no, msg, y_offset):
    print_text(epd.fb, pix, line_no, 0, 5 + y_offset, size=3, bold=True)
    print_text(epd.fb, pix, msg, 100, 12 + y_offset, size=1, bold=True)

def render_error_fullscreen(epd, pix, msg="Fehler"):
    epd.fb.fill(1)
    print_text(epd.fb, pix, msg, 10, 10, size=2, bold=True)
    epd.display_full_and_sync()

def render_loading_screen(epd, pix, line_no_1, line_no_2):
    epd.fb.fill(1)
    draw_hline(pix, 0, 295, 65, color=0)
    render_none_card(epd, pix, line_no_1, "Lade...", y_offset=5)
    render_none_card(epd, pix, line_no_2, "Lade...", y_offset=70)
    epd.display_full_and_sync()

def redraw_full(epd, pix, line_no_1, line_no_2, r1, r2):
    epd.fb.fill(1)
    draw_hline(pix, 0, 295, 65, color=0)

    if r1 is None:
        render_none_card(epd, pix, line_no_1, "Keine Abfahrt", y_offset=5)
    else:
        cd, direction, planned, real, delay = r1
        render_card(epd, pix, line_no_1, cd, direction, planned, real, delay, y_offset=5)

    if r2 is None:
        render_none_card(epd, pix, line_no_2, "Keine Abfahrt", y_offset=70)
    else:
        cd, direction, planned, real, delay = r2
        render_card(epd, pix, line_no_2, cd, direction, planned, real, delay, y_offset=70)

    epd.display_full_and_sync()
