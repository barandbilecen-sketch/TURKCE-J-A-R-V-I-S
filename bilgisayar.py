# -*- coding: utf-8 -*-
"""
Jarvis'in fareyi ve klavyeyi kullanması (Windows, ek paket gerektirmez).

Claude'un "computer" araç setinden gelen eylemleri (left_click, type, key, scroll...)
gerçek fare/klavye hareketine çevirir. Koordinatlar, Claude'a gönderilen küçültülmüş
ekran görüntüsünün piksel uzayındadır; burada gerçek ekrana ölçeklenir.

ACİL DURDURMA: fareyi ekranın sol üst köşesine götür ya da Esc tuşunu basılı tut.
"""

import io
import time
import base64
import ctypes

EN_UZUN_KENAR = 1280      # Claude'a gönderilen ekran görüntüsünün uzun kenarı
_olcek = 1.0              # gerçek piksel * _olcek = görüntü pikseli


class Durduruldu(Exception):
    pass


def _win():
    return ctypes.windll.user32


def dpi_ayarla():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            _win().SetProcessDPIAware()
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Ekran görüntüsü
# ----------------------------------------------------------------------------

def ekran_resmi():
    """Birincil ekranın görüntüsü (PIL), Claude'a uygun boyuta küçültülmüş."""
    global _olcek
    from PIL import ImageGrab
    im = ImageGrab.grab()
    w, h = im.size
    _olcek = min(1.0, EN_UZUN_KENAR / max(w, h))
    if _olcek < 1.0:
        im = im.resize((round(w * _olcek), round(h * _olcek)))
    return im.convert("RGB")


def b64(im, kalite=80):
    tampon = io.BytesIO()
    im.save(tampon, format="JPEG", quality=kalite)
    return base64.b64encode(tampon.getvalue()).decode()


def resim_blogu(im):
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64(im)}}


def _gercek(xy):
    x, y = xy
    return int(round(x / _olcek)), int(round(y / _olcek))


# ----------------------------------------------------------------------------
# Düşük seviye fare / klavye
# ----------------------------------------------------------------------------

LEFTDOWN, LEFTUP = 0x0002, 0x0004
RIGHTDOWN, RIGHTUP = 0x0008, 0x0010
MIDDLEDOWN, MIDDLEUP = 0x0020, 0x0040
WHEEL, HWHEEL = 0x0800, 0x1000
KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1

ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", ULONG_PTR)]


class _INPUTunion(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("u", _INPUTunion)]


VK = {
    "return": 0x0D, "enter": 0x0D, "tab": 0x09, "escape": 0x1B, "esc": 0x1B, "backspace": 0x08,
    "delete": 0x2E, "del": 0x2E, "insert": 0x2D, "space": 0x20, "up": 0x26, "down": 0x28, "left": 0x25,
    "right": 0x27, "home": 0x24, "end": 0x23, "page_up": 0x21, "pageup": 0x21, "prior": 0x21,
    "page_down": 0x22, "pagedown": 0x22, "next": 0x22, "ctrl": 0x11, "control": 0x11, "alt": 0x12,
    "shift": 0x10, "super": 0x5B, "win": 0x5B, "cmd": 0x5B, "meta": 0x5B, "caps_lock": 0x14,
    "print": 0x2C, "menu": 0x5D, "minus": 0xBD, "plus": 0xBB, "equal": 0xBB, "comma": 0xBC,
    "period": 0xBE, "slash": 0xBF, "semicolon": 0xBA, "apostrophe": 0xDE,
    "volumeup": 0xAF, "volumedown": 0xAE, "volumemute": 0xAD,
}
for _i in range(1, 25):
    VK[f"f{_i}"] = 0x6F + _i


def _vk(ad):
    a = ad.strip().lower().replace("-", "_")
    if a in VK:
        return VK[a]
    if len(a) == 1 and a.isalnum():
        return ord(a.upper())
    if a.startswith("kp_") and a[3:].isdigit():
        return 0x60 + int(a[3:])
    raise ValueError(f"Bilinmeyen tuş: {ad}")


