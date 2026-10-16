# -*- coding: utf-8 -*-
"""
Jarvis arayüzünün çizimi (yalnızca Pillow). Her şey yarı saydam RGBA resim olarak üretilir:
neon parlamalı ark reaktörü, buzlu cam bilgi paneli ve mesaj kartları.
"""

import math
import random
import datetime
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops

# ----------------------------------------------------------------------------
# Renkler ve yazı tipleri
# ----------------------------------------------------------------------------

DURUM_RENK = {
    "baslatiliyor": (63, 224, 255),
    "bekliyor": (63, 224, 255),
    "dinliyor": (110, 245, 255),
    "dusunuyor": (255, 179, 64),
    "konusuyor": (140, 238, 255),
    "hata": (255, 77, 94),
}
DURUM_HIZ = {"baslatiliyor": 3.0, "bekliyor": 1.0, "dinliyor": 2.0, "dusunuyor": 4.5, "konusuyor": 1.5, "hata": 0.5}
DURUM_ETIKET = {
    "baslatiliyor": "BAŞLATILIYOR",
    "bekliyor": "ÇEVRİMİÇİ",
    "dinliyor": "DİNLİYORUM",
    "dusunuyor": "İŞLENİYOR",
    "konusuyor": "YANITLIYOR",
    "hata": "UYARI",
}
GUN = ["PAZARTESİ", "SALI", "ÇARŞAMBA", "PERŞEMBE", "CUMA", "CUMARTESİ", "PAZAR"]
AY = ["OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ", "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK"]

CAM = (5, 16, 24)          # cam panel rengi
YAZI = (226, 246, 252)
SOLUK = (128, 168, 184)

_FONT_ADAYLARI = {
    "baslik": ["bahnschrift.ttf", "segoeuisl.ttf", "segoeui.ttf", "DejaVuSansCondensed.ttf", "DejaVuSans.ttf"],
    "kalin": ["seguisb.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"],
    "normal": ["segoeui.ttf", "DejaVuSans.ttf"],
    "ince": ["segoeuil.ttf", "segoeuisl.ttf", "segoeui.ttf", "DejaVuSans-ExtraLight.ttf", "DejaVuSans.ttf"],
}
_font_onbellek = {}


def font(tur, boyut):
    anahtar = (tur, int(boyut))
    if anahtar in _font_onbellek:
        return _font_onbellek[anahtar]
    f = None
    for ad in _FONT_ADAYLARI[tur]:
        for yol in (ad, "C:/Windows/Fonts/" + ad, "/usr/share/fonts/truetype/dejavu/" + ad):
            try:
                f = ImageFont.truetype(yol, int(boyut))
                break
            except OSError:
                continue
        if f:
            break
    if f is None:
        f = ImageFont.load_default()
    if tur == "baslik":
        try:  # Bahnschrift değişken font: yarı kalın
            f.set_variation_by_name("SemiBold")
        except Exception:
            pass
    _font_onbellek[anahtar] = f
    return f


def aralikli(metin, aralik=0.18):
    """Harf aralığı açılmış metin için yardımcı (her harfin x konumu)."""
    return metin, aralik


def metin_aralikli(d, xy, metin, f, renk, aralik_px, hiza="sol"):
    genislik = sum(f.getlength(h) for h in metin) + aralik_px * (len(metin) - 1)
    x, y = xy
    if hiza == "orta":
        x -= genislik / 2
    elif hiza == "sag":
        x -= genislik
    for h in metin:
        d.text((x, y), h, font=f, fill=renk)
        x += f.getlength(h) + aralik_px
    return genislik


def renklendir(maske, renk, beyaz_oran=0.0):
    """Gri tonlu maskeyi renkli RGBA'ya çevirir. beyaz_oran: parlak çekirdek için beyaza kaydırma."""
    r, g, b = renk
    if beyaz_oran:
        r = int(r + (255 - r) * beyaz_oran)
        g = int(g + (255 - g) * beyaz_oran)
        b = int(b + (255 - b) * beyaz_oran)
    katman = Image.new("RGBA", maske.size, (r, g, b, 0))
    katman.putalpha(maske)
    return katman


def neon(maske, renk, parlama=6, guc=0.9):
    """Keskin çizgi maskesine parlama ekleyip renkli RGBA döndürür."""
    hale = maske.filter(ImageFilter.GaussianBlur(parlama))
    hale = hale.point(lambda v: min(255, int(v * guc * 1.6)))
    alt = renklendir(hale, renk)
    ust = renklendir(maske, renk, beyaz_oran=0.35)
    return Image.alpha_composite(alt, ust)


