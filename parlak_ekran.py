# -*- coding: utf-8 -*-
"""
Jarvis'in parlak, yarı saydam masaüstü arayüzü (Windows).

Her öğe (reaktör, bilgi paneli, mesajlar) ayrı bir "katmanlı pencere"dir ve
UpdateLayeredWindow ile piksel piksel saydamlıkla gösterilir: parlamalar yumuşak,
arka plan görünür, tamamen saydam yerlere tıklayınca alttaki pencereye geçer.
Çizimler cizim.py'de, ayrı bir iş parçacığında üretilir.
"""

import os
import math
import time
import queue
import threading
import ctypes
import ctypes.wintypes as wt
import tkinter as tk
from PIL import Image, ImageChops

import cizim

# ----------------------------------------------------------------------------
# Win32
# ----------------------------------------------------------------------------

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
ULW_ALPHA = 0x02
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
DIB_RGB_COLORS = 0


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD), ("biSizeImage", wt.DWORD),
                ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


user32.GetParent.restype = wt.HWND
user32.GetParent.argtypes = [wt.HWND]
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.GetWindowLongW.restype = ctypes.c_long
user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
user32.SetWindowLongW.restype = ctypes.c_long
user32.SetWindowLongW.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_long]
user32.UpdateLayeredWindow.restype = wt.BOOL
user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT), ctypes.POINTER(wt.SIZE),
                                       wt.HDC, ctypes.POINTER(wt.POINT), wt.COLORREF,
                                       ctypes.POINTER(BLENDFUNCTION), wt.DWORD]
gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateDIBSection.restype = wt.HBITMAP
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
gdi32.SelectObject.restype = wt.HGDIOBJ
gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
gdi32.DeleteObject.argtypes = [wt.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wt.HDC]


def bgra_premul(im):
    """RGBA PIL resmini Windows'un beklediği ön-çarpımlı BGRA baytlarına çevirir."""
    r, g, b, a = im.split()
    r = ImageChops.multiply(r, a)
    g = ImageChops.multiply(g, a)
    b = ImageChops.multiply(b, a)
    return Image.merge("RGBA", (b, g, r, a)).tobytes()


class Katman:
    """Piksel saydamlıklı, her zaman üstte bir pencere (tkinter Toplevel üzerine)."""

    def __init__(self, kok, x, y, w, h):
        self.top = top = tk.Toplevel(kok)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.configure(bg="black")
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.update_idletasks()
        self.hwnd = user32.GetParent(top.winfo_id()) or top.winfo_id()
        ex = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | WS_EX_TOOLWINDOW)
        self.x, self.y, self.w, self.h = x, y, w, h
        self._dc = None
        self._bmp = None
        self._eski = None
        self._bits = ctypes.c_void_p()
        self._boyut = None
        self.gorunur = True

    def _dib(self, w, h):
        if self._boyut == (w, h):
            return
        self._temizle()
        ekran = user32.GetDC(None)
        self._dc = gdi32.CreateCompatibleDC(ekran)
        user32.ReleaseDC(None, ekran)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # yukarıdan aşağı
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        self._bits = ctypes.c_void_p()
        self._bmp = gdi32.CreateDIBSection(self._dc, ctypes.byref(bmi), DIB_RGB_COLORS,
                                           ctypes.byref(self._bits), None, 0)
        self._eski = gdi32.SelectObject(self._dc, self._bmp)
        self._boyut = (w, h)

    def _temizle(self):
        if self._dc:
            gdi32.SelectObject(self._dc, self._eski)
            gdi32.DeleteObject(self._bmp)
            gdi32.DeleteDC(self._dc)
        self._dc = self._bmp = self._eski = None
        self._boyut = None

    def goster(self, veri, w, h, x=None, y=None):
        """veri: bgra_premul() çıktısı."""
        if x is not None:
            self.x, self.y = int(x), int(y)
        if (w, h) != (self.w, self.h):
            self.w, self.h = w, h
            self.top.geometry(f"{w}x{h}+{self.x}+{self.y}")
        self._dib(w, h)
        ctypes.memmove(self._bits, veri, len(veri))
        ekran = user32.GetDC(None)
        hedef = wt.POINT(self.x, self.y)
        boyut = wt.SIZE(w, h)
        kaynak = wt.POINT(0, 0)
        karisim = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(self.hwnd, ekran, ctypes.byref(hedef), ctypes.byref(boyut), self._dc,
                                   ctypes.byref(kaynak), 0, ctypes.byref(karisim), ULW_ALPHA)
        user32.ReleaseDC(None, ekran)

    def tasi(self, x, y):
        self.x, self.y = int(x), int(y)
        ekran = user32.GetDC(None)
        hedef = wt.POINT(self.x, self.y)
        boyut = wt.SIZE(self.w, self.h)
        kaynak = wt.POINT(0, 0)
        karisim = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        if self._dc:
            user32.UpdateLayeredWindow(self.hwnd, ekran, ctypes.byref(hedef), ctypes.byref(boyut), self._dc,
                                       ctypes.byref(kaynak), 0, ctypes.byref(karisim), ULW_ALPHA)
        user32.ReleaseDC(None, ekran)

    def gizle(self):
        self.top.withdraw()
        self.gorunur = False

    def goster_pencere(self):
        self.top.deiconify()
        self.top.attributes("-topmost", True)
        self.gorunur = True