def _tus_bas(vk):
    _win().keybd_event(vk, 0, 0, 0)


def _tus_birak(vk):
    _win().keybd_event(vk, 0, KEYUP, 0)


def _kontrol():
    """Acil durdurma: fare sol üst köşede veya Esc basılı tutuluyor."""
    import ctypes.wintypes as wt
    nokta = wt.POINT()
    _win().GetCursorPos(ctypes.byref(nokta))
    if nokta.x <= 3 and nokta.y <= 3:
        raise Durduruldu("Fare sol üst köşeye götürüldü")
    if _win().GetAsyncKeyState(0x1B) & 0x8000:
        raise Durduruldu("Esc basılı tutuldu")


def _git(x, y):
    _win().SetCursorPos(int(x), int(y))


def _modifiyerler(metin):
    if not metin:
        return []
    return [_vk(m) for m in metin.replace(" ", "").split("+") if m]


def _tikla(xy, asagi, yukari, kez=1, mod=None):
    if xy:
        _git(*_gercek(xy))
        time.sleep(0.05)
    modlar = _modifiyerler(mod)
    for m in modlar:
        _tus_bas(m)
    try:
        for _ in range(kez):
            _win().mouse_event(asagi, 0, 0, 0, 0)
            _win().mouse_event(yukari, 0, 0, 0, 0)
            time.sleep(0.04)
    finally:
        for m in reversed(modlar):
            _tus_birak(m)


def yaz(metin):
    """Her karakteri Unicode olarak gönderir (ğ, ş, ı, İ, € sorunsuz)."""
    for ch in metin:
        if ch == "\n":
            _tus_bas(0x0D)
            _tus_birak(0x0D)
            continue
        kodlar = ch.encode("utf-16-le")
        for i in range(0, len(kodlar), 2):
            kod = int.from_bytes(kodlar[i:i + 2], "little")
            girdiler = (INPUT * 2)()
            for j, bayrak in enumerate((KEYEVENTF_UNICODE, KEYEVENTF_UNICODE | KEYUP)):
                girdiler[j].type = INPUT_KEYBOARD
                girdiler[j].u.ki = KEYBDINPUT(0, kod, bayrak, 0, 0)
            _win().SendInput(2, ctypes.byref(girdiler), ctypes.sizeof(INPUT))
        time.sleep(0.008)


def tus(kombinasyon, tekrar=1):
    """'ctrl+s', 'Return', 'alt+tab' gibi."""
    parcalar = [p for p in kombinasyon.replace(" ", "+").split("+") if p]
    kodlar = [_vk(p) for p in parcalar]
    for _ in range(max(1, int(tekrar))):
        for k in kodlar:
            _tus_bas(k)
        time.sleep(0.03)
        for k in reversed(kodlar):
            _tus_birak(k)
        time.sleep(0.05)


# ----------------------------------------------------------------------------
# Claude araç setinin üyeleri
# ----------------------------------------------------------------------------

EYLEMLER = {"screenshot", "zoom", "left_click", "right_click", "middle_click", "double_click", "triple_click",
            "left_click_drag", "mouse_move", "left_mouse_down", "left_mouse_up", "cursor_position", "scroll",
            "type", "key", "hold_key", "wait"}


