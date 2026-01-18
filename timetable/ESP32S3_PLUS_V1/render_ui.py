# render_ui.py — Full-Render (Layout aus layout.py)
from helper import split_string, normalize_text
from display_driver import print_text
import layout as L

def draw_hline(pix, x0, x1, y, color=0):
    for x in range(x0, x1 + 1):
        pix(x, y, color)

def render_card(epd, pix, line_no, countdown, direction, planned, real, delay, y_offset):
    # LINE
    print_text(epd.fb, pix, str(line_no), L.LINE_X, L.LINE_Y + y_offset, size=L.LINE_SIZE, bold=L.LINE_BOLD)

    # DIRECTION (1–2 Zeilen)
    direction = normalize_text(direction)
    s1, s2 = split_string(direction, L.DIR_SPLIT_CHARS)
    print_text(epd.fb, pix, s1, L.DIR_X, L.DIR_Y1 + y_offset, size=L.DIR_SIZE, bold=L.DIR_BOLD)
    if s2:
        print_text(epd.fb, pix, s2, L.DIR_X, L.DIR_Y2 + y_offset, size=L.DIR_SIZE, bold=L.DIR_BOLD)

    # REAL + COUNTDOWN
    print_text(epd.fb, pix, str(real), L.REAL_X, L.BOTTOM_Y + y_offset, size=L.BOTTOM_SIZE, bold=L.BOTTOM_BOLD)
    print_text(epd.fb, pix, "-> {} min".format(countdown), L.CD_X, L.BOTTOM_Y + y_offset, size=L.BOTTOM_SIZE, bold=L.BOTTOM_BOLD)

def render_none_card(epd, pix, line_no, msg, y_offset):
    print_text(epd.fb, pix, str(line_no), L.LINE_X, L.LINE_Y + y_offset, size=L.LINE_SIZE, bold=L.LINE_BOLD)
    # Nachricht im Richtungsbereich zentriert-ish
    print_text(epd.fb, pix, str(msg), L.DIR_X, 12 + y_offset, size=1, bold=True)

def render_error_fullscreen(epd, pix, msg="Fehler"):
    epd.fb.fill(1)
    print_text(epd.fb, pix, msg, 10, 10, size=2, bold=True)
    epd.display_full_and_sync()

def render_loading_screen(epd, pix, line_no_1, line_no_2):
    epd.fb.fill(1)
    draw_hline(pix, L.DIVIDER_X0, L.DIVIDER_X1, L.DIVIDER_Y, color=0)
    render_none_card(epd, pix, line_no_1, "Lade...", y_offset=L.SLOT1_Y)
    render_none_card(epd, pix, line_no_2, "Lade...", y_offset=L.SLOT2_Y)
    epd.display_full_and_sync()

def redraw_full(epd, pix, line_no_1, line_no_2, r1, r2):
    epd.fb.fill(1)
    draw_hline(pix, L.DIVIDER_X0, L.DIVIDER_X1, L.DIVIDER_Y, color=0)

    if r1 is None:
        render_none_card(epd, pix, line_no_1, "Keine Abfahrt", y_offset=L.SLOT1_Y)
    else:
        cd, direction, planned, real, delay = r1
        render_card(epd, pix, line_no_1, cd, direction, planned, real, delay, y_offset=L.SLOT1_Y)

    if r2 is None:
        render_none_card(epd, pix, line_no_2, "Keine Abfahrt", y_offset=L.SLOT2_Y)
    else:
        cd, direction, planned, real, delay = r2
        render_card(epd, pix, line_no_2, cd, direction, planned, real, delay, y_offset=L.SLOT2_Y)

    epd.display_full_and_sync()
