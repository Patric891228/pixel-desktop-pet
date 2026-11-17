"""配件：貓耳、耳機、圍巾、手套、眼鏡、聖誕帽、色違制服……做成「疊圖」。

每個配件對每個動作輸出一張跟動作圖一樣大的透明 PNG（accessories/<配件 id>/<動作>.png），
引擎把它直接疊在動作圖上。配件畫在「頭部座標」上：用紅色蝴蝶結的位置找出每一格的頭在哪、
是正面還是側面（朝右），再把配件的正面／側面小圖貼上去，所以動作圖改了以後重跑就會跟著動。

用法（在角色資料夾）：python3 art/make_accessories.py assets accessories
"""
import json, os, subprocess, sys, tempfile
from PIL import Image

OUTLINE = (16, 12, 24)
RED = {(240, 52, 60), (140, 10, 30)}
SKIN = {(255, 240, 230), (246, 186, 190)}
BOW = ["##...##", "###.###", "#######", "###.###", "##...##"]


# ---------------------------------------------------------------- 找頭
def find_bow(im):
    w, h = im.size
    px = im.load()

    def col(x, y):
        if 0 <= x < w and 0 <= y < h and px[x, y][3]:
            return px[x, y][:3]

    best = (-1, 0, 0)
    for y in range(-2, h):
        for x in range(-2, w):
            s = 0
            for r in range(5):
                for c in range(7):
                    s += (col(x + c, y + r) in RED) == (BOW[r][c] == "#")
            if s > best[0]:
                best = (s, x, y)
    return best, col


def auto_anchor(im, view=None, need=27):
    """回傳 [view, hx, hy]：view 是 front／side（朝右），(hx, hy) 是頭的中心。找不到回傳 None。"""
    (s, bx, by), col = find_bow(im)
    if s < need:
        return None
    if view == "front" or (view is None and col(bx + 8, by + 13) in SKIN):
        return ["front", bx + 15, by + 9]
    return ["side", bx + 10, by + 10]


# 自動找不到或找錯的格子，手動指定（[view, hx, hy]，None 表示這格不畫配件）。
# hide：這格要被擋住的範圍 (x0, y0, x1, y1)，例如躲在電線杆後面。
POLE = (11, 0, 20, 30)
_POLE = [(0, 0, 1), (0, .35, 0), (0, .7, 0), (-2, 1, .4), (-7, 1, 1), (-7, 1, 1), (-1, 1, 1), (4, 1, 1),
         (4, 1, 1), (-7, 1, 1), (-4, .6, .3), (-2, .25, 0), (0, 0, 1)]   # make_girl_v6 的 shy_pole：(dx, rise, wire)
OVERRIDE = {
    "peek": {4: None},
    "shy_pole": {i: ["front", 16 + dx, 14] for i, (dx, r, w) in enumerate(_POLE)},
    "guard": {i: ["side_l", 17, 14] for i in (2, 3, 4)},          # 「哼」地轉頭：側面朝左
}
# 頭被畫布下緣切掉、蝴蝶結只露出一部分的動作：放寬比對，並固定是正面。
LOOSE = {"peek": "front"}


def _pole_boxes(rise, wire):
    """電線杆、橫擔、電線擋住的範圍（跟 make_girl_v6.pole_peek 一致）。"""
    if rise <= 0:
        return ()
    off = round((1 - rise) * 31)
    n = round(15 * wire)
    boxes = [(11, off, 20, 30), (4, off + 2, 27, off + 4)]
    if n:
        boxes += [(16 - n, off + 2, 15 + n, off + 2), (16 - n, off + 6, 15 + n, off + 6)]
    return boxes


HIDE = {"shy_pole": {i: _pole_boxes(r, w) for i, (dx, r, w) in enumerate(_POLE)}}


