# -*- coding: utf-8 -*-
"""
Jarvis için şeffaf masaüstü katmanı (Windows).

Ekranın tamamını kaplayan, her zaman üstte duran, arka planı tamamen görünen bir pencere.
Sadece çizilen öğeler (reaktör, saat, yazılar) görünür; boş yerlere yapılan tıklamalar
alttaki pencerelere geçer. Reaktöre sol tık = dinle, sağ tık = menü, sürükle = taşı.
"""

import math
import time
import queue
import datetime
import tkinter as tk

ANAHTAR = "#010203"  # bu renk tamamen şeffaf olur
ZEMIN = "#07141c"    # yazıların arkasındaki koyu panel

RENK = {
    "baslatiliyor": "#2fd8ff",
    "bekliyor": "#2fd8ff",
    "dinliyor": "#6ff4ff",
    "dusunuyor": "#ffb23e",
    "konusuyor": "#9ff2ff",
    "hata": "#ff4d5e",
}
HIZ = {"baslatiliyor": 3, "bekliyor": 1, "dinliyor": 2.2, "dusunuyor": 5, "konusuyor": 1.6, "hata": .5}
ETIKET = {
    "baslatiliyor": "BAŞLATILIYOR",
    "bekliyor": "ÇEVRİMİÇİ",
    "dinliyor": "DİNLİYORUM",
    "dusunuyor": "İŞLENİYOR",
    "konusuyor": "YANITLIYOR",
    "hata": "UYARI",
}
GUN = ["PAZARTESİ", "SALI", "ÇARŞAMBA", "PERŞEMBE", "CUMA", "CUMARTESİ", "PAZAR"]
AY = ["OCAK", "ŞUBAT", "MART", "NİSAN", "MAYIS", "HAZİRAN", "TEMMUZ", "AĞUSTOS", "EYLÜL", "EKİM", "KASIM", "ARALIK"]


def karistir(renk, oran, hedef=(8, 14, 20)):
    """Rengi koyu bir tona doğru karıştırır (yarı saydamlık taklidi)."""
    r, g, b = int(renk[1:3], 16), int(renk[3:5], 16), int(renk[5:7], 16)
    r = int(r * oran + hedef[0] * (1 - oran))
    g = int(g * oran + hedef[1] * (1 - oran))
    b = int(b * oran + hedef[2] * (1 - oran))
    return f"#{r:02x}{g:02x}{b:02x}"


