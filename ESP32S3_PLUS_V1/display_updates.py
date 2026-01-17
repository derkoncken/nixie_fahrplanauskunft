# display_updates.py — Partial-Updates + State-Handling

from display_driver import print_text

# Querformat Maße (pix): 296x128
W_LAND = 296

def _landscape_clear_rect(pix, x, y, w, h, color=1):
    x1 = x + w
    y1 = y + h
    for yy in range(y, y1):
        for xx in range(x, x1):
            pix(xx, yy, color)

def _text_w_px(text, size):
    return len(text) * 8 * size

def update_time_and_countdown_partial(epd, pix, y_offset, real, countdown):
    """
    Fix 1++:
    - kleines Fenster links (real)
    - fixes, sicheres Fenster rechts (countdown) inkl. Minus/3 Stellen
    """
    y_line = 35 + y_offset
    rect_y = y_line - 2
    rect_h = 22

    # links: real (fix)
    real = str(real)
    real_w = 96
    _landscape_clear_rect(pix, 0, rect_y, real_w, rect_h, color=1)
    print_text(epd.fb, pix, real, 0, y_line, size=2, bold=False)
    epd.display_partial_landscape(0, rect_y, real_w, rect_h)

    # rechts: countdown (Worst-case)
    worst = "-> -999 min"
    cd_text = "-> {} min".format(countdown)
    x2 = 100
    cd_w = _text_w_px(worst, 2) + 16
    if x2 + cd_w > W_LAND:
        cd_w = W_LAND - x2

    _landscape_clear_rect(pix, x2, rect_y, cd_w, rect_h, color=1)
    print_text(epd.fb, pix, cd_text, x2, y_line, size=2, bold=False)
    epd.display_partial_landscape(x2, rect_y, cd_w, rect_h)

def make_full_state(tag, result, normalize_text_fn):
    """
    Alles was ein Full-Redraw erzwingt (Layout/Content außer Zeit+Countdown).
    """
    if result is None:
        return tag + "|NONE"
    countdown, direction, planned, real, delay = result
    direction_norm = normalize_text_fn(direction)
    return "{}|DIR:{}|DLY:{}|PLN:{}".format(tag, direction_norm, delay, planned)

def make_time_state(tag, result):
    """
    Nur Zeit/Countdown (Partial).
    """
    if result is None:
        return tag + "|NONE"
    countdown, direction, planned, real, delay = result
    return "{}|REAL:{}|CD:{}".format(tag, real, countdown)