# ---------------------------------------------------------------- 畫圖工具
def parse(rows, pal):
    """字元圖 → [(dx, dy, rgb)]；'.' 是空白，'o' 是外框。"""
    out = []
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch == ".":
                continue
            out.append((x, y, OUTLINE if ch == "o" else pal[ch]))
    return out


def mirror(rows):
    return [r[::-1] for r in rows]


class Layer:
    anim = ""
    index = 0

    def __init__(self, base):
        self.base = base
        self.w, self.h = base.size
        self.img = Image.new("RGBA", base.size, (0, 0, 0, 0))
        self.erase = Image.new("RGBA", base.size, (0, 0, 0, 0))     # 要擦成透明的格子
        self.top = Image.new("RGBA", base.size, (0, 0, 0, 0))       # 其他配件畫完後再蓋一次的格子
        self.bp = base.load()
        self.p = self.img.load()

    def frame_of(self, sheets):
        """從另一組動作圖（同樣大小）取出這一格。"""
        return sheets[self.anim].crop((self.index * self.w, 0, (self.index + 1) * self.w, self.h))

    def put(self, x, y, rgb):
        if 0 <= x < self.w and 0 <= y < self.h:
            self.p[x, y] = rgb + (255,)

    def sprite(self, x0, y0, pix, under=()):
        """under：底圖是這些顏色的格子不畫（配件在它後面，例如貓耳在蝴蝶結後面）。"""
        for dx, dy, c in pix:
            x, y = x0 + dx, y0 + dy
            if under and 0 <= x < self.w and 0 <= y < self.h and self.bp[x, y][3] and self.bp[x, y][:3] in under:
                continue
            self.put(x, y, c)

    def solid(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h and (self.p[x, y][3] or self.bp[x, y][3])

    def auto_outline(self):
        """配件伸出角色外面的地方補一圈黑框（只描在原本透明的格子上）。"""
        add = []
        for y in range(self.h):
            for x in range(self.w):
                if self.p[x, y][3] or self.bp[x, y][3]:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < self.w and 0 <= ny < self.h and self.p[nx, ny][3] and self.p[nx, ny][:3] != OUTLINE:
                        add.append((x, y))
                        break
        for x, y in add:
            self.put(x, y, OUTLINE)

    def hide(self, box):
        x0, y0, x1, y1 = box
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            for x in range(max(0, x0), min(self.w, x1 + 1)):
                self.p[x, y] = (0, 0, 0, 0)


# ---------------------------------------------------------------- 找手
SOCK = (32, 34, 62)
HAIR_RED = {(46, 42, 72), (240, 52, 60), (140, 10, 30)}
BUBBLE = (150, 205, 255)
N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))


def find_hands(base, anim, anchor, knees=None):
    """手＝臉以外的小塊皮膚。排除膝蓋（腳的位置）、瀏海裡的零星膚色、泡泡裡透出來的臉。"""
    w, h = base.size
    p = base.load()

    def col(x, y):
        if 0 <= x < w and 0 <= y < h and p[x, y][3]:
            return p[x, y][:3]

    seen, out = set(), []
    for y in range(h):
        for x in range(w):
            if (x, y) in seen or col(x, y) not in SKIN:
                continue
            comp, st = [], [(x, y)]
            seen.add((x, y))
            while st:
                q = st.pop(); comp.append(q)
                for dx, dy in N4:
                    r = (q[0] + dx, q[1] + dy)
                    if r not in seen and col(*r) in SKIN:
                        seen.add(r); st.append(r)
            if len(comp) > 12:                      # 臉
                continue

            def touch(cols, dirs=N4):
                return any(col(x + dx, y + dy) in cols for x, y in comp for dx, dy in dirs)
            ys = [y for _, y in comp]
            if anim.startswith("bed"):
                knee = touch({SOCK}, ((1, 0), (-1, 0)))
            elif anim.startswith("desk"):
                knee = touch({SOCK}, ((0, 1),))
            elif anim == "peek" or not anchor:
                knee = False
            elif anchor[0] == "front":
                knee = all(abs(x - anchor[1]) <= 3 for x, _ in comp) and min(ys) >= h - 6
            else:
                knee = min(ys) >= h - 5
            stray = len(comp) <= 2 and sum(col(x + dx, y + dy) in HAIR_RED for x, y in comp for dx, dy in N4) >= 2
            if knee and knees is not None:
                knees += comp
            if knee or stray or touch({BUBBLE}):
                continue
            out += comp
    return out