# ----------------------------------------------------------------------------
# Ark reaktörü
# ----------------------------------------------------------------------------

class Reaktor:
    """Katmanlar bir kere çizilir, her karede döndürülüp birleştirilir."""

    def __init__(self, R=100, olcek=1.0):
        self.R = int(R)
        self.olcek = olcek
        self.S = int(self.R * 3.1)            # kare boyutu (halka + ses çubukları)
        self.etiket_h = int(self.R * 0.62)
        self.gen, self.yuk = self.S, self.S + self.etiket_h
        self.c = self.S / 2
        self._maskeler = self._maskeleri_ciz()
        self._renk_onbellek = {}
        self._cekirdek_onbellek = {}
        self.cubuk = [0.0] * 72
        self.aci = 0.0
        self._etiket_anahtar = None
        self._etiket_resim = None

    # ---------- maskeler (2x çizip küçültülür = yumuşak kenar) ----------
    def _tuval(self):
        k = 2
        im = Image.new("L", (self.S * k, self.S * k), 0)
        return im, ImageDraw.Draw(im), k

    def _bitir(self, im):
        return im.resize((self.S, self.S), Image.LANCZOS)

    def _halka(self, d, k, r, w, deger=255, bas=0, uz=360):
        c, R = self.c * k, self.R * k
        rr = r * R
        kutu = [c - rr, c - rr, c + rr, c + rr]
        if uz >= 360:
            d.ellipse(kutu, outline=deger, width=max(1, int(w * R)))
        else:
            d.arc(kutu, bas, bas + uz, fill=deger, width=max(1, int(w * R)))

    def _maskeleri_ciz(self):
        m = {}
        c = self.c

        # L1: dış tik halkası + köşeli parantez yayları (yavaş, saat yönü)
        im, d, k = self._tuval()
        C, R = c * k, self.R * k
        self._halka(d, k, 1.18, .006, 150)
        for i in range(120):
            a = math.radians(i * 3)
            uzun, orta = i % 10 == 0, i % 5 == 0
            r1, r2 = 1.12, (1.05 if uzun else 1.09 if orta else 1.105)
            w = .012 if uzun else .006
            d.line([C + math.cos(a) * r1 * R, C + math.sin(a) * r1 * R,
                    C + math.cos(a) * r2 * R, C + math.sin(a) * r2 * R],
                   fill=230 if uzun else 140, width=max(1, int(w * R)))
        for bas in (0, 120, 240):
            self._halka(d, k, 1.24, .014, 255, bas, 34)
            self._halka(d, k, 1.24, .006, 120, bas + 40, 10)
        m["l1"] = self._bitir(im)

        # L2: kalın parçalı yaylar (orta hız, ters)
        im, d, k = self._tuval()
        for bas, uz, guc in [(0, 58, 255), (66, 14, 200), (88, 74, 255), (170, 18, 170),
                             (196, 88, 255), (292, 8, 170), (308, 44, 230)]:
            self._halka(d, k, .99, .05, guc, bas, uz)
        m["l2"] = self._bitir(im)

        # L3: noktalı halka + vurgu yayı (hızlı, saat yönü)
        im, d, k = self._tuval()
        C, R = c * k, self.R * k
        for i in range(96):
            a = math.radians(i * 3.75)
            rr = .875 * R
            nr = .009 * R if i % 4 else .014 * R
            d.ellipse([C + math.cos(a) * rr - nr, C + math.sin(a) * rr - nr,
                       C + math.cos(a) * rr + nr, C + math.sin(a) * rr + nr], fill=200)
        self._halka(d, k, .81, .022, 255, 200, 60)
        self._halka(d, k, .81, .008, 160, 270, 25)
        m["l3"] = self._bitir(im)

        # L4: 10 bobin bloğu (Mark I tarzı), yavaş ters
        im, d, k = self._tuval()
        C, R = c * k, self.R * k
        for i in range(10):
            a1, a2 = math.radians(i * 36 + 4), math.radians(i * 36 + 30)
            ic, dis = .53 * R, .70 * R
            noktalar = []
            for j in range(12):
                a = a1 + (a2 - a1) * j / 11
                noktalar.append((C + math.cos(a) * dis, C + math.sin(a) * dis))
            for j in range(12):
                a = a2 - (a2 - a1) * j / 11
                noktalar.append((C + math.cos(a) * ic, C + math.sin(a) * ic))
            d.polygon(noktalar, fill=110, outline=255)
            d.line(noktalar[:12], fill=255, width=max(1, int(.012 * R)))
        m["l4"] = self._bitir(im)

        # Sabit: iç halkalar, üçgen, ince tikler
        im, d, k = self._tuval()
        C, R = c * k, self.R * k
        self._halka(d, k, .935, .006, 120)
        self._halka(d, k, .76, .004, 110)
        self._halka(d, k, .48, .014, 255)
        self._halka(d, k, .41, .005, 150)
        for i in range(36):
            a = math.radians(i * 10)
            d.line([C + math.cos(a) * .735 * R, C + math.sin(a) * .735 * R,
                    C + math.cos(a) * .76 * R, C + math.sin(a) * .76 * R], fill=150, width=max(1, int(.006 * R)))
        r3 = .33 * R
        uc = [(C + r3 * math.cos(math.radians(-90 + j * 120)), C + r3 * math.sin(math.radians(-90 + j * 120)))
              for j in range(3)]
        d.line(uc + [uc[0]], fill=255, width=max(1, int(.016 * R)), joint="curve")
        m["sabit"] = self._bitir(im)

        # Arka hale (yumuşak disk)
        im = Image.new("L", (self.S, self.S), 0)
        d = ImageDraw.Draw(im)
        rr = .62 * self.R
        d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=255)
        m["hale"] = im.filter(ImageFilter.GaussianBlur(self.R * .35))

        # Koyu iç zemin (açık renkli ekranlarda okunabilirlik için)
        im = Image.new("L", (self.S, self.S), 0)
        d = ImageDraw.Draw(im)
        rr = 1.27 * self.R
        d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=150)
        m["zemin"] = im.filter(ImageFilter.GaussianBlur(self.R * .08))
        return m

    # ---------- renkli katmanlar (duruma göre önbellekli) ----------
    def _renkli(self, renk):
        if renk in self._renk_onbellek:
            return self._renk_onbellek[renk]
        p = max(2, self.R * .05)
        k = {
            "zemin": renklendir(self._maskeler["zemin"], (2, 8, 13)),
            "hale": renklendir(self._maskeler["hale"].point(lambda v: v * .55), renk),
            "l1": neon(self._maskeler["l1"], renk, p, .7),
            "l2": neon(self._maskeler["l2"], renk, p * 1.2, .8),
            "l3": neon(self._maskeler["l3"], renk, p * .8, .7),
            "l4": neon(self._maskeler["l4"], renk, p, .6),
            "sabit": neon(self._maskeler["sabit"], renk, p, .8),
        }
        self._renk_onbellek[renk] = k
        return k

    def _cekirdek(self, renk, olc):
        """Çekirdek parlaması; boyut adımlara bölünüp önbelleklenir."""
        adim = round(olc * 20) / 20
        anahtar = (renk, adim)
        if anahtar in self._cekirdek_onbellek:
            return self._cekirdek_onbellek[anahtar]
        S, c = self.S, self.c
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        r0 = self.R * .46 * adim
        # radyal gradyan: halka halka
        katman = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(katman)
        adimlar = 40
        for i in range(adimlar, 0, -1):
            t = i / adimlar
            rr = r0 * t
            a = int(255 * (1 - t) ** 1.25)
            w = 1 - t
            col = (int(renk[0] + (255 - renk[0]) * w ** 2), int(renk[1] + (255 - renk[1]) * w ** 2),
                   int(renk[2] + (255 - renk[2]) * w ** 2), a)
            d.ellipse([c - rr, c - rr, c + rr, c + rr], fill=col)
        im = Image.alpha_composite(im, katman.filter(ImageFilter.GaussianBlur(self.R * .02)))
        if len(self._cekirdek_onbellek) > 200:
            self._cekirdek_onbellek.clear()
        self._cekirdek_onbellek[anahtar] = im
        return im

    @staticmethod
    def _dondur(im, aci):
        return im.rotate(-aci, resample=Image.BILINEAR)

    # ---------- bir kare ----------
    def kare(self, durum, seviye, dt, ipucu="", zaman=0.0):
        renk = DURUM_RENK.get(durum, DURUM_RENK["bekliyor"])
        self.aci = (self.aci + dt * 14 * DURUM_HIZ.get(durum, 1)) % 360
        a = self.aci
        k = self._renkli(renk)
        S, c, R = self.S, self.c, self.R

        out = Image.new("RGBA", (self.gen, self.yuk), (0, 0, 0, 0))
        adim = round(min(1.0, seviye) * 10) / 10
        kare = self._taban(renk, adim).copy()
        kare.alpha_composite(self._dondur(k["l1"], a * .5))
        kare.alpha_composite(self._dondur(k["l2"], -a * 1.3))
        kare.alpha_composite(self._dondur(k["l3"], a * 2.4))
        kare.alpha_composite(self._dondur(k["l4"], -a * .6))
        kare.alpha_composite(self._tepe(renk, adim))

        # ses halkası (dinlerken/konuşurken dışarı taşan çubuklar)
        d = ImageDraw.Draw(kare)
        aktif = durum in ("dinliyor", "konusuyor")
        n = len(self.cubuk)
        for i in range(n):
            if aktif:
                dalga = .5 + .5 * math.sin(zaman * 7 + i * .9) * math.sin(zaman * 3.1 + i * .37)
                hedef = seviye * (.25 + .75 * dalga)
            elif durum == "dusunuyor":
                hedef = .18 * max(0.0, math.sin(zaman * 5 - i * .35)) ** 4
            else:
                hedef = 0.0
            self.cubuk[i] += (hedef - self.cubuk[i]) * .35
            v = self.cubuk[i]
            if v < .02:
                continue
            aci = math.radians(i * 360 / n - 90)
            r1, r2 = 1.31 * R, (1.31 + .02 + v * .2) * R
            alfa = int(min(255, 90 + v * 400))
            d.line([c + math.cos(aci) * r1, c + math.sin(aci) * r1, c + math.cos(aci) * r2, c + math.sin(aci) * r2],
                   fill=renk + (alfa,), width=max(2, int(R * .022)))
        out.paste(kare, (0, 0))

        # durum etiketi (önbellekli)
        anahtar = (durum, ipucu)
        if self._etiket_anahtar != anahtar:
            self._etiket_resim = Image.new("RGBA", (self.gen, self.yuk), (0, 0, 0, 0))
            self._etiket(self._etiket_resim, durum, ipucu, renk)
            self._etiket_anahtar = anahtar
        out.alpha_composite(self._etiket_resim)
        return out

    def _taban(self, renk, adim):
        anahtar = ("taban", renk, adim)
        if anahtar not in self._cekirdek_onbellek:
            k = self._renkli(renk)
            im = k["zemin"].copy()
            hale = k["hale"]
            if adim > 0:
                a = hale.getchannel("A").point(lambda v: min(255, int(v * (1 + adim * 1.2))))
                hale = hale.copy()
                hale.putalpha(a)
            im.alpha_composite(hale)
            self._cekirdek_onbellek[anahtar] = im
        return self._cekirdek_onbellek[anahtar]

    def _tepe(self, renk, adim):
        anahtar = ("tepe", renk, adim)
        if anahtar not in self._cekirdek_onbellek:
            im = self._renkli(renk)["sabit"].copy()
            im.alpha_composite(self._cekirdek(renk, 1 + adim * .55))
            self._cekirdek_onbellek[anahtar] = im
        return self._cekirdek_onbellek[anahtar]

    def _etiket(self, out, durum, ipucu, renk):
        R = self.R
        d = ImageDraw.Draw(out)
        y0 = self.S - int(R * .12)
        f1 = font("baslik", R * .15)
        f2 = font("normal", R * .115)
        metin = DURUM_ETIKET.get(durum, durum.upper())
        aralik = R * .045
        gen = sum(f1.getlength(h) for h in metin) + aralik * (len(metin) - 1)
        gen2 = f2.getlength(ipucu) if ipucu else 0
        kutu_g = max(gen, gen2) + R * .5
        x1, x2 = self.c - kutu_g / 2, self.c + kutu_g / 2
        y2 = y0 + R * (.48 if ipucu else .3)
        zemin = Image.new("RGBA", out.size, (0, 0, 0, 0))
        zd = ImageDraw.Draw(zemin)
        zd.rounded_rectangle([x1, y0 - R * .06, x2, y2], radius=int(R * .08), fill=CAM + (175,))
        zd.line([x1 + R * .1, y0 - R * .06, x2 - R * .1, y0 - R * .06], fill=renk + (200,), width=max(1, int(R * .012)))
        out.alpha_composite(zemin)
        # parlayan başlık
        yazi = Image.new("L", out.size, 0)
        metin_aralikli(ImageDraw.Draw(yazi), (self.c, y0), metin, f1, 255, aralik, "orta")
        out.alpha_composite(neon(yazi, renk, max(2, R * .03), .7))
        if ipucu:
            d.text((self.c, y0 + R * .24), ipucu, font=f2, fill=SOLUK + (255,), anchor="ma")


