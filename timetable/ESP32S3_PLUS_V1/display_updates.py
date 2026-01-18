# display_updates.py — Partial-Updates (Layout aus layout.py)
from helper import split_string, normalize_text
from display_driver import print_text
import layout as L

def _landscape_clear_rect(pix, x, y, w, h, color=1):
    x1 = x + w
    y1 = y + h
    for yy in range(y, y1):
        for xx in range(x, x1):
            pix(xx, yy, color)

def _text_w_px(text, size):
    return len(text) * 8 * size

def _cd_rect_w():
    w = _text_w_px(L.CD_WORST, L.BOTTOM_SIZE) + L.CD_RECT_PAD
    if L.CD_X + w > L.W_LAND:
        w = L.W_LAND - L.CD_X
    return w

def update_slot_partial(epd, pix, line_no, countdown, direction, real, y_offset):
    """
    Partial-Update Slot, Layout 1:1 wie render_ui.render_card()
    """

    # --- LINE ---
    y_line = L.LINE_Y + y_offset
    rect_y = y_line - L.LINE_RECT_Y_PAD_TOP
    _landscape_clear_rect(pix, L.LINE_RECT_X, rect_y, L.LINE_RECT_W, L.LINE_RECT_H, 1)
    print_text(epd.fb, pix, str(line_no), L.LINE_X, y_line, size=L.LINE_SIZE, bold=L.LINE_BOLD)
    epd.display_partial_landscape(L.LINE_RECT_X, rect_y, L.LINE_RECT_W, L.LINE_RECT_H)

    # --- DIRECTION ---
    direction = normalize_text(direction if direction is not None else "—")
    s1, s2 = split_string(direction, L.DIR_SPLIT_CHARS)

    rect_y_dir = (L.DIR_Y1 + y_offset) - L.DIR_RECT_Y_PAD_TOP
    _landscape_clear_rect(pix, L.DIR_RECT_X, rect_y_dir, L.DIR_RECT_W, L.DIR_RECT_H, 1)
    print_text(epd.fb, pix, s1, L.DIR_X, L.DIR_Y1 + y_offset, size=L.DIR_SIZE, bold=L.DIR_BOLD)
    if s2:
        print_text(epd.fb, pix, s2, L.DIR_X, L.DIR_Y2 + y_offset, size=L.DIR_SIZE, bold=L.DIR_BOLD)
    epd.display_partial_landscape(L.DIR_RECT_X, rect_y_dir, L.DIR_RECT_W, L.DIR_RECT_H)

    # --- REAL ---
    y_bottom = L.BOTTOM_Y + y_offset
    rect_y_b = y_bottom - L.REAL_RECT_Y_PAD_TOP
    _landscape_clear_rect(pix, L.REAL_RECT_X, rect_y_b, L.REAL_RECT_W, L.REAL_RECT_H, 1)
    print_text(epd.fb, pix, str(real if real else "—"), L.REAL_X, y_bottom, size=L.BOTTOM_SIZE, bold=L.BOTTOM_BOLD)
    epd.display_partial_landscape(L.REAL_RECT_X, rect_y_b, L.REAL_RECT_W, L.REAL_RECT_H)

    # --- COUNTDOWN ---
    cd_w = _cd_rect_w()
    _landscape_clear_rect(pix, L.CD_X, rect_y_b, cd_w, L.CD_RECT_H, 1)
    cd_text = "-> {} min".format(countdown) if countdown is not None else "—"
    print_text(epd.fb, pix, cd_text, L.CD_X, y_bottom, size=L.BOTTOM_SIZE, bold=L.BOTTOM_BOLD)
    epd.display_partial_landscape(L.CD_X, rect_y_b, cd_w, L.CD_RECT_H)