def gloves(main, dark):
    def draw(L, view, hx, hy):
        for x, y in L.hands:
            L.put(x, y, dark if L.bp[x, y][:3] == (246, 186, 190) else main)
    draw.hands = True
    return draw


# ---------------------------------------------------------------- 圍巾
BOOK = {"read", "book_open", "book_close"}
SCARF_FRONT = [        # 原點 (hx-7, hy+9)
    "oSSSSSSSSSSSSo",
    "oMMMMMMMMMMMMo",
    "oMDMMDMMDMMDMo",
    ".ooooooMMMoooo",
    "......oMDMo...",
    "......oMMMo...",
    "......oDMDo...",
    "......oFoFo...",
]
SCARF_SIDE = [         # 原點 (hx-6, hy+9)，尾巴往後飄
    "...oSSSSSSSSo",
    "oooMMMMMMMMMo",
    "oMMMDMMDMMDMo",
    "oMDMoooooooo.",
    "oMMo.........",
    "oDMo.........",
    "oFoF.........",
]


def scarf(main, light, dark):
    pal = {"M": main, "S": light, "D": dark, "F": main}

    def draw(L, view, hx, hy):
        # 圍巾在書、禮物後面
        under = {(34, 92, 60), (222, 178, 64), (150, 92, 52)} | ({(255, 255, 255)} if L.anim in BOOK else set())
        if view == "front":
            L.sprite(hx - 7, hy + 9, parse(SCARF_FRONT, pal), under=under)
        else:
            L.sprite(hx - 6, hy + 9, parse(SCARF_SIDE, pal), under=under)
    return draw


# ---------------------------------------------------------------- 眼鏡
GLASS_FRONT = [        # 一邊鏡框，原點 (hx-8, hy+1) 和 (hx+1, hy+1)
    ".FFFFF.",
    "F.....F",
    "F.....F",
    "F.....F",
    "F.....F",
    "F.....F",
    ".FFFFF.",
]
GLASS_SIDE = [         # 原點 (hx+2, hy+1)
    "...FFF.",
    "..F...F",
    "FFF...F",
    "..F...F",
    "..F...F",
    "...FFF.",
]


def face_under(L):
    return {BUBBLE, (34, 92, 60), (222, 178, 64)} | ({(255, 255, 255)} if L.anim in BOOK else set())


def glasses(frame, glint=(255, 255, 255)):
    pal = {"F": frame}

    def draw(L, view, hx, hy):
        u = face_under(L)
        if view == "front":
            for x0 in (hx - 8, hx + 1):
                L.sprite(x0, hy + 1, parse(GLASS_FRONT, pal), under=u)
                L.put(x0 + 5, hy + 2, glint)
            L.put(hx - 1, hy + 3, frame); L.put(hx, hy + 3, frame)
        else:
            L.sprite(hx + 2, hy + 1, parse(GLASS_SIDE, pal), under=u)
            L.put(hx + 7, hy + 2, glint)
    return draw


# ---------------------------------------------------------------- 剪刀
# art/weapon_mask.py 用記號色把剪刀（各種造型）重畫一次，對照原本的動作圖就知道每一格要：
#   疊上去的格子（新的刀、刀移開後露出來的身體）、要擦掉的格子（原本的刀伸出去、新的刀沒有的地方）、
#   以及「刀本身」（最後再蓋一次，才不會被制服換色蓋掉）。
WEAPON_ANIMS = ("swing", "run_weapon", "walk_weapon", "draw_weapon", "sheath")
MARK = {(255, 0, 0): "red", (0, 255, 0): "red_dk", (0, 0, 255): "black", (255, 0, 255): "edge",
        (0, 255, 255): "pivot", (255, 255, 0): "grip", (128, 0, 255): "grip_dk", (255, 128, 0): "metal",
        (0, 128, 255): "metal_dk"}
