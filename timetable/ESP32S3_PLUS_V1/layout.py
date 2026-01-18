# layout.py — Single Source of Truth für UI-Layout (Querformat 296x128)

W_LAND = 296
H_LAND = 128

# Slot-Offsets (wie bisher)
SLOT1_Y = 5
SLOT2_Y = 70

# Trennlinie
DIVIDER_Y = 65
DIVIDER_X0 = 0
DIVIDER_X1 = 295

# --- LINE NO (links oben) ---
LINE_X = 0
LINE_Y = 5          # relativ zu slot y_offset
LINE_SIZE = 3
LINE_BOLD = True

# Partial-Fenster (clear+partial) für LINE
LINE_RECT_X = 0
LINE_RECT_Y_PAD_TOP = 2
LINE_RECT_W = 96
LINE_RECT_H = 30    # großzügig für size=3

# --- DIRECTION (rechts oben, 1–2 Zeilen) ---
DIR_X = 100
DIR_Y1 = 5          # relativ zu slot y_offset
DIR_Y2 = 20         # relativ zu slot y_offset
DIR_SIZE = 1
DIR_BOLD = False
DIR_SPLIT_CHARS = 23

# Partial-Fenster für DIR
DIR_RECT_X = DIR_X
DIR_RECT_Y_PAD_TOP = 2
DIR_RECT_W = W_LAND - DIR_X
DIR_RECT_H = 28     # deckt beide 1er-Zeilen ab

# --- BOTTOM: REAL + COUNTDOWN ---
BOTTOM_Y = 35        # relativ zu slot y_offset
BOTTOM_SIZE = 2
BOTTOM_BOLD = False

# REAL (links unten)
REAL_X = 0
REAL_RECT_X = 0
REAL_RECT_Y_PAD_TOP = 2
REAL_RECT_W = 96
REAL_RECT_H = 22

# COUNTDOWN (rechts unten)
CD_X = 100
CD_WORST = "-> -999 min"  # Worst-Case Text für Fensterbreite
CD_RECT_PAD = 16          # extra Padding für Sicherheit
CD_RECT_Y_PAD_TOP = 2
CD_RECT_H = 22