class SeffafEkran:
    def __init__(self, konum="sag-alt", yazi_tipi="Bahnschrift", saydamlik=0.92):
        self.kuyruk = queue.Queue()
        self.saydamlik = saydamlik
        self.konum = konum
        self.font_adi = yazi_tipi
        self.durum_adi = "baslatiliyor"
        self.ipucu = "Sistemler yükleniyor…"
        self.seviye_hedef = 0.0
        self.seviye_su_an = 0.0
        self.mesajlar = []          # [(kim, metin, zaman)]
        self.hava = None
        self.istat = {}
        self.bilgi = {}
        self.aci = 0.0
        self.gizli_bilgi = False
        self.on_komut = None
        self.on_dinle = None
        self.on_kapat = None
        self.on_hazir = None
        self.aktif = True

    # ---------------- diğer thread'lerden çağrılan fonksiyonlar ----------------
    def durum(self, ad, ipucu=None):
        self.durum_adi = ad
        self.kuyruk.put(("durum", ad, ipucu))

    def mesaj(self, kim, metin):
        self.kuyruk.put(("mesaj", kim, metin))

    def seviye(self, deger):
        self.seviye_hedef = max(0.0, min(1.0, float(deger)))

    def veri(self, fonk, sozluk):
        self.kuyruk.put(("veri", fonk, sozluk))

    def kapat(self):
        self.kuyruk.put(("kapat", None, None))

    # ---------------- kurulum ----------------
    def calistir(self):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self.kok = kok = tk.Tk()
        kok.title("J.A.R.V.I.S.")
        kok.overrideredirect(True)
        kok.attributes("-topmost", True)
        kok.configure(bg=ANAHTAR)
        try:
            kok.attributes("-transparentcolor", ANAHTAR)
            kok.attributes("-alpha", self.saydamlik)
        except tk.TclError:
            pass

        self.W, self.H = kok.winfo_screenwidth(), kok.winfo_screenheight()
        kok.geometry(f"{self.W}x{self.H}+0+0")
        self.s = s = max(1.0, kok.winfo_fpixels("1i") / 96.0)

        self.tuval = c = tk.Canvas(kok, bg=ANAHTAR, highlightthickness=0, width=self.W, height=self.H)
        c.pack(fill="both", expand=True)

        self.f_saat = (self.font_adi, int(34 * 1), "bold")
        self.f_buyuk = (self.font_adi, 12, "bold")
        self.f_orta = (self.font_adi, 11)
        self.f_kucuk = (self.font_adi, 9)
        self.f_mesaj = (self.font_adi, 12)

        # reaktör merkezi
        R = self.R = int(105 * s)
        alt_bosluk = int(80 * s)  # görev çubuğu için
        if self.konum == "sol-alt":
            self.cx, self.cy = int(40 * s) + R + int(30 * s), self.H - alt_bosluk - R - int(40 * s)
        elif self.konum == "orta":
            self.cx, self.cy = self.W // 2, self.H // 2
        else:
            self.cx, self.cy = self.W - int(40 * s) - R - int(30 * s), self.H - alt_bosluk - R - int(40 * s)

        self._reaktor_ciz()
        self._bilgi_ciz()
        self.mesaj_ogeleri = []

        # Tıklamalar (sadece reaktör alanı)
        c.tag_bind("reaktor", "<ButtonPress-1>", self._bas)
        c.tag_bind("reaktor", "<B1-Motion>", self._surukle)
        c.tag_bind("reaktor", "<ButtonRelease-1>", self._birak)
        c.tag_bind("reaktor", "<Button-3>", self._menu_ac)
        c.tag_bind("reaktor", "<Enter>", lambda e: c.configure(cursor="hand2"))
        c.tag_bind("reaktor", "<Leave>", lambda e: c.configure(cursor=""))

        self.menu = tk.Menu(kok, tearoff=0, bg="#08131b", fg="#cdf6ff", activebackground="#0f3b4d",
                            activeforeground="#ffffff", bd=0, font=self.f_orta)
        self.menu.add_command(label="Dinle", command=self._dinle)
        self.menu.add_command(label="Komut yaz...", command=self._yazi_kutusu)
        self.menu.add_command(label="Saat / hava panelini gizle-göster", command=self._bilgi_gizle_goster)
        self.menu.add_separator()
        self.menu.add_command(label="Jarvis'i kapat", command=self._kapat_tik)

        self.son_kare = time.time()
        self._surukleme = (0, 0, False)
        self.sayac = 0
        kok.after(30, self._dongu)
        kok.after(3000, self._ustte_tut)
        if self.on_hazir:
            kok.after(100, self.on_hazir)
        kok.mainloop()

    # ---------------- çizim ----------------
    def _reaktor_ciz(self):
        c, cx, cy, R, s = self.tuval, self.cx, self.cy, self.R, self.s
        renk = RENK["baslatiliyor"]
        self.r_ogeler = {}
        # Tıklama alanı: anahtar renginden 1 ton farklı, neredeyse görünmez dolgu
        self.r_ogeler["alan"] = c.create_oval(cx - R, cy - R, cx + R, cy + R, fill="#020407", outline="",
                                              tags=("reaktor",))
        # dış tikler
        self.tikler = []
        for i in range(72):
            uzun = i % 6 == 0
            l = c.create_line(0, 0, 1, 1, fill=renk, width=max(1, int((2 if uzun else 1) * s)), tags=("reaktor", "renkli"))
            self.tikler.append((l, uzun))
        # dış ince çember
        self.r_ogeler["cember1"] = c.create_oval(cx - R * .93, cy - R * .93, cx + R * .93, cy + R * .93,
                                                 outline=karistir(renk, .45), width=1, tags=("reaktor",))
        # dönen yaylar (halka 2)
        self.yaylar2 = []
        for bas, uz in [(0, 70), (85, 25), (125, 95), (235, 40), (290, 55)]:
            a = c.create_arc(cx - R * .84, cy - R * .84, cx + R * .84, cy + R * .84, start=bas, extent=uz,
                             style="arc", outline=renk, width=max(2, int(5 * s)), tags=("reaktor",))
            self.yaylar2.append((a, bas))
        # ince ters dönen yaylar (halka 3)
        self.yaylar3 = []
        for bas, uz in [(10, 120), (150, 60), (230, 100)]:
            a = c.create_arc(cx - R * .72, cy - R * .72, cx + R * .72, cy + R * .72, start=bas, extent=uz,
                             style="arc", outline=karistir(renk, .8), width=max(1, int(2 * s)), tags=("reaktor", "renkli2"))
            self.yaylar3.append((a, bas))
        # 10 bobin segmenti
        self.bobinler = []
        for i in range(10):
            a = c.create_arc(cx - R * .56, cy - R * .56, cx + R * .56, cy + R * .56, start=i * 36, extent=27,
                             style="arc", outline=karistir(renk, .7), width=max(6, int(15 * s)), tags=("reaktor", "bobin"))
            self.bobinler.append((a, i * 36))
        self.r_ogeler["cember2"] = c.create_oval(cx - R * .42, cy - R * .42, cx + R * .42, cy + R * .42,
                                                 outline=renk, width=max(1, int(2 * s)), tags=("reaktor",))
        # çekirdek (iç içe dolu daireler = parlama)
        self.cekirdek = []
        for oran, parlak in [(.36, .25), (.29, .5), (.22, .8), (.12, 1.0)]:
            o = c.create_oval(cx, cy, cx, cy, fill=karistir(renk, parlak), outline="", tags=("reaktor",))
            self.cekirdek.append((o, oran, parlak))
        self.merkez = c.create_oval(cx, cy, cx, cy, fill="#ffffff", outline="", tags=("reaktor",))
        # üçgen
        r3 = R * .32
        noktalar = []
        for k in range(3):
            aci = math.radians(-90 + k * 120)
            noktalar += [cx + r3 * math.cos(aci), cy + r3 * math.sin(aci)]
        self.ucgen = c.create_polygon(*noktalar, outline=renk, fill="", width=max(1, int(2 * s)), tags=("reaktor",))
        # durum yazısı + ipucu
        self.durum_yazi = c.create_text(cx, cy + R + int(22 * s), text=ETIKET["baslatiliyor"], fill=renk,
                                        font=(self.font_adi, 12, "bold"), tags=("renkli_yazi", "etiket"))
        self.ipucu_yazi = c.create_text(cx, cy + R + int(42 * s), text=self.ipucu, fill="#b8d6df",
                                        font=self.f_kucuk, tags=("etiket",))
        self.etiket_zemin = c.create_rectangle(0, 0, 1, 1, fill=ZEMIN, outline="", tags=("etiket",))
        c.tag_lower(self.etiket_zemin, self.durum_yazi)
        self._etiket_zemin_guncelle()

    def _bilgi_ciz(self):
        c, s = self.tuval, self.s
        x, y = self.W - int(36 * s), int(28 * s)
        renk = RENK["bekliyor"]
        self.b_saat = c.create_text(x, y, text="--:--", anchor="ne", fill=renk, font=(self.font_adi, 34, "bold"),
                                    tags=("bilgi", "renkli_yazi"))
        self.b_tarih = c.create_text(x, y + int(56 * s), text="", anchor="ne", fill="#cdf6ff", font=self.f_orta, tags=("bilgi",))
        self.b_cizgi = c.create_line(x - int(230 * s), y + int(80 * s), x, y + int(80 * s), fill=karistir(renk, .6),
                                     tags=("bilgi", "soluk"))
        self.b_hava = c.create_text(x, y + int(94 * s), text="", anchor="ne", fill="#ffffff",
                                    font=(self.font_adi, 20, "bold"), tags=("bilgi",))
        self.b_hava2 = c.create_text(x, y + int(128 * s), text="", anchor="ne", fill="#cdf6ff", font=self.f_orta, tags=("bilgi",))
        self.b_sistem = c.create_text(x, y + int(154 * s), text="", anchor="ne", fill="#9fc3cf", font=self.f_kucuk, tags=("bilgi",))
        self.b_jarvis = c.create_text(x, y + int(174 * s), text="J.A.R.V.I.S.", anchor="ne", fill=renk,
                                      font=(self.font_adi, 9, "bold"), tags=("bilgi", "renkli_yazi"))
        self.b_zemin = c.create_rectangle(0, 0, 1, 1, fill=ZEMIN, outline=karistir(renk, .35), tags=("bilgi", "cerceve"))
        c.tag_lower(self.b_zemin, self.b_saat)

    def _mesajlari_ciz(self):
        c, s = self.tuval, self.s
        for o in self.mesaj_ogeleri:
            c.delete(o)
        self.mesaj_ogeleri = []
        simdi = time.time()
        self.mesajlar = [m for m in self.mesajlar if simdi - m[2] < 30][-4:]
        genislik = int(420 * s)
        sag = self.cx + self.R if self.konum != "sol-alt" else self.cx - self.R + genislik
        anchor = "se" if self.konum != "sol-alt" else "se"
        y = self.cy - self.R - int(24 * s)
        renk = RENK.get(self.durum_adi, RENK["bekliyor"])
        for kim, metin, t in reversed(self.mesajlar):
            yas = simdi - t
            if kim == "jarvis":
                r = renk if yas < 15 else karistir(renk, .55)
                metin_r = "#ffffff" if yas < 15 else "#9fb3bd"
            else:
                r = "#9fb3bd" if yas < 15 else "#5f7681"
                metin_r = "#e6eef2" if yas < 15 else "#7f939c"
            govde = c.create_text(sag, y, text=metin, anchor=anchor, width=genislik, justify="right",
                                  fill=metin_r, font=self.f_mesaj)
            x1, y1, x2, y2 = c.bbox(govde)
            ad = c.create_text(sag, y1 - int(4 * s), text=("JARVIS" if kim == "jarvis" else "SEN"), anchor="se",
                               fill=r, font=(self.font_adi, 8, "bold"))
            p = int(10 * s)
            zemin = c.create_rectangle(x1 - p, y1 - int(20 * s), sag + int(14 * s), y2 + p // 2,
                                       fill=ZEMIN, outline="")
            c.tag_lower(zemin, govde)
            cizgi = c.create_line(sag + int(8 * s), y1 - int(14 * s), sag + int(8 * s), y2, fill=r, width=max(2, int(2 * s)))
            self.mesaj_ogeleri += [zemin, govde, ad, cizgi]
            y = y1 - int(34 * s)
            if y < int(240 * s):
                break

    def _etiket_zemin_guncelle(self):
        ogeler = [self.durum_yazi] + ([self.ipucu_yazi] if self.tuval.itemcget(self.ipucu_yazi, "text") else [])
        x1, y1, x2, y2 = self._kutu(ogeler)
        p = int(10 * self.s)
        self.tuval.coords(self.etiket_zemin, x1 - p, y1 - p // 2, x2 + p, y2 + p // 2)

    def _kutu(self, ogeler):
        kutular = [self.tuval.bbox(o) for o in ogeler]
        kutular = [k for k in kutular if k]
        return (min(k[0] for k in kutular), min(k[1] for k in kutular),
                max(k[2] for k in kutular), max(k[3] for k in kutular))

    # ---------------- animasyon döngüsü ----------------
    def _dongu(self):
        try:
            self._kuyrugu_isle()
            self._animasyon()
            self.sayac += 1
            if self.sayac % 15 == 0:
                self._saati_guncelle()
            if self.sayac % 60 == 0 and self.mesajlar:
                self._mesajlari_ciz()
        except Exception as e:
            print("Ekran hatası:", e)
        self.kok.after(33, self._dongu)

    def _kuyrugu_isle(self):
        while True:
            try:
                tur, a, b = self.kuyruk.get_nowait()
            except queue.Empty:
                break
            if tur == "durum":
                self._durum_uygula(a, b)
            elif tur == "mesaj":
                if a in ("jarvis", "sen"):
                    self.mesajlar.append((a, b, time.time()))
                    self._mesajlari_ciz()
            elif tur == "veri":
                if a == "setWeather":
                    self.hava = b
                elif a == "setStats":
                    self.istat = b
                elif a == "setInfo":
                    self.bilgi.update(b)
                self._saati_guncelle()
            elif tur == "kapat":
                self.kok.destroy()
                return

    def _durum_uygula(self, ad, ipucu):
        c = self.tuval
        renk = RENK.get(ad, RENK["bekliyor"])
        c.itemconfigure("renkli", fill=renk)
        for oge, _ in self.yaylar2:
            c.itemconfigure(oge, outline=renk)
        for oge, _ in self.yaylar3:
            c.itemconfigure(oge, outline=karistir(renk, .8))
        for oge, _ in self.bobinler:
            c.itemconfigure(oge, outline=karistir(renk, .7))
        c.itemconfigure(self.r_ogeler["cember2"], outline=renk)
        c.itemconfigure(self.r_ogeler["cember1"], outline=karistir(renk, .45))
        c.itemconfigure(self.ucgen, outline=renk)
        c.itemconfigure("renkli_yazi", fill=renk)
        c.itemconfigure("soluk", fill=karistir(renk, .6))
        c.itemconfigure("cerceve", outline=karistir(renk, .35))
        for o, oran, parlak in self.cekirdek:
            c.itemconfigure(o, fill=karistir(renk, parlak))
        c.itemconfigure(self.durum_yazi, text=ETIKET.get(ad, ad.upper()))
        varsayilan = {"bekliyor": "“Hey Jarvis” de · reaktöre tıkla", "dinliyor": "Seni dinliyorum…",
                      "dusunuyor": "Bir saniye…"}.get(ad, "")
        c.itemconfigure(self.ipucu_yazi, text=ipucu if ipucu is not None else varsayilan)
        self._etiket_zemin_guncelle()
        if self.mesajlar:
            self._mesajlari_ciz()

    def _animasyon(self):
        c, cx, cy, R = self.tuval, self.cx, self.cy, self.R
        simdi = time.time()
        dt = simdi - self.son_kare
        self.son_kare = simdi
        ad = self.durum_adi
        self.aci = (self.aci + dt * 12 * HIZ.get(ad, 1)) % 360

        # seviye
        hedef = self.seviye_hedef
        t = simdi * 1000
        if ad == "konusuyor":
            hedef = .35 + .45 * abs(math.sin(t / 140)) * (.6 + .4 * math.sin(t / 53))
        elif ad == "dusunuyor":
            hedef = .2 + .12 * math.sin(t / 120)
        elif ad in ("bekliyor", "baslatiliyor"):
            hedef = max(hedef * .4, .06 + .05 * math.sin(t / 700))
        self.seviye_su_an += (hedef - self.seviye_su_an) * .3
        lv = self.seviye_su_an

        # tikler
        for i, (l, uzun) in enumerate(self.tikler):
            a = math.radians(i * 5 + self.aci)
            r1, r2 = R, R * (.88 if uzun else .94)
            c.coords(l, cx + r1 * math.cos(a), cy + r1 * math.sin(a), cx + r2 * math.cos(a), cy + r2 * math.sin(a))
        for oge, bas in self.yaylar2:
            c.itemconfigure(oge, start=(bas - self.aci * 1.6) % 360)
        for oge, bas in self.yaylar3:
            c.itemconfigure(oge, start=(bas + self.aci * 2.6) % 360)
        for oge, bas in self.bobinler:
            c.itemconfigure(oge, start=(bas + self.aci * .7) % 360)
        # çekirdek
        for o, oran, _ in self.cekirdek:
            r = R * oran * (1 + lv * .45)
            c.coords(o, cx - r, cy - r, cx + r, cy + r)
        r = R * .06 * (1 + lv * .8)
        c.coords(self.merkez, cx - r, cy - r, cx + r, cy + r)

    def _saati_guncelle(self):
        c = self.tuval
        d = datetime.datetime.now()
        c.itemconfigure(self.b_saat, text=d.strftime("%H:%M"))
        c.itemconfigure(self.b_tarih, text=f"{GUN[d.weekday()]} · {d.day} {AY[d.month - 1]} {d.year}")
        if self.hava:
            h = self.hava
            c.itemconfigure(self.b_hava, text=f"{h.get('temp', '--')}°C  {h.get('desc', '')}")
            ek = f"Hissedilen {h['hiss']}°" if h.get("hiss") is not None else ""
            if h.get("yer"):
                ek = (h["yer"].upper() + "  ·  " + ek) if ek else h["yer"].upper()
            c.itemconfigure(self.b_hava2, text=ek)
        st = self.istat
        parcalar = []
        if st.get("cpu") is not None:
            parcalar.append(f"CPU %{round(st['cpu'])}")
        if st.get("ram") is not None:
            parcalar.append(f"RAM %{round(st['ram'])}")
        if st.get("bat") is not None:
            parcalar.append(f"PİL %{st['bat']}" + (" şarjda" if st.get("sarj") else ""))
        c.itemconfigure(self.b_sistem, text="   ".join(parcalar))
        b = self.bilgi
        alt = "J.A.R.V.I.S."
        if b.get("beyin"):
            alt += "  ·  " + b["beyin"].upper()
        c.itemconfigure(self.b_jarvis, text=alt)
        x1, y1, x2, y2 = self._kutu([self.b_saat, self.b_tarih, self.b_hava, self.b_hava2, self.b_sistem, self.b_jarvis])
        p = int(16 * self.s)
        x1 = min(x1, x2 - int(250 * self.s))
        c.coords(self.b_zemin, x1 - p, y1 - p // 2, x2 + p, y2 + p // 2)

    def _ustte_tut(self):
        try:
            self.kok.attributes("-topmost", True)
            self.kok.lift()
        except Exception:
            pass
        self.kok.after(3000, self._ustte_tut)

    # ---------------- etkileşim ----------------
    def _bas(self, e):
        self._surukleme = (e.x, e.y, False)

    def _surukle(self, e):
        x0, y0, _ = self._surukleme
        dx, dy = e.x - x0, e.y - y0
        if abs(dx) + abs(dy) < 4 and not self._surukleme[2]:
            return
        self.tuval.move("reaktor", dx, dy)
        self.tuval.move("etiket", dx, dy)
        self.cx += dx
        self.cy += dy
        self._surukleme = (e.x, e.y, True)

    def _birak(self, e):
        tasindi = getattr(self, "_surukleme", (0, 0, False))[2]
        if tasindi:
            self.konum = "sol-alt" if self.cx < self.W / 2 else "sag-alt"
            self._mesajlari_ciz()
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

    def _bilgi_gizle_goster(self):
        self.gizli_bilgi = not self.gizli_bilgi
        self.tuval.itemconfigure("bilgi", state="hidden" if self.gizli_bilgi else "normal")

    def _kapat_tik(self):
        if self.on_kapat:
            self.on_kapat()
        else:
            self.kok.destroy()

    def _yazi_kutusu(self):
        s = self.s
        renk = RENK["bekliyor"]
        k = tk.Toplevel(self.kok)
        k.overrideredirect(True)
        k.attributes("-topmost", True)
        k.configure(bg=renk)
        gen, yuk = int(460 * s), int(46 * s)
        x = max(10, min(self.W - gen - 10, self.cx - gen // 2))
        y = max(10, self.cy - self.R - yuk - int(20 * s))
        k.geometry(f"{gen}x{yuk}+{x}+{y}")
        ic = tk.Frame(k, bg="#06121a")
        ic.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(ic, text=" >_", bg="#06121a", fg=renk, font=(self.font_adi, 12, "bold")).pack(side="left")
        g = tk.Entry(ic, bg="#06121a", fg="#e6faff", insertbackground=renk, relief="flat", font=(self.font_adi, 13))
        g.pack(side="left", fill="both", expand=True, padx=(4, 10))

        def gonder(_=None):
            metin = g.get().strip()
            k.destroy()
            if metin and self.on_komut:
                self.on_komut(metin)

        g.bind("<Return>", gonder)
        g.bind("<Escape>", lambda _: k.destroy())
        g.bind("<FocusOut>", lambda _: k.after(150, lambda: k.winfo_exists() and k.destroy()))
        k.after(50, lambda: (k.focus_force(), g.focus_set()))