ORIGINAL = {"red": (240, 52, 60), "red_dk": (140, 10, 30), "black": (38, 36, 44), "edge": (96, 94, 112),
            "pivot": (222, 178, 64)}
_RENDER = {}


def weapon_render(shape):
    """{動作: 用記號色畫的動作圖}；每種造型只算一次。"""
    if shape not in _RENDER:
        tmp = tempfile.mkdtemp()
        here = os.path.dirname(os.path.abspath(__file__))
        subprocess.run([sys.executable, os.path.join(here, "weapon_mask.py"), shape, tmp], check=True,
                       stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable, os.path.join(here, "..", "..", "..", "tools", "finish_assets.py"), tmp,
                        "--fix-top"], check=True, stdout=subprocess.DEVNULL)
        _RENDER[shape] = {n: Image.open(os.path.join(tmp, n + ".png")).convert("RGBA") for n in WEAPON_ANIMS}
    return _RENDER[shape]


def blade(shape="classic", **colors):
    """shape：classic／garden／kids；colors：各部位的顏色（沒給的用原本的顏色）。"""
    pal = dict(ORIGINAL, black=(38, 36, 44), grip=(240, 52, 60), grip_dk=(140, 10, 30),
               metal=(224, 228, 240), metal_dk=(150, 156, 178))
    pal.update(colors)

    def draw(L, view, hx, hy):
        if L.anim not in WEAPON_ANIMS:
            return
        r = L.frame_of(weapon_render(shape)).load()
        for y in range(L.h):
            for x in range(L.w):
                c, b = r[x, y], L.bp[x, y]
                if c[3] and c[:3] in MARK:
                    col = pal[MARK[c[:3]]]
                    L.top.putpixel((x, y), col + (255,))
                    if col != b[:3] or not b[3]:
                        L.put(x, y, col)
                elif c != b and not (c[3] == 0 and b[3] == 0):
                    if c[3]:
                        L.put(x, y, c[:3])
                    else:
                        L.erase.putpixel((x, y), (0, 0, 0, 255))
    draw.outline = False
    draw.raw = True
    return draw


# ---------------------------------------------------------------- 衣服換色
COAT, TRIM, SKIRT = (38, 36, 44), (96, 94, 112), (32, 34, 62)


def socks(L, knees):
    """膝蓋往腳的方向連著的深藍色是襪子，不跟著裙子換色。"""
    d = (1, 0) if L.anim.startswith("bed") else (0, 1)
    out = set()
    for x, y in knees:
        for k in range(1, 4):
            q = (x + d[0] * k, y + d[1] * k)
            if not (0 <= q[0] < L.w and 0 <= q[1] < L.h) or L.bp[q][:3] != SKIRT or not L.bp[q][3]:
                break
            out.add(q)
    return out


def outfit(coat, trim, skirt, sock=None):
    def draw(L, view, hx, hy):
        knees = []
        find_hands(L.base, L.anim, [view, hx, hy], knees)
        keep = socks(L, knees)
        # 拿剪刀的動作：照「沒拿剪刀」的版本換色（刀移開的地方也換到），刀最後由剪刀那層蓋回去
        body = L.frame_of(weapon_render("none")).load() if L.anim in WEAPON_ANIMS else L.bp
        for y in range(L.h):
            for x in range(L.w):
                c = body[x, y]
                if not c[3]:
                    continue
                c = c[:3]
                if y < hy + 9 and abs(x - hx) < 14:      # 頭
                    continue
                if c == COAT:
                    L.put(x, y, coat)
                elif c == SKIRT:
                    L.put(x, y, (sock or c) if (x, y) in keep else skirt)
                elif c == TRIM and any(body[x + dx, y + dy][:3] == COAT for dx, dy in N4
                                       if 0 <= x + dx < L.w and 0 <= y + dy < L.h):
                    L.put(x, y, trim)
    draw.outline = False
    return draw


