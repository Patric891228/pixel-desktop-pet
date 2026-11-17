"""剪刀造型：把剪刀用「記號色」重畫一次拿武器的動作，給 make_accessories 找出刀的像素、換色、換造型。

用法：python3 art/weapon_mask.py <造型> <輸出資料夾>
造型：classic（原本的剪刀大刃）、garden（園藝剪刀）、kids（兒童剪刀）、none（不畫剪刀，只有人）
輸出 swing.png、draw_weapon.png……：剪刀的每個部位是一種記號色（見 PARTS），其他跟原本的動作圖一樣。
"""
import math, os, runpy, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_girl_weapon as v4

# 部位 → 調色盤編號（20 以後是記號色）、記號 RGB
PARTS = {"red": 20, "red_dk": 21, "black": 22, "edge": 23, "pivot": 24,
         "grip": 25, "grip_dk": 26, "metal": 27, "metal_dk": 28}
MARK_RGB = {20: (255, 0, 0), 21: (0, 255, 0), 22: (0, 0, 255), 23: (255, 0, 255), 24: (0, 255, 255),
            25: (255, 255, 0), 26: (128, 0, 255), 27: (255, 128, 0), 28: (0, 128, 255)}
P = PARTS
while len(v4.PAL) < 29:
    v4.PAL.append((0, 0, 0))
for k, rgb in MARK_RGB.items():
    v4.PAL[k] = rgb

_px, _weapon = v4.px, v4.weapon


def classic(*a, **k):
    """原本的剪刀大刃，顏色換成記號色。"""
    m = {9: P["red"], 10: P["red_dk"], 11: P["black"], 8: P["edge"], 14: P["pivot"]}
    v4.px = lambda g, x, y, c: _px(g, x, y, m.get(c, c))
    try:
        _weapon(*a, **k)
    finally:
        v4.px = _px


def _axes(ang):
    c, s = math.cos(math.radians(ang)), -math.sin(math.radians(ang))
    return c, s, -s, c


def _pen(g, x0, y0):
    def P_(ax, t, w, col):
        c, s, nx, ny = ax
        _px(g, x0 + c * t + nx * w, y0 + s * t + ny * w, col)

    def T(ax, a, b, w, col):
        t = a
        while t <= b:
            P_(ax, t, w, col)
            t += 0.5
    return P_, T


def garden(g, x0, y0, ang, L=22, open_=0):
    """園藝剪刀（修枝剪）：刀短而厚、一片彎鉤，握把很長、包著橡膠套，中間有彈簧。"""
    P_, T = _pen(g, x0, y0)
    A = _axes(ang)
    U = _axes(ang + open_ / 2 + 4)       # 上刃（彎刀）
    D = _axes(ang - open_ / 2 - 4)       # 下刃（鉤）
    HU = _axes(ang + 180 - 8 - open_ / 3)    # 握把往後、微微張開
    HD = _axes(ang + 180 + 8 + open_ / 3)
    # 握把：從轉軸往手後面延伸，後半段包橡膠套
    for H, w in ((HU, 0), (HD, 0)):
        T(H, 0, 4, w, P["metal_dk"])
        T(H, 4, 11, w, P["grip"]); T(H, 4, 11, w + (1 if H is HU else -1), P["grip_dk"])
        T(H, 11, 11.5, w, P["grip_dk"])
    # 彈簧（兩根握把中間）
    for t in (2, 3):
        P_(A, -t, 0, P["pivot"])
    # 下刃：短、厚、往內彎的鉤
    T(D, 2, 9, 1, P["metal_dk"]); T(D, 2, 8, 2, P["metal_dk"]); T(D, 3, 6, 3, P["metal_dk"])
    P_(D, 10, 0, P["metal_dk"]); P_(D, 9.5, 0.5, P["metal_dk"])
    # 上刃：彎刀，刃口亮
    for t in range(2, 14):
        bend = -0.06 * (t - 2) ** 1.5 * 0.5
        P_(U, t, bend, P["metal"]); P_(U, t, bend - 1, P["metal"])
        if t < 11:
            P_(U, t, bend - 2, P["metal_dk"])
    T(U, 3, 12, 0.6, P["edge"])
    # 轉軸螺絲
    for dt, dw in ((0, 0), (1, 0), (0, 1), (0, -1), (-1, 0)):
        P_(A, 1.5 + dt, dw, P["pivot"])
    P_(A, 1.5, 0, P["red_dk"])


def kids(g, x0, y0, ang, L=22, open_=0):
    """兒童剪刀：大大的塑膠握環、短短的鈍頭刀（圓頭，不會戳到人）。"""
    P_, T = _pen(g, x0, y0)
    A = _axes(ang)
    R = _axes(ang + open_ / 2)
    B = _axes(ang - open_ / 2)
    # 兩個大握環（塑膠，實心邊、中間空）
    for ax, w0 in ((R, -2.2), (B, 2.2)):
        for i in range(48):
            a = 2 * math.pi * i / 48
            for r in (1.0, 0.8):
                P_(ax, -5 + 3.4 * r * math.cos(a), w0 + 2.3 * r * math.sin(a), P["grip"] if r == 1.0 else P["grip_dk"])
        T(ax, -1.5, 1, w0 * 0.4, P["grip"])
    # 刀：短、圓頭
    T(B, 2, 13, 1, P["metal_dk"]); T(B, 2, 12, 2, P["metal_dk"]); P_(B, 13.5, 1.5, P["metal_dk"])
    T(R, 2, 13, 0, P["metal"]); T(R, 2, 12, -1, P["metal"]); P_(R, 13.5, -0.5, P["metal"])
    T(R, 3, 12, 0, P["edge"])
    # 轉軸：跟握環同色的大圓釘
    for dt, dw in ((0, 0), (1, 0), (0, 1), (0, -1), (-1, 0)):
        P_(A, 1.5 + dt, dw, P["grip"])
    P_(A, 1.5, 0, P["pivot"])


def none(*a, **k):
    pass


SHAPES = {"classic": classic, "garden": garden, "kids": kids, "none": none}

if __name__ == "__main__":
    shape, out = sys.argv[1], sys.argv[2]
    v4.weapon = SHAPES[shape]
    os.makedirs(out, exist_ok=True)
    sys.argv = ["build_girl.py", HERE, out]
    runpy.run_path(os.path.join(HERE, "build_girl.py"), run_name="__main__")
    sys.argv = ["make_transitions.py", out]
    runpy.run_path(os.path.join(HERE, "make_transitions.py"), run_name="__main__")