# ----------------------------------------------------------------------------
# Cam panel yardımcıları
# ----------------------------------------------------------------------------

def cam_panel(gen, yuk, renk, olcek=1.0, alfa=226, kose=None):
    s = olcek
    im = Image.new("RGBA", (gen, yuk), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = int(14 * s) if kose is None else kose
    d.rounded_rectangle([0, 0, gen - 1, yuk - 1], radius=r, fill=CAM + (alfa,), outline=renk + (45,), width=max(1, int(s)))
    # üstte ince parlak çizgi
    ust = Image.new("L", (gen, yuk), 0)
    ImageDraw.Draw(ust).line([r, 1, gen - r, 1], fill=255, width=max(1, int(1.5 * s)))
    im.alpha_composite(neon(ust, renk, 3 * s, .5))
    # köşe parantezleri
    L, w = int(16 * s), max(2, int(2 * s))
    for (x, y, dx, dy) in [(0, 0, 1, 1), (gen - 1, 0, -1, 1), (0, yuk - 1, 1, -1), (gen - 1, yuk - 1, -1, -1)]:
        d.line([x, y + dy * L, x, y, x + dx * L, y], fill=renk + (230,), width=w)
    return im


def sar(metin, f, genislik):
    satirlar = []
    for paragraf in metin.split("\n"):
        mevcut = ""
        for kelime in paragraf.split(" "):
            dene = (mevcut + " " + kelime).strip()
            if f.getlength(dene) <= genislik or not mevcut:
                mevcut = dene
            else:
                satirlar.append(mevcut)
                mevcut = kelime
        satirlar.append(mevcut)
    return satirlar


# ----------------------------------------------------------------------------
# Hava ikonları
# ----------------------------------------------------------------------------

def hava_ikonu(tanim, boyut, renk):
    t = (tanim or "").lower()
    k = 3
    B = boyut * k
    im = Image.new("L", (B, B), 0)
    d = ImageDraw.Draw(im)
    w = max(2, int(B * .055))

    def gunes(cx, cy, r, isinlar=True):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=255, width=w)
        if isinlar:
            for i in range(8):
                a = math.radians(i * 45)
                d.line([cx + math.cos(a) * r * 1.45, cy + math.sin(a) * r * 1.45,
                        cx + math.cos(a) * r * 1.85, cy + math.sin(a) * r * 1.85], fill=255, width=w)

    def bulut(cx, cy, s):
        ImageDraw.Draw(im)
        maske = Image.new("L", (B, B), 0)
        md = ImageDraw.Draw(maske)
        for (x, y, r) in [(-.32, .05, .22), (-.05, -.12, .3), (.28, .02, .24)]:
            md.ellipse([cx + (x - r) * s, cy + (y - r) * s, cx + (x + r) * s, cy + (y + r) * s], fill=255)
        md.rounded_rectangle([cx - .55 * s, cy - .02 * s, cx + .52 * s, cy + .26 * s], radius=int(.13 * s), fill=255)
        kenar = maske.filter(ImageFilter.MaxFilter(3))
        ic = maske.filter(ImageFilter.MinFilter(max(3, (w // 2) * 2 + 1)))
        cizgi = ImageChops.subtract(kenar, ic)
        im.paste(0, mask=maske)
        im.paste(255, mask=cizgi)

    if any(x in t for x in ("açık", "güneş", "clear", "sunny")):
        gunes(B / 2, B / 2, B * .2)
    elif any(x in t for x in ("yağmur", "sağanak", "çisenti", "rain", "drizzle")):
        bulut(B / 2, B * .4, B * .8)
        for i in range(3):
            x = B * (.33 + i * .17)
            d.line([x, B * .72, x - B * .05, B * .88], fill=255, width=w)
    elif any(x in t for x in ("kar", "snow")):
        bulut(B / 2, B * .4, B * .8)
        for i in range(3):
            x = B * (.33 + i * .17)
            d.ellipse([x - w, B * .8 - w, x + w, B * .8 + w], fill=255)
    elif any(x in t for x in ("gök gürültü", "fırtına", "thunder")):
        bulut(B / 2, B * .38, B * .8)
        d.line([B * .52, B * .62, B * .44, B * .78, B * .55, B * .78, B * .47, B * .94], fill=255, width=w)
    elif any(x in t for x in ("sis", "pus", "fog", "mist")):
        for i in range(4):
            y = B * (.3 + i * .14)
            d.line([B * .2, y, B * .8, y], fill=255, width=w)
    elif any(x in t for x in ("parçalı", "az bulut", "partly")):
        gunes(B * .62, B * .36, B * .14)
        bulut(B * .45, B * .58, B * .72)
    else:
        bulut(B / 2, B / 2, B * .85)
    im = im.resize((boyut, boyut), Image.LANCZOS)
    return neon(im, renk, max(2, boyut * .05), .6)


# ----------------------------------------------------------------------------
# Bilgi paneli (saat, hava, sistem)
# ----------------------------------------------------------------------------

def bilgi_paneli(olcek, renk, hava=None, istat=None, bilgi=None, simdi=None):
    s = olcek
    istat = istat or {}
    bilgi = bilgi or {}
    simdi = simdi or datetime.datetime.now()
    G = int(330 * s)
    pad = int(22 * s)
    satir_sis = [st for st in (("CPU", istat.get("cpu")), ("RAM", istat.get("ram")), ("PİL", istat.get("bat")))
                 if st[1] is not None]
    Y = int((206 + (118 if hava else 0) + 26 * len(satir_sis) + 34) * s)
    im = cam_panel(G, Y, renk, s)
    d = ImageDraw.Draw(im)

    # saat
    f_saat = font("ince", 64 * s)
    f_sn = font("baslik", 20 * s)
    saat = simdi.strftime("%H:%M")
    y = int(14 * s)
    yazi = Image.new("L", im.size, 0)
    ImageDraw.Draw(yazi).text((pad, y), saat, font=f_saat, fill=255)
    im.alpha_composite(neon(yazi, renk, 5 * s, .55))
    sx = pad + f_saat.getlength(saat) + 8 * s
    d.text((sx, y + int(18 * s)), simdi.strftime("%S"), font=f_sn, fill=renk + (230,))
    # tarih
    f_tarih = font("baslik", 13 * s)
    y += int(84 * s)
    metin_aralikli(d, (pad, y), f"{GUN[simdi.weekday()]}  ·  {simdi.day} {AY[simdi.month - 1]} {simdi.year}",
                   f_tarih, YAZI + (235,), 1.6 * s)
    # ayraç
    y += int(32 * s)
    ayrac(d, pad, y, G - pad, renk, s)
    y += int(18 * s)

    if hava:
        ik = int(64 * s)
        im.alpha_composite(hava_ikonu(hava.get("desc"), ik, renk), (pad - int(4 * s), y))
        f_der = font("ince", 50 * s)
        tx = pad + ik + int(14 * s)
        d.text((tx, y - int(4 * s)), f"{hava.get('temp', '--')}°", font=f_der, fill=YAZI + (255,))
        d.text((tx + f_der.getlength(f"{hava.get('temp', '--')}°") + 6 * s, y + int(10 * s)), "C",
               font=font("baslik", 18 * s), fill=renk + (255,))
        f_desc = font("kalin", 16 * s)
        d.text((pad, y + int(72 * s)), hava.get("desc", ""), font=f_desc, fill=YAZI + (255,))
        alt = []
        if hava.get("yer"):
            alt.append(hava["yer"].upper())
        if hava.get("hiss") is not None:
            alt.append(f"HİSSEDİLEN {hava['hiss']}°")
        metin_aralikli(d, (pad, y + int(96 * s)), "  ·  ".join(alt), font("baslik", 11.5 * s), SOLUK + (255,), 1.2 * s)
        y += int(124 * s)
        ayrac(d, pad, y, G - pad, renk, s)
        y += int(18 * s)

    f_et = font("baslik", 11.5 * s)
    for ad, deger in satir_sis:
        metin_aralikli(d, (pad, y), ad, f_et, SOLUK + (255,), 1.5 * s)
        d.text((G - pad, y - int(1 * s)), f"%{round(deger)}", font=font("kalin", 13 * s), fill=YAZI + (255,), anchor="ra")
        bx1, bx2, by = pad + int(46 * s), G - pad - int(48 * s), y + int(8 * s)
        d.rounded_rectangle([bx1, by - 2 * s, bx2, by + 2 * s], radius=int(2 * s), fill=renk + (40,))
        dolu = bx1 + (bx2 - bx1) * max(0, min(100, deger)) / 100
        cubuk = Image.new("L", im.size, 0)
        ImageDraw.Draw(cubuk).rounded_rectangle([bx1, by - 2 * s, dolu, by + 2 * s], radius=int(2 * s), fill=255)
        im.alpha_composite(neon(cubuk, renk if deger < 85 else (255, 120, 90), 3 * s, .6))
        y += int(26 * s)

    alt = "J.A.R.V.I.S."
    if bilgi.get("beyin"):
        alt += "   ·   " + bilgi["beyin"].upper()
    metin_aralikli(d, (pad, Y - int(28 * s)), alt, font("baslik", 10.5 * s), renk + (200,), 1.8 * s)
    return im


def ayrac(d, x1, y, x2, renk, s):
    d.line([x1, y, x2, y], fill=renk + (60,), width=max(1, int(s)))
    d.line([x1, y, x1 + 40 * s, y], fill=renk + (220,), width=max(1, int(2 * s)))
    m = 4 * s
    d.polygon([(x2 - m, y), (x2, y - m), (x2 + m, y), (x2, y + m)], fill=renk + (220,))


# ----------------------------------------------------------------------------
# Mesaj kartları
# ----------------------------------------------------------------------------

def mesaj_kartlari(olcek, renk, mesajlar, simdi_ts, genislik=440, en_yuk=560):
    """mesajlar: [(kim, metin, zaman_ts)] eskiden yeniye. Alttan üste dizilir."""
    s = olcek
    G = int(genislik * s)
    H = int(en_yuk * s)
    im = Image.new("RGBA", (G, H), (0, 0, 0, 0))
    f = font("normal", 15.5 * s)
    f_ad = font("baslik", 11 * s)
    pad = int(16 * s)
    y = H
    for kim, metin, ts in reversed(mesajlar):
        yas = simdi_ts - ts
        if yas > 30:
            continue
        sondur = 1.0 if yas < 20 else max(0.0, 1 - (yas - 20) / 10)
        satirlar = sar(metin, f, G - pad * 2 - int(10 * s))
        satir_h = int(f.size * 1.32)
        kart_h = pad + int(20 * s) + satir_h * len(satirlar) + int(pad * .8)
        if y - kart_h < 0:
            break
        y -= kart_h
        vurgu = renk if kim == "jarvis" else (150, 170, 180)
        kart = cam_panel(G, kart_h, vurgu, s, alfa=215 if kim == "jarvis" else 195, kose=int(10 * s))
        kd = ImageDraw.Draw(kart)
        # sol vurgu çizgisi
        cizgi = Image.new("L", kart.size, 0)
        ImageDraw.Draw(cizgi).line([int(3 * s), int(10 * s), int(3 * s), kart_h - int(10 * s)], fill=255, width=max(2, int(3 * s)))
        kart.alpha_composite(neon(cizgi, vurgu, 3 * s, .6))
        zaman = datetime.datetime.fromtimestamp(ts).strftime("%H:%M")
        metin_aralikli(kd, (pad + int(4 * s), pad - int(4 * s)), "JARVIS" if kim == "jarvis" else "SEN",
                       f_ad, vurgu + (255,), 2.2 * s)
        kd.text((G - pad, pad - int(4 * s)), zaman, font=font("normal", 11 * s), fill=SOLUK + (255,), anchor="ra")
        yy = pad + int(20 * s)
        for satir in satirlar:
            kd.text((pad + int(4 * s), yy), satir, font=f, fill=YAZI + (255,) if kim == "jarvis" else (205, 220, 228, 255))
            yy += satir_h
        if sondur < 1:
            a = kart.getchannel("A").point(lambda v: int(v * sondur))
            kart.putalpha(a)
        im.alpha_composite(kart, (0, y))
        y -= int(10 * s)
    return im