def santa_hat(red=(214, 36, 48), dark=(150, 20, 36), fur=(255, 255, 255), fur_sh=(214, 214, 226)):
    pal = {"R": red, "D": dark, "W": fur, "w": fur_sh}
    FRONT = [              # 原點 (hx-12, hy-13)：帽子壓在頭頂，尖端往右垂、白毛球掛在右邊
        ".......oooooooooo.......",
        ".....ooRRRRRRRRRRooo....",
        "...ooRRRRRRRRRRRRRRRoo..",
        "..oRRRRRRRRRRRRRRRRDDRo.",
        ".oWWWWWWWWWWWWWWWWWWWoRo",
        ".oWwWWwWWWwWWWwWWWwWWoDo",
        "..ooooooooooooooooooooWWo",
        "....................oWWWWo",
        "....................oWwWWo",
        ".....................oooo.",
    ]
    SIDE = [               # 原點 (hx-11, hy-13)：尖端往後垂
        "......ooooooooo.....",
        "...oooRRRRRRRRRoo...",
        "..oRRRRRRRRRRRRRRo..",
        ".oRDRRRRRRRRRRRRRRo.",
        "oRoWWWWWWWWWWWWWWWWo",
        "oDoWwWWwWWWwWWWwWWWo",
        "oWWoooooooooooooooo.",
        "oWWWo...............",
        "oWwWo...............",
        ".ooo................",
    ]

    def draw(L, view, hx, hy):
        if view == "front":
            L.sprite(hx - 12, hy - 13, parse(FRONT, pal), under=RED)
        else:
            L.sprite(hx - 11, hy - 13, parse(SIDE, pal), under=RED)
    return draw


# ---------------------------------------------------------------- 貓耳
# 左耳（觀眾看到的左邊），右耳左右翻轉。原點在頭中心往左 11、往上 13。
EAR_L = [
    ".o.....",
    ".oo....",
    ".oFo...",
    "oFPFo..",
    "oFPPFo.",
    "oFFFFFo",
]
EAR_SIDE_NEAR = [   # 側面近耳（原點 hx-4, hy-13）
    "...o..",
    "..oo..",
    ".oFPo.",
    ".oFPFo",
    "oFFPFo",
    "oFFFFF",
]
EAR_SIDE_FAR = [    # 側面遠耳，只露出尖端（原點 hx-9, hy-12）
    ".o...",
    ".oo..",
    "oSSo.",
    "oSSSo",
]


def cat_ears(fur, inner, shade, tip=None, right=None, base=None):
    """tip：耳尖顏色（虎斑、橘貓）；right：右耳另外的毛色（三花）；base：耳朵根部的毛色（三花的白毛）。"""
    def ear(rows, f, t):
        pal = {"F": f, "P": inner, "S": shade}
        pix = parse(rows, pal)
        n = len(rows)
        if t:
            pix = [(x, y, t if (c == f and y <= n - 3) else c) for x, y, c in pix]
        if base:
            pix = [(x, y, base if (c == f and y >= n - 2) else c) for x, y, c in pix]
        return pix

    def draw(L, view, hx, hy):
        if view == "front":
            L.sprite(hx - 11, hy - 13, ear(EAR_L, fur, tip), under=RED)
            L.sprite(hx + 5, hy - 13, ear(mirror(EAR_L), right or fur, tip), under=RED)
        else:
            L.sprite(hx - 9, hy - 12, ear(EAR_SIDE_FAR, fur, None), under=RED)
            L.sprite(hx - 4, hy - 13, ear(EAR_SIDE_NEAR, right or fur, tip), under=RED)
    return draw