# ----------------------------------------------------------------------------
# Arayüz
# ----------------------------------------------------------------------------

class ParlakEkran:
    def __init__(self, konum="sag-alt", konum_dosyasi=None, fps=25):
        self.kuyruk = queue.Queue()
        self.konum = konum
        self.konum_dosyasi = konum_dosyasi
        self.fps = fps
        self.durum_adi = "baslatiliyor"
        self.ipucu = "Sistemler yükleniyor…"
        self.seviye_hedef = 0.0
        self.seviye_su_an = 0.0
        self.mesajlar = []
        self.hava = None
        self.istat = {}
        self.bilgi = {}
        self.panel_gizli = False
        self.calisiyor = True
        self.aktif = True
        self.on_komut = self.on_dinle = self.on_kapat = self.on_hazir = None
        self._r_kare = None       # (bayt, w, h)
        self._p_kare = None
        self._m_kare = None
        self._m_degisti = True
        self._kilit = threading.Lock()

    # ---------- diğer thread'lerden ----------
    def durum(self, ad, ipucu=None):
        self.durum_adi = ad
        varsayilan = {"bekliyor": "“Hey Jarvis” de  ·  reaktöre tıkla", "dinliyor": "Seni dinliyorum…",
                      "dusunuyor": "Bir saniye…", "baslatiliyor": "Sistemler yükleniyor…"}.get(ad, "")
        self.ipucu = ipucu if ipucu is not None else varsayilan
        self._m_degisti = True

    def mesaj(self, kim, metin):
        if kim in ("jarvis", "sen"):
            with self._kilit:
                self.mesajlar.append((kim, metin, time.time()))
                self.mesajlar = self.mesajlar[-8:]
            self._m_degisti = True

    def seviye(self, deger):
        self.seviye_hedef = max(0.0, min(1.0, float(deger)))

    def veri(self, fonk, sozluk):
        if fonk == "setWeather":
            self.hava = sozluk
        elif fonk == "setStats":
            self.istat = sozluk
        elif fonk == "setInfo":
            self.bilgi.update(sozluk)

    def kapat(self):
        self.kuyruk.put("kapat")

    # ---------- kurulum ----------
    def calistir(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
        self.kok = kok = tk.Tk()
        kok.withdraw()
        kok.title("J.A.R.V.I.S.")
        self.W, self.H = kok.winfo_screenwidth(), kok.winfo_screenheight()
        self.s = s = max(1.0, kok.winfo_fpixels("1i") / 96.0)
        self.m = int(22 * s)

        self.reaktor = cizim.Reaktor(R=int(92 * s), olcek=s)
        rg, ry = self.reaktor.gen, self.reaktor.yuk
        x, y = self._baslangic_konumu(rg, ry)
        self.k_reaktor = Katman(kok, x, y, rg, ry)
        self.k_panel = Katman(kok, self.W - int(330 * s) - self.m, self.m, int(330 * s), int(300 * s))
        self.k_mesaj = Katman(kok, 0, 0, int(440 * s), int(100 * s))
        self.panel_alt = self.m + int(300 * s)

        t = self.k_reaktor.top
        t.bind("<ButtonPress-1>", self._bas)
        t.bind("<B1-Motion>", self._surukle)
        t.bind("<ButtonRelease-1>", self._birak)
        t.bind("<Button-3>", self._menu_ac)
        t.configure(cursor="hand2")

        self.menu = tk.Menu(kok, tearoff=0, bg="#08131b", fg="#dff6ff", activebackground="#0f3b4d",
                            activeforeground="#ffffff", bd=0, font=("Segoe UI", 10))
        self.menu.add_command(label="  Dinle", command=self._dinle)
        self.menu.add_command(label="  Komut yaz...", command=self._yazi_kutusu)
        self.menu.add_command(label="  Saat / hava panelini gizle-göster", command=self._panel_degistir)
        self.menu.add_separator()
        self.menu.add_command(label="  Jarvis'i kapat", command=self._kapat_tik)

        threading.Thread(target=self._reaktor_dongusu, daemon=True).start()
        threading.Thread(target=self._panel_dongusu, daemon=True).start()
        kok.after(15, self._goster_dongusu)
        kok.after(4000, self._ustte_tut)
        if self.on_hazir:
            kok.after(200, self.on_hazir)
        kok.mainloop()
        self.calisiyor = False

    def _baslangic_konumu(self, rg, ry):
        if self.konum_dosyasi and os.path.exists(self.konum_dosyasi):
            try:
                x, y = map(int, open(self.konum_dosyasi).read().split(","))
                if 0 <= x <= self.W - 40 and 0 <= y <= self.H - 40:
                    return x, y
            except Exception:
                pass
        alt = int(48 * self.s)  # görev çubuğu
        if self.konum == "sol-alt":
            return self.m, self.H - ry - alt
        if self.konum == "orta":
            return (self.W - rg) // 2, (self.H - ry) // 2
        return self.W - rg - self.m, self.H - ry - alt

    # ---------- çizim iş parçacıkları ----------
    def _reaktor_dongusu(self):
        aralik = 1.0 / self.fps
        onceki = time.time()
        while self.calisiyor:
            bas = time.time()
            dt = bas - onceki
            onceki = bas
            ad = self.durum_adi
            hedef = self.seviye_hedef
            if ad == "konusuyor":
                hedef = .35 + .4 * abs(math.sin(bas * 7)) * (.6 + .4 * math.sin(bas * 19))
            elif ad == "dusunuyor":
                hedef = .15
            elif ad in ("bekliyor", "baslatiliyor"):
                hedef = hedef * .4
            self.seviye_su_an += (hedef - self.seviye_su_an) * .3
            try:
                im = self.reaktor.kare(ad, self.seviye_su_an, dt, self.ipucu, bas)
                self._r_kare = (bgra_premul(im), im.size[0], im.size[1])
            except Exception as e:
                print("Reaktör çizim hatası:", e)
            time.sleep(max(0.005, aralik - (time.time() - bas)))

    def _panel_dongusu(self):
        son_sn = -1
        son_mesaj = 0
        while self.calisiyor:
            simdi = time.time()
            renk = cizim.DURUM_RENK.get(self.durum_adi, cizim.DURUM_RENK["bekliyor"])
            try:
                sn = int(simdi)
                if sn != son_sn and not self.panel_gizli:
                    son_sn = sn
                    p = cizim.bilgi_paneli(self.s, cizim.DURUM_RENK["bekliyor"], self.hava, self.istat, self.bilgi)
                    self._p_kare = (bgra_premul(p), p.size[0], p.size[1])
                    self.panel_alt = self.m + p.size[1]
                with self._kilit:
                    mesajlar = list(self.mesajlar)
                solan = any(20 < simdi - t < 31 for _, _, t in mesajlar)
                if self._m_degisti or (solan and simdi - son_mesaj > .1):
                    self._m_degisti = False
                    son_mesaj = simdi
                    self._m_kare = self._mesaj_resmi(renk, mesajlar, simdi)
            except Exception as e:
                print("Panel çizim hatası:", e)
            time.sleep(0.05)

    def _mesaj_resmi(self, renk, mesajlar, simdi):
        s = self.s
        kr = self.k_reaktor
        R = self.reaktor.R
        halka_ust = kr.y + self.reaktor.c - R * 1.35
        genislik = int(440 * s)
        sag = min(self.W - self.m, kr.x + kr.w // 2 + int(R * 1.3))
        if kr.x + kr.w / 2 < self.W / 2:  # reaktör soldaysa kartlar sola hizalı
            sol = max(self.m, kr.x + kr.w // 2 - int(R * 1.3))
        else:
            sol = max(self.m, sag - genislik)
        ust_sinir = self.m
        if not self.panel_gizli and sol + genislik > self.W - int(330 * s) - self.m:
            ust_sinir = self.panel_alt + int(14 * s)
        yuk = int(halka_ust - ust_sinir)
        if yuk < int(80 * s):
            return (b"", 0, 0, 0, 0)
        im = cizim.mesaj_kartlari(s, renk, mesajlar, simdi, genislik=440, en_yuk=yuk / s)
        return (bgra_premul(im), im.size[0], im.size[1], sol, int(halka_ust - im.size[1]))

    # ---------- tk iş parçacığı: hazır kareleri ekrana bas ----------
    def _goster_dongusu(self):
        try:
            while True:
                try:
                    if self.kuyruk.get_nowait() == "kapat":
                        self.calisiyor = False
                        self.kok.destroy()
                        return
                except queue.Empty:
                    break
            if self._r_kare:
                veri, w, h = self._r_kare
                self._r_kare = None
                self.k_reaktor.goster(veri, w, h)
            if self._p_kare and not self.panel_gizli:
                veri, w, h = self._p_kare
                self._p_kare = None
                self.k_panel.goster(veri, w, h, self.W - w - self.m, self.m)
            if self._m_kare:
                veri, w, h, x, y = self._m_kare
                self._m_kare = None
                if w:
                    if not self.k_mesaj.gorunur:
                        self.k_mesaj.goster_pencere()
                    self.k_mesaj.goster(veri, w, h, x, y)
                elif self.k_mesaj.gorunur:
                    self.k_mesaj.gizle()
        except Exception as e:
            print("Ekran hatası:", e)
        self.kok.after(15, self._goster_dongusu)

    def _ustte_tut(self):
        for k in (self.k_reaktor, self.k_panel, self.k_mesaj):
            try:
                if k.gorunur:
                    k.top.attributes("-topmost", True)
            except Exception:
                pass
        self.kok.after(4000, self._ustte_tut)

    # ---------- fare ----------
    def _bas(self, e):
        self._surukleme = (e.x_root, e.y_root, self.k_reaktor.x, self.k_reaktor.y, False)

    def _surukle(self, e):
        x0, y0, kx, ky, tasindi = self._surukleme
        dx, dy = e.x_root - x0, e.y_root - y0
        if not tasindi and abs(dx) + abs(dy) < 5:
            return
        self._surukleme = (x0, y0, kx, ky, True)
        self.k_reaktor.tasi(kx + dx, ky + dy)

    def _birak(self, e):
        tasindi = getattr(self, "_surukleme", (0, 0, 0, 0, False))[4]
        if tasindi:
            self._m_degisti = True
            if self.konum_dosyasi:
                try:
                    with open(self.konum_dosyasi, "w") as f:
                        f.write(f"{self.k_reaktor.x},{self.k_reaktor.y}")
                except Exception:
                    pass
        else:
            self._dinle()

    def _menu_ac(self, e):
        try:
            self.menu.tk_popup(e.x_root, e.y_root)
        finally:
            self.menu.grab_release()

    def _dinle(self):
        if self.on_dinle:
            self.on_dinle()

    def _panel_degistir(self):
        self.panel_gizli = not self.panel_gizli
        if self.panel_gizli:
            self.k_panel.gizle()
        else:
            self.k_panel.goster_pencere()
        self._m_degisti = True

    def _kapat_tik(self):
        if self.on_kapat:
            self.on_kapat()
        else:
            self.kapat()

    def _yazi_kutusu(self):
        s = self.s
        renk = "#%02x%02x%02x" % cizim.DURUM_RENK["bekliyor"]
        k = tk.Toplevel(self.kok)
        k.overrideredirect(True)
        k.attributes("-topmost", True)
        k.configure(bg=renk)
        gen, yuk = int(460 * s), int(48 * s)
        kr = self.k_reaktor
        x = max(10, min(self.W - gen - 10, kr.x + kr.w // 2 - gen // 2))
        y = max(10, kr.y - yuk - int(10 * s))
        k.geometry(f"{gen}x{yuk}+{x}+{y}")
        ic = tk.Frame(k, bg="#06121a")
        ic.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(ic, text="  >_", bg="#06121a", fg=renk, font=("Bahnschrift", 13, "bold")).pack(side="left")
        g = tk.Entry(ic, bg="#06121a", fg="#e6faff", insertbackground=renk, relief="flat",
                     font=("Segoe UI", 13))
        g.pack(side="left", fill="both", expand=True, padx=(6, 12))

        def gonder(_=None):
            metin = g.get().strip()
            k.destroy()
            if metin and self.on_komut:
                self.on_komut(metin)

        g.bind("<Return>", gonder)
        g.bind("<Escape>", lambda _: k.destroy())
        k.after(60, lambda: (k.focus_force(), g.focus_set()))