def eylem(ad, girdi):
    """Bir eylemi uygular; Claude'a dönecek tool_result içeriğini (liste) döndürür."""
    girdi = girdi or {}
    _kontrol()
    xy = girdi.get("coordinate")
    mod = girdi.get("text") if ad.endswith("click") or ad == "scroll" else None
    ekran_gonder = True
    not_ = "Tamam."

    if ad == "screenshot":
        pass
    elif ad == "zoom":
        from PIL import ImageGrab
        x0, y0, x1, y1 = girdi["region"]
        gx0, gy0 = _gercek((x0, y0))
        gx1, gy1 = _gercek((x1, y1))
        parca = ImageGrab.grab(bbox=(gx0, gy0, gx1, gy1)).convert("RGB")
        k = min(EN_UZUN_KENAR / max(parca.size), 4.0)
        parca = parca.resize((max(1, round(parca.size[0] * k)), max(1, round(parca.size[1] * k))))
        return [{"type": "text", "text": "Yakınlaştırılmış bölge:"}, resim_blogu(parca)]
    elif ad == "left_click":
        _tikla(xy, LEFTDOWN, LEFTUP, 1, mod)
    elif ad == "right_click":
        _tikla(xy, RIGHTDOWN, RIGHTUP, 1, mod)
    elif ad == "middle_click":
        _tikla(xy, MIDDLEDOWN, MIDDLEUP, 1, mod)
    elif ad == "double_click":
        _tikla(xy, LEFTDOWN, LEFTUP, 2, mod)
    elif ad == "triple_click":
        _tikla(xy, LEFTDOWN, LEFTUP, 3, mod)
    elif ad == "left_click_drag":
        sx, sy = _gercek(girdi["start_coordinate"])
        ex, ey = _gercek(girdi["coordinate"])
        modlar = _modifiyerler(girdi.get("text"))
        for m in modlar:
            _tus_bas(m)
        _git(sx, sy)
        time.sleep(0.05)
        _win().mouse_event(LEFTDOWN, 0, 0, 0, 0)
        for i in range(1, 16):
            _git(sx + (ex - sx) * i / 15, sy + (ey - sy) * i / 15)
            time.sleep(0.015)
        _win().mouse_event(LEFTUP, 0, 0, 0, 0)
        for m in reversed(modlar):
            _tus_birak(m)
    elif ad == "mouse_move":
        _git(*_gercek(xy))
    elif ad == "left_mouse_down":
        _win().mouse_event(LEFTDOWN, 0, 0, 0, 0)
    elif ad == "left_mouse_up":
        _win().mouse_event(LEFTUP, 0, 0, 0, 0)
    elif ad == "cursor_position":
        import ctypes.wintypes as wt
        p = wt.POINT()
        _win().GetCursorPos(ctypes.byref(p))
        return [{"type": "text", "text": f"İmleç: ({round(p.x * _olcek)}, {round(p.y * _olcek)})"}]
    elif ad == "scroll":
        if xy:
            _git(*_gercek(xy))
        yon = girdi.get("scroll_direction", "down")
        miktar = int(girdi.get("scroll_amount", 3))
        modlar = _modifiyerler(mod)
        for m in modlar:
            _tus_bas(m)
        if yon in ("up", "down"):
            _win().mouse_event(WHEEL, 0, 0, ctypes.c_ulong((120 if yon == "up" else -120) * miktar).value, 0)
        else:
            _win().mouse_event(HWHEEL, 0, 0, ctypes.c_ulong((120 if yon == "right" else -120) * miktar).value, 0)
        for m in reversed(modlar):
            _tus_birak(m)
    elif ad == "type":
        yaz(girdi.get("text", ""))
    elif ad == "key":
        tus(girdi.get("text", ""), girdi.get("repeat", 1))
    elif ad == "hold_key":
        kodlar = [_vk(p) for p in girdi.get("text", "").split("+") if p]
        for k in kodlar:
            _tus_bas(k)
        time.sleep(min(10.0, float(girdi.get("duration", 1))))
        for k in reversed(kodlar):
            _tus_birak(k)
    elif ad == "wait":
        time.sleep(min(10.0, float(girdi.get("duration", 1))))
    else:
        return [{"type": "text", "text": f"Desteklenmeyen eylem: {ad}"}]

    if ekran_gonder:
        if ad != "screenshot":
            time.sleep(0.6)  # ekranın tepki vermesine zaman tanı
        return [{"type": "text", "text": not_}, resim_blogu(ekran_resmi())]
    return [{"type": "text", "text": not_}]