# ---------------------------------------------------------------- 耳機（全罩式）
def headphones(band, cup, pad, light=None):
    def draw(L, view, hx, hy):
        pal = {"B": band, "C": cup, "P": pad, "L": light or cup}
        if view == "front":
            # 頭帶：沿著頭頂弧線
            arc = [(-10, -6), (-9, -8), (-8, -9), (-7, -10), (-6, -10), (-5, -11), (-4, -11), (-3, -11),
                   (-2, -11), (-1, -11), (0, -11), (1, -11)]
            pts = arc + [(-x - 1, y) for x, y in arc]
            for x, y in pts:
                L.put(hx + x, hy + y, band)
                L.put(hx + x, hy + y - 1, OUTLINE)
            for x, y in ((-11, -6), (-11, -5), (-10, -7), (10, -6), (10, -7), (9, -8)):
                L.put(hx + x, hy + y, OUTLINE)
            cupL = [
                ".oooo",
                "oLCCo",
                "oCCCPo",
                "oCCCPo",
                "oCCCPo",
                "oCCCPo",
                ".oooo",
            ]
            L.sprite(hx - 15, hy - 3, parse(cupL, pal))
            L.sprite(hx + 10, hy - 3, parse([r.rjust(6, ".")[::-1] for r in cupL], pal))
        else:
            for y in range(-11, -2):
                L.put(hx - 3, hy + y, band); L.put(hx - 2, hy + y, OUTLINE if y == -11 else band)
            L.put(hx - 3, hy - 12, OUTLINE); L.put(hx - 2, hy - 12, OUTLINE)
            cup_s = [
                ".oooo.",
                "oLCCCo",
                "oCLCCo",
                "oCCCCo",
                "oCCCCo",
                "oCCCCo",
                ".oooo.",
            ]
            L.sprite(hx - 6, hy - 3, parse(cup_s, pal))
    return draw


# ---------------------------------------------------------------- 清單
C = dict(
    black=(38, 36, 44), black_hi=(96, 94, 112), pink=(246, 186, 190), white=(255, 255, 255),
    white_sh=(206, 206, 222), orange=(240, 150, 60), orange_dk=(196, 98, 40), gray=(150, 150, 166),
    gray_dk=(96, 94, 112), red=(240, 52, 60), dred=(140, 10, 30), cream=(250, 226, 196),
    sakura=(255, 196, 214), sakura_dk=(224, 132, 164), gold=(222, 178, 64),
)

ITEMS = {
    # id: (名稱, 欄位, 畫法)
    "ears_black": ("黑貓耳", "head", cat_ears(C["black"], C["pink"], C["black_hi"])),
    "ears_white": ("白貓耳", "head", cat_ears(C["white"], C["pink"], C["white_sh"])),
    "ears_orange": ("橘貓耳", "head", cat_ears(C["orange"], C["pink"], C["orange_dk"])),
    "ears_tabby": ("灰虎斑貓耳", "head", cat_ears(C["gray"], C["pink"], C["gray_dk"], tip=C["gray_dk"])),
    "ears_calico": ("三花貓耳", "head", cat_ears(C["orange"], C["pink"], C["orange_dk"], right=C["black"], base=C["white"])),
    "phones_black": ("黑色耳機", "head", headphones((150, 150, 166), (66, 66, 78), C["red"], light=(176, 176, 192))),
    "phones_white": ("白色耳機", "head", headphones(C["white_sh"], C["white"], C["sakura_dk"], light=C["white"])),
    "phones_pink": ("粉色耳機", "head", headphones(C["sakura_dk"], C["sakura"], C["white"], light=C["white"])),
    "scarf_red": ("紅色圍巾", "neck", scarf((214, 44, 52), (246, 110, 110), (150, 20, 36))),
    "scarf_cream": ("奶白圍巾", "neck", scarf((246, 236, 216), (255, 255, 255), (214, 196, 170))),
    "scarf_green": ("墨綠圍巾", "neck", scarf((46, 110, 74), (86, 156, 104), (26, 70, 48))),
    "scarf_mustard": ("芥末黃圍巾", "neck", scarf((222, 170, 50), (244, 210, 110), (170, 120, 30))),
    "scarf_pink": ("粉紅圍巾", "neck", scarf((244, 160, 190), (255, 210, 226), (210, 110, 150))),
    "glasses_round": ("圓框眼鏡", "eyes", glasses((70, 52, 50))),
    "outfit_white": ("白色夏季制服", "outfit", outfit((232, 232, 242), (176, 178, 200), (44, 58, 120))),
    "outfit_navy": ("海軍藍制服", "outfit", outfit((40, 52, 104), (110, 128, 186), (92, 92, 104), sock=(32, 34, 62))),
    "outfit_wine": ("酒紅制服", "outfit", outfit((110, 30, 46), (196, 90, 104), (30, 28, 36))),
    "outfit_xmas": ("聖誕服", "outfit", outfit((204, 34, 46), (255, 255, 255), (132, 18, 34))),
    "hat_santa": ("聖誕帽", "head", santa_hat()),
    "blade_default": ("原本的剪刀", "weapon", blade()),
    "blade_silver": ("銀白剪刀", "weapon", blade(red=(224, 228, 240), red_dk=(150, 156, 178), black=(104, 110, 132),
                                               edge=(196, 202, 220))),
    "blade_sakura": ("櫻花粉剪刀", "weapon", blade(red=(255, 172, 202), red_dk=(214, 98, 148), black=(250, 236, 242),
                                                edge=(236, 186, 206))),
    "blade_ice": ("冰藍剪刀", "weapon", blade(red=(130, 206, 255), red_dk=(40, 112, 204), black=(30, 46, 96),
                                           edge=(150, 200, 255), pivot=(255, 255, 255))),
    "blade_gold": ("黃金剪刀", "weapon", blade(red=(244, 204, 84), red_dk=(178, 126, 30), black=(70, 46, 24),
                                            edge=(204, 162, 72), pivot=(240, 52, 60))),
    "blade_void": ("湮滅紫剪刀", "weapon", blade(red=(176, 96, 236), red_dk=(92, 32, 144), black=(34, 22, 48),
                                              edge=(124, 84, 176), pivot=(100, 230, 240))),
    "garden_green": ("園藝剪刀（綠）", "weapon", blade("garden", grip=(76, 156, 84), grip_dk=(40, 96, 50),
                                                   edge=(255, 255, 255))),
    "garden_orange": ("園藝剪刀（橘）", "weapon", blade("garden", grip=(244, 140, 50), grip_dk=(180, 86, 30),
                                                    edge=(255, 255, 255))),
    "kids_yellow": ("兒童剪刀（黃）", "weapon", blade("kids", grip=(252, 206, 60), grip_dk=(206, 150, 30),
                                                 edge=(255, 255, 255), pivot=(255, 255, 255))),
    "kids_blue": ("兒童剪刀（藍）", "weapon", blade("kids", grip=(84, 156, 244), grip_dk=(40, 94, 184),
                                               edge=(255, 255, 255), pivot=(255, 255, 255))),
    "kids_pink": ("兒童剪刀（粉）", "weapon", blade("kids", grip=(250, 150, 190), grip_dk=(212, 98, 150),
                                               edge=(255, 255, 255), pivot=(255, 255, 255))),
    "gloves_white": ("白手套", "hands", gloves((255, 255, 255), (206, 206, 222))),
    "gloves_red": ("紅手套", "hands", gloves((220, 48, 56), (150, 20, 36))),
    "gloves_pink": ("粉紅手套", "hands", gloves((244, 160, 190), (210, 110, 150))),
    "gloves_navy": ("深藍手套", "hands", gloves((60, 76, 150), (36, 44, 100))),
    "gloves_brown": ("咖啡色毛線手套", "hands", gloves((150, 100, 64), (110, 70, 44))),
}


# 套裝：選單裡一次穿上好幾個部位
SETS = [{"name": "聖誕套裝", "items": {"outfit": "outfit_xmas", "head": "hat_santa"}}]
# 部位沒選東西時用的預設（不會出現在選單清單裡，選單上顯示成它的名字）：原本的剪刀要在制服換色之後蓋回去
DEFAULTS = {"weapon": "blade_default"}


def anchors(assets):
    meta = json.load(open(os.path.join(assets, "anims.json"), encoding="utf-8"))
    out = {}
    for n, m in meta.items():
        sheet = Image.open(os.path.join(assets, n + ".png")).convert("RGBA")
        L = []
        for i in range(m["frames"]):
            ov = OVERRIDE.get(n, {})
            if i in ov:
                L.append(ov[i]); continue
            fr = sheet.crop((i * m["w"], 0, (i + 1) * m["w"], m["h"]))
            L.append(auto_anchor(fr, LOOSE[n], 12) if n in LOOSE else auto_anchor(fr))
        out[n] = L
    return meta, out


def build(assets, outdir, only=None):
    meta, anc = anchors(assets)
    for iid, (name, slot, draw) in ITEMS.items():
        if only and iid not in only:
            continue
        d = os.path.join(outdir, iid)
        os.makedirs(d, exist_ok=True)
        for n, m in meta.items():
            sheet = Image.open(os.path.join(assets, n + ".png")).convert("RGBA")
            strips = {k: Image.new("RGBA", sheet.size, (0, 0, 0, 0)) for k in ("", "_erase", "_top")}
            Layer.anim = n
            for i, a in enumerate(anc[n]):
                Layer.index = i
                base = sheet.crop((i * m["w"], 0, (i + 1) * m["w"], m["h"]))
                if getattr(draw, "raw", False):
                    L = Layer(base)
                    draw(L, None, 0, 0)
                elif not a:
                    continue
                elif a[0] == "side_l":        # 朝左的側面：把圖翻過來當朝右畫，畫完再翻回去
                    view, hx, hy = a
                    L = Layer(base.transpose(Image.FLIP_LEFT_RIGHT))
                    if getattr(draw, "hands", False):
                        L.hands = find_hands(L.base, n, ["side", m["w"] - 1 - hx, hy])
                    draw(L, "side", m["w"] - 1 - hx, hy)
                    if getattr(draw, "outline", True):
                        L.auto_outline()
                    L.img = L.img.transpose(Image.FLIP_LEFT_RIGHT)
                    L.p = L.img.load()
                else:
                    view, hx, hy = a
                    L = Layer(base)
                    if getattr(draw, "hands", False):
                        L.hands = find_hands(base, n, a)
                    draw(L, view, hx, hy)
                    if getattr(draw, "outline", True):
                        L.auto_outline()
                for box in HIDE.get(n, {}).get(i, ()):
                    L.hide(box)
                strips[""].alpha_composite(L.img, (i * m["w"], 0))
                strips["_erase"].alpha_composite(L.erase, (i * m["w"], 0))
                strips["_top"].alpha_composite(L.top, (i * m["w"], 0))
            for k, im in strips.items():
                if im.getbbox():
                    im.save(os.path.join(d, n + k + ".png"), optimize=True)
    json.dump({"items": [{"id": k, "name": v[0], "slot": v[1]} for k, v in ITEMS.items()], "sets": SETS,
               "defaults": DEFAULTS},
              open(os.path.join(outdir, "items.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return anc


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2], set(sys.argv[3:]) or None)
    print("ok", len(ITEMS), "accessories")
