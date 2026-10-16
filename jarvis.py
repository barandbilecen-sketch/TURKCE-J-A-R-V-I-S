# -*- coding: utf-8 -*-
"""
JARVIS - Türkçe sesli asistan (Windows)

"Hey Jarvis" de, bip sesinden sonra komutunu söyle.
Yazarak denemek için:  python jarvis.py --yazi
"""

import os
import re
import sys
import time
import queue
import random
import tempfile
import threading
import datetime
import subprocess
import webbrowser
import urllib.parse

KLASOR = os.path.dirname(os.path.abspath(__file__))

# ----------------------------------------------------------------------------
# Ayarlar (ayarlar.txt)
# ----------------------------------------------------------------------------

def ayarlari_oku():
    ayar = {
        "ANTHROPIC_API_KEY": "",
        "MODEL": "claude-haiku-5-5",
        "SES": "tr-TR-AhmetNeural",
        "HITAP": "efendim",
        "UYANMA_YONTEMI": "otomatik",   # otomatik | model | kelime
        "UYANMA_HASSASIYETI": "0.5",
        "MIKROFON": "",
    }
    yol = os.path.join(KLASOR, "ayarlar.txt")
    if os.path.exists(yol):
        with open(yol, encoding="utf-8-sig") as f:
            for satir in f:
                satir = satir.strip()
                if not satir or satir.startswith("#") or "=" not in satir:
                    continue
                k, v = satir.split("=", 1)
                ayar[k.strip().upper()] = v.strip().strip('"').strip("'")
    if os.environ.get("ANTHROPIC_API_KEY") and not ayar["ANTHROPIC_API_KEY"]:
        ayar["ANTHROPIC_API_KEY"] = os.environ["ANTHROPIC_API_KEY"]
    return ayar


AYAR = ayarlari_oku()
HITAP = AYAR["HITAP"]
EKRANI_GOR = AYAR.get("EKRANI_GOR", "evet").lower() in ("evet", "1", "true")
BILGISAYAR_KONTROL = sys.platform == "win32" and AYAR.get("BILGISAYAR_KONTROL", "evet").lower() in ("evet", "1", "true")
try:
    import bilgisayar
except Exception:
    bilgisayar = None
    BILGISAYAR_KONTROL = False


def log(*a):
    print(datetime.datetime.now().strftime("[%H:%M:%S]"), *a, flush=True)


# ----------------------------------------------------------------------------
# Konuşma (Türkçe ses)
# ----------------------------------------------------------------------------

_ses_kilidi = threading.Lock()
_pygame_hazir = False


def _pygame_baslat():
    global _pygame_hazir
    if not _pygame_hazir:
        os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
        import pygame
        pygame.mixer.init()
        _pygame_hazir = True


def _mp3_cal(yol):
    import pygame
    _pygame_baslat()
    pygame.mixer.music.load(yol)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        time.sleep(0.05)
    pygame.mixer.music.unload()


class Ekran:
    """Iron Man tarzı HUD penceresi ile konuşur. Pencere yoksa hiçbir şey yapmaz."""

    def __init__(self):
        self.pencere = None
        self.durum_adi = "baslatiliyor"

    @property
    def aktif(self):
        return self.pencere is not None

    def _js(self, kod):
        if self.pencere is None:
            return
        try:
            self.pencere.evaluate_js(kod)
        except Exception:
            pass

    def durum(self, ad, ipucu=None):
        self.durum_adi = ad
        import json
        self._js(f"setState({json.dumps(ad)}{', ' + json.dumps(ipucu) if ipucu is not None else ''})")

    def mesaj(self, kim, metin):
        import json
        self._js(f"addMsg({json.dumps(kim)}, {json.dumps(metin)})")

    def seviye(self, deger):
        self._js(f"setLevel({deger:.3f})")

    def veri(self, fonk, sozluk):
        import json
        self._js(f"{fonk}({json.dumps(sozluk, ensure_ascii=False)})")


EKRAN = Ekran()


def konus(metin):
    """Metni sesli söyler (önce Edge sesi, olmazsa Windows sesi)."""
    if not metin:
        return
    print(f"JARVIS: {metin}", flush=True)
    if YAZI_MODU:
        return
    onceki = EKRAN.durum_adi
    EKRAN.durum("konusuyor")
    EKRAN.mesaj("jarvis", metin)
    try:
        _konus_ses(metin)
    finally:
        EKRAN.durum("bekliyor" if onceki in ("konusuyor", "dusunuyor", "baslatiliyor") else onceki)


# Denenecek erkek sesleri (ilki ayarlardaki ses). Microsoft bazen tek tek sesleri engelliyor;
# biri çalışmazsa sıradakine geçilir. "Multilingual" sesler Türkçe metni Türkçe okur.
YEDEK_SESLER = [
    "tr-TR-AhmetNeural",
    "en-US-AndrewMultilingualNeural",
    "en-US-BrianMultilingualNeural",
    "fr-FR-RemyMultilingualNeural",
    "de-DE-FlorianMultilingualNeural",
]
_calisan_ses = None
_bozuk_sesler = set()
_windows_ses_yok = False


def _edge_sesi(metin, ses, dosya):
    import asyncio
    import edge_tts

    async def _uret():
        await asyncio.wait_for(edge_tts.Communicate(metin, ses).save(dosya), timeout=12)

    asyncio.run(_uret())
    if not os.path.exists(dosya) or os.path.getsize(dosya) < 500:
        raise RuntimeError("boş ses dosyası")


_PS_WINDOWS_SES = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Bekle($op, $tip) { $t = $asTask.MakeGenericMethod($tip).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[void][Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
[void][Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]
$metin = [IO.File]::ReadAllText($args[0], [Text.Encoding]::UTF8)
$s = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
$v = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices | Where-Object { $_.Language -like 'tr*' } | Sort-Object { [string]$_.Gender -ne 'Male' } | Select-Object -First 1
if (-not $v) { exit 3 }
$s.Voice = $v
$akis = Bekle ($s.SynthesizeTextToStreamAsync($metin)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
$okuyucu = New-Object Windows.Storage.Streams.DataReader($akis.GetInputStreamAt(0))
$n = Bekle ($okuyucu.LoadAsync([uint32]$akis.Size)) ([uint32])
$b = New-Object byte[] $n
$okuyucu.ReadBytes($b)
[IO.File]::WriteAllBytes($args[1], $b)
"""


def _windows_turkce_ses(metin):
    """Windows'un yerleşik Türkçe sesiyle (Tolga) okur. Başarılıysa True."""
    global _windows_ses_yok
    if _windows_ses_yok or sys.platform != "win32":
        return False
    tmp = tempfile.gettempdir()
    ps = os.path.join(tmp, "jarvis_ses.ps1")
    txt = os.path.join(tmp, f"jarvis_{os.getpid()}.txt")
    wav = os.path.join(tmp, f"jarvis_{os.getpid()}.wav")
    with open(ps, "w", encoding="utf-8-sig") as f:
        f.write(_PS_WINDOWS_SES)
    with open(txt, "w", encoding="utf-8") as f:
        f.write(metin)
    sonuc = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps, txt, wav],
                           capture_output=True, text=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if sonuc.returncode == 3:
        log("Windows'ta Türkçe ses yüklü değil (Ayarlar > Saat ve dil > Konuşma > Ses ekle > Türkçe).")
        _windows_ses_yok = True
        return False
    if sonuc.returncode != 0 or not os.path.exists(wav):
        log("Windows Türkçe sesi çalışmadı:", (sonuc.stderr or "").strip()[:300])
        _windows_ses_yok = True
        return False
    import winsound
    winsound.PlaySound(wav, winsound.SND_FILENAME)
    return True


# ---------------- Çevrimdışı Türkçe erkek sesi (Piper, "dfki") ----------------
PIPER_MODEL = "tr_TR-dfki-medium"
PIPER_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/"
PIPER_KLASOR = os.path.join(KLASOR, "sesler")
_piper_ses = None
_piper_yok = False


def piper_modeli_indir(sessiz=False):
    """Türkçe erkek ses modelini (yaklaşık 63 MB) bir kere indirir."""
    import urllib.request
    os.makedirs(PIPER_KLASOR, exist_ok=True)
    for uzanti in (".onnx.json", ".onnx"):
        hedef = os.path.join(PIPER_KLASOR, PIPER_MODEL + uzanti)
        if os.path.exists(hedef) and os.path.getsize(hedef) > 1000:
            continue
        if not sessiz:
            log(f"Türkçe ses indiriliyor: {PIPER_MODEL}{uzanti} ...")
        gecici = hedef + ".indiriliyor"
        istek = urllib.request.Request(PIPER_URL + PIPER_MODEL + uzanti + "?download=true",
                                       headers={"User-Agent": "Jarvis"})
        with urllib.request.urlopen(istek, timeout=60) as r, open(gecici, "wb") as f:
            toplam = int(r.headers.get("Content-Length") or 0)
            inen, son = 0, 0
            while True:
                parca = r.read(1 << 16)
                if not parca:
                    break
                f.write(parca)
                inen += len(parca)
                if toplam and not sessiz and inen - son > toplam / 10:
                    son = inen
                    log(f"  %{inen * 100 // toplam}")
        os.replace(gecici, hedef)
    return os.path.join(PIPER_KLASOR, PIPER_MODEL + ".onnx")


def _piper_yukle():
    global _piper_ses, _piper_yok
    if _piper_ses is not None or _piper_yok:
        return _piper_ses
    try:
        from piper import PiperVoice
    except Exception:
        log("Çevrimdışı Türkçe ses paketi (piper-tts) yüklü değil. 'Turkce Ses Kur.bat' dosyasını çalıştır.")
        _piper_yok = True
        return None
    try:
        model = piper_modeli_indir()
        _piper_ses = PiperVoice.load(model)
        log("Çevrimdışı Türkçe erkek sesi hazır.")
        EKRAN.veri("setInfo", {"ses": "Türkçe (çevrimdışı)"})
    except Exception as e:
        log("Çevrimdışı Türkçe ses yüklenemedi:", e)
        _piper_yok = True
    return _piper_ses


def _piper_konus(metin):
    ses = _piper_yukle()
    if ses is None:
        return False
    import wave
    wav = os.path.join(tempfile.gettempdir(), f"jarvis_piper_{os.getpid()}.wav")
    try:
        ayar = None
        try:
            from piper import SynthesisConfig
            hiz = float(AYAR.get("SES_HIZI", "1.0") or 1.0)
            ayar = SynthesisConfig(length_scale=1.0 / max(0.5, min(2.0, hiz)))
        except Exception:
            pass
        with wave.open(wav, "wb") as wf:
            if ayar is not None:
                ses.synthesize_wav(metin, wf, syn_config=ayar)
            else:
                ses.synthesize_wav(metin, wf)
    except TypeError:
        with wave.open(wav, "wb") as wf:
            ses.synthesize_wav(metin, wf)
    if sys.platform == "win32":
        import winsound
        winsound.PlaySound(wav, winsound.SND_FILENAME)
    else:
        _mp3_cal(wav)
    return True


def _konus_ses(metin):
    global _calisan_ses
    metin = metin.replace("·", ",").replace("…", "...").strip()
    motor = (AYAR.get("SES_MOTORU", "otomatik") or "otomatik").lower()
    if motor in ("otomatik", "piper", "cevrimdisi"):
        with _ses_kilidi:
            try:
                if _piper_konus(metin):
                    return
            except Exception as e:
                log("Çevrimdışı ses hatası:", e)
    with _ses_kilidi:
        dosya = os.path.join(tempfile.gettempdir(), f"jarvis_{os.getpid()}.mp3")
        sira = []
        for ses in ([_calisan_ses] if _calisan_ses else []) + [AYAR["SES"]] + YEDEK_SESLER:
            if ses and ses not in sira and ses not in _bozuk_sesler:
                sira.append(ses)
        for ses in sira:
            try:
                if os.path.exists(dosya):
                    os.remove(dosya)
                _edge_sesi(metin, ses, dosya)
                if ses != _calisan_ses:
                    if _calisan_ses or ses != AYAR["SES"]:
                        log(f"Ses: {ses} kullanılıyor.")
                    _calisan_ses = ses
                    EKRAN.veri("setInfo", {"ses": ses.split("-")[2].replace("MultilingualNeural", "").replace("Neural", "")})
                _mp3_cal(dosya)
                return
            except Exception as e:
                log(f"Edge sesi ({ses}) çalışmadı: {e}")
                _bozuk_sesler.add(ses)
                threading.Timer(600, _bozuk_sesler.discard, args=(ses,)).start()  # 10 dk sonra yeniden dene
                if ses == _calisan_ses:
                    _calisan_ses = None
        # Hiçbir Edge sesi olmadı: bir dakika sonra yeniden denemek üzere listeyi temizle
        threading.Timer(60, _bozuk_sesler.clear).start()
        try:
            if _windows_turkce_ses(metin):
                return
        except Exception as e:
            log("Windows sesi hatası:", e)
        log("Türkçe ses bulunamadı, cevap sadece ekranda gösteriliyor.")


def bip(yuksek=True):
    if YAZI_MODU:
        return
    try:
        import winsound
        winsound.Beep(880 if yuksek else 520, 120)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Dinleme (mikrofon + Google ses tanıma)
# ----------------------------------------------------------------------------

ORNEK_HIZI = 16000
PARCA = 1280  # 80 ms


BT_MIKROFON_ISARETLERI = ("airpods", "hands-free", "handsfree", "headset", "bluetooth", "bt ", "kulaklık",
                          "buds", "jabra", "bose", "sony wh", "sony wf")
IYI_MIKROFON_ISARETLERI = ("mikrofon dizisi", "microphone array", "dahili", "internal", "realtek", "intel",
                           "conexant", "built-in", "yerleşik")


def mikrofon_sec(sd):
    """Kullanılacak mikrofonu seçer: ayardaki numara/isim, yoksa Bluetooth kulaklık mikrofonu
    yerine bilgisayarın kendi mikrofonu (Bluetooth mikrofonu sesi boğar ve kulaklığı telefon moduna sokar)."""
    ayar = (AYAR.get("MIKROFON") or "").strip()
    cihazlar = list(enumerate(sd.query_devices()))
    girisler = [(i, d) for i, d in cihazlar if d.get("max_input_channels", 0) > 0]
    if ayar.isdigit():
        return int(ayar)
    if ayar and ayar.lower() not in ("otomatik", "auto"):
        for i, d in girisler:
            if ayar.lower() in d["name"].lower():
                return i
        log(f"'{ayar}' adında mikrofon bulunamadı, otomatik seçiliyor.")
    try:
        varsayilan = sd.default.device[0]
    except Exception:
        varsayilan = None
    if varsayilan is None or varsayilan < 0:
        return None
    vad = sd.query_devices(varsayilan)
    bt = lambda ad: any(k in ad.lower() for k in BT_MIKROFON_ISARETLERI)
    if not bt(vad["name"]):
        return varsayilan
    ayni_api = [(i, d) for i, d in girisler if d["hostapi"] == vad["hostapi"] and not bt(d["name"])]
    adaylar = sorted(ayni_api, key=lambda x: not any(k in x[1]["name"].lower() for k in IYI_MIKROFON_ISARETLERI))
    if adaylar:
        log(f"Bluetooth mikrofonu ({vad['name']}) yerine bilgisayarın mikrofonu kullanılıyor: {adaylar[0][1]['name']}")
        return adaylar[0][0]
    return varsayilan


class Kulak:
    def __init__(self):
        import numpy as np
        import sounddevice as sd
        self.np = np
        self.sd = sd
        self.kuyruk = queue.Queue()
        self.son_seviye = 0.0
        self.esik = 400
        cihaz = mikrofon_sec(sd)
        self.hiz = ORNEK_HIZI
        try:
            self.akis = sd.InputStream(samplerate=ORNEK_HIZI, channels=1, dtype="int16",
                                       blocksize=PARCA, device=cihaz, callback=self._geri)
        except Exception:
            # Bazı sürücüler 16 kHz açmaz: cihazın kendi hızında açıp yeniden örnekle
            bilgi = sd.query_devices(cihaz if cihaz is not None else sd.default.device[0])
            self.hiz = int(bilgi["default_samplerate"])
            self.akis = sd.InputStream(samplerate=self.hiz, channels=1, dtype="int16",
                                       blocksize=int(PARCA * self.hiz / ORNEK_HIZI), device=cihaz,
                                       callback=self._geri)
        try:
            ad = sd.query_devices(cihaz if cihaz is not None else sd.default.device[0])["name"]
        except Exception:
            ad = "?"
        log(f"Mikrofon: {ad}")
        self.akis.start()
        self._kalibre()

    def _geri(self, veri, kare, zaman, durum):
        p = veri[:, 0].copy()
        if self.hiz != ORNEK_HIZI:
            n = int(len(p) * ORNEK_HIZI / self.hiz)
            p = self.np.interp(self.np.linspace(0, len(p) - 1, n), self.np.arange(len(p)), p).astype(self.np.int16)
        self.kuyruk.put(p)
        try:
            self.son_seviye = min(1.0, self._rms(p) / (self.esik * 4))
        except Exception:
            pass

    def parca(self):
        return self.kuyruk.get()

    def temizle(self):
        while not self.kuyruk.empty():
            try:
                self.kuyruk.get_nowait()
            except queue.Empty:
                break

    def _rms(self, p):
        return float(self.np.sqrt(self.np.mean(p.astype(self.np.float32) ** 2)))

    def _kalibre(self):
        olcum = [self._rms(self.parca()) for _ in range(20)]
        ortam = sorted(olcum)[len(olcum) // 2]
        self.esik = max(220.0, ortam * 3.0)
        log(f"Ortam gürültüsü {ortam:.0f}, konuşma eşiği {self.esik:.0f}")

    def cumle_kaydet(self, bekleme=6.0, en_uzun=14.0, sessizlik=1.1):
        """Konuşma başlayınca kaydeder, sessizlikte durur. Ses yoksa None."""
        self.temizle()
        onceki = []
        kayit = []
        basladi = False
        sessiz_sure = 0.0
        yuksek_sayac = 0
        t0 = time.time()
        while True:
            p = self.parca()
            yuksek = self._rms(p) > self.esik
            if not basladi:
                onceki.append(p)
                onceki = onceki[-8:]            # konuşmanın başı kesilmesin (~0.6 sn)
                yuksek_sayac = yuksek_sayac + 1 if yuksek else 0
                if yuksek_sayac >= 2:           # tek bir tıkırtıyla başlama
                    basladi = True
                    kayit = list(onceki)
                elif MANUEL.is_set() and bekleme == 0:
                    return None
                elif bekleme and time.time() - t0 > bekleme:
                    return None
                continue
            kayit.append(p)
            sessiz_sure = 0.0 if yuksek else sessiz_sure + PARCA / ORNEK_HIZI
            if sessiz_sure >= sessizlik or len(kayit) * PARCA / ORNEK_HIZI > en_uzun:
                break
        return self.np.concatenate(kayit)

    def yaziya_cevir(self, ses):
        if ses is None or len(ses) < ORNEK_HIZI * 0.35:
            return ""
        metin = TANIYICI.cevir(ses)
        if metin:
            log(f"Duyduğum: {metin}")
        return metin


# ---------------- Ses tanıma: Whisper (bilgisayarda) ya da Google ----------------
WHISPER_IPUCU = ("Jarvis, merhaba. Saat kaç? Hava nasıl? Dubai, Abu Dhabi, Antalya, İstanbul, tur, otel, vize, "
                 "euro, dolar, rezervasyon, müşteri, mesaj, WhatsApp, Instagram, YouTube, Chrome, Google, gönder.")
WHISPER_UYDURMALAR = ("altyazı", "abone ol", "izlediğiniz için", "m.k.", "www.", "subtitles", "beğenmeyi unutmayın")


class Taniyici:
    def __init__(self):
        self.whisper = None
        self.yukleniyor = False
        tercih = (AYAR.get("TANIMA", "otomatik") or "otomatik").lower()
        if tercih in ("otomatik", "whisper"):
            try:
                import faster_whisper  # noqa: F401
                self.yukleniyor = True
                threading.Thread(target=self._whisper_yukle, daemon=True).start()
            except Exception:
                if tercih == "whisper":
                    log("Whisper yüklü değil. 'Gelismis Ses Tanima Kur.bat' dosyasını çalıştır.")

    def _whisper_yukle(self):
        try:
            from faster_whisper import WhisperModel
            boyut = AYAR.get("TANIMA_MODELI", "small") or "small"
            log(f"Gelişmiş ses tanıma (Whisper {boyut}) yükleniyor...")
            self.whisper = WhisperModel(boyut, device="cpu", compute_type="int8",
                                        download_root=os.path.join(KLASOR, "sesler", "whisper"))
            log("Gelişmiş ses tanıma hazır.")
        except Exception as e:
            log("Whisper yüklenemedi, Google ses tanıma kullanılacak:", e)
        self.yukleniyor = False

    def cevir(self, ses):
        if self.whisper is not None:
            try:
                return self._whisper(ses)
            except Exception as e:
                log("Whisper hatası:", e)
        return self._google(ses)

    def _whisper(self, ses):
        import numpy as np
        dalga = ses.astype(np.float32) / 32768.0
        tepe = float(np.max(np.abs(dalga))) or 1.0
        if tepe < 0.5:                       # sessiz mikrofonlarda sesi yükselt
            dalga = dalga * min(8.0, 0.7 / tepe)
        parcalar, bilgi = self.whisper.transcribe(
            dalga, language="tr", beam_size=5, initial_prompt=WHISPER_IPUCU,
            condition_on_previous_text=False, no_speech_threshold=0.6, vad_filter=False)
        metin = " ".join(p.text.strip() for p in parcalar if p.no_speech_prob < 0.7).strip()
        if any(u in metin.lower() for u in WHISPER_UYDURMALAR) and len(metin) < 60:
            return ""
        return metin.strip(" .")

    def _google(self, ses):
        import speech_recognition as sr
        veri = sr.AudioData(ses.tobytes(), ORNEK_HIZI, 2)
        try:
            return sr.Recognizer().recognize_google(veri, language="tr-TR")
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            log("Ses tanıma servisine ulaşılamadı (internet?):", e)
            return ""


class _GecikmeliTaniyici:
    """İlk kullanımda oluşturulur (ayarlar okunduktan sonra)."""
    _t = None

    def cevir(self, ses):
        if _GecikmeliTaniyici._t is None:
            _GecikmeliTaniyici._t = Taniyici()
        return _GecikmeliTaniyici._t.cevir(ses)

    def baslat(self):
        if _GecikmeliTaniyici._t is None:
            _GecikmeliTaniyici._t = Taniyici()


TANIYICI = _GecikmeliTaniyici()


class UyanmaModeli:
    """openWakeWord 'hey jarvis' modeli (çevrimdışı)."""

    def __init__(self):
        import openwakeword
        from openwakeword.model import Model
        try:
            openwakeword.utils.download_models(["hey_jarvis"])
        except TypeError:
            openwakeword.utils.download_models()
        self.model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        self.esik = float(AYAR["UYANMA_HASSASIYETI"] or 0.5)

    def duydu_mu(self, parca):
        skor = max(self.model.predict(parca).values())
        return skor >= self.esik

    def sifirla(self):
        self.model.reset()


UYANMA_KELIMELERI = ("jarvis", "carvis", "cervis", "çervis", "jarvıs", "cerviz", "garvis", "jervis")


def uyanma_kelimesi_ayikla(metin):
    """'jarvis saat kaç' -> (True, 'saat kaç')."""
    kucuk = tr_kucuk(metin)
    for k in UYANMA_KELIMELERI:
        i = kucuk.find(k)
        if i != -1:
            kalan = metin[i + len(k):].strip(" ,.!?")
            return True, kalan
    return False, ""


# ----------------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------------

def tr_kucuk(s):
    return s.replace("I", "ı").replace("İ", "i").lower()


SAYI_KELIME = {
    "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8,
    "dokuz": 9, "on": 10, "on beş": 15, "yirmi": 20, "otuz": 30, "kırk": 40, "kırk beş": 45,
    "elli": 50, "altmış": 60, "yarım": 0.5, "buçuk": 0.5,
}

GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
         "Eylül", "Ekim", "Kasım", "Aralık"]


def sayi_bul(metin):
    m = re.search(r"(\d+(?:[.,]\d+)?)", metin)
    if m:
        return float(m.group(1).replace(",", "."))
    for kelime in sorted(SAYI_KELIME, key=len, reverse=True):
        if re.search(rf"\b{kelime}\b", metin):
            return SAYI_KELIME[kelime]
    return None


# ----------------------------------------------------------------------------
# Eylemler
# ----------------------------------------------------------------------------

UYGULAMALAR = {
    "chrome": "chrome", "krom": "chrome", "google chrome": "chrome",
    "edge": "msedge", "tarayıcı": "chrome",
    "whatsapp": "whatsapp:", "vatsap": "whatsapp:", "watsap": "whatsapp:",
    "telegram": "tg:", "spotify": "spotify:", "zoom": "zoommtg:",
    "hesap makinesi": "calc", "hesap makinası": "calc",
    "not defteri": "notepad", "dosya gezgini": "explorer", "dosyalar": "explorer",
    "ayarlar": "ms-settings:", "paint": "mspaint", "word": "winword", "excel": "excel",
    "görev yöneticisi": "taskmgr", "kamera": "microsoft.windows.camera:",
}

SITELER = {
    "youtube": "https://www.youtube.com",
    "instagram": "https://www.instagram.com",
    "facebook": "https://www.facebook.com",
    "gmail": "https://mail.google.com",
    "mail": "https://mail.google.com",
    "business suite": "https://business.facebook.com/latest/inbox/all",
    "meta": "https://business.facebook.com/latest/inbox/all",
    "gelen kutusu": "https://business.facebook.com/latest/inbox/all",
    "reklam yöneticisi": "https://adsmanager.facebook.com",
    "whatsapp web": "https://web.whatsapp.com",
    "google drive": "https://drive.google.com",
    "drive": "https://drive.google.com",
    "takvim": "https://calendar.google.com",
    "harita": "https://maps.google.com",
    "çeviri": "https://translate.google.com",
    "claude": "https://claude.ai",
}


def uygulama_ac(ad):
    ad = tr_kucuk(ad).strip()
    for anahtar in sorted(SITELER, key=len, reverse=True):
        if anahtar in ad:
            webbrowser.open(SITELER[anahtar])
            return f"{anahtar.title()} açılıyor."
    for anahtar in sorted(UYGULAMALAR, key=len, reverse=True):
        if anahtar in ad:
            hedef = UYGULAMALAR[anahtar]
            try:
                if hedef.endswith(":"):
                    os.startfile(hedef)
                else:
                    subprocess.Popen(f'start "" {hedef}', shell=True)
                return f"{anahtar.title()} açılıyor."
            except Exception:
                return f"{anahtar.title()} açılamadı, bilgisayarda yüklü olmayabilir."
    # Bilinmeyen: Windows'un kendisine sor
    try:
        subprocess.Popen(f'start "" "{ad}"', shell=True)
        return f"{ad} açmayı deniyorum."
    except Exception:
        return f"{ad} adında bir şey bulamadım."


def web_ara(sorgu):
    webbrowser.open("https://www.google.com/search?q=" + urllib.parse.quote(sorgu))
    return f"Google'da {sorgu} için arama yapıyorum."


def youtube_ac(sorgu):
    webbrowser.open("https://www.youtube.com/results?search_query=" + urllib.parse.quote(sorgu))
    return f"YouTube'da {sorgu} açıyorum."


def _tus(vk, kac=1):
    import ctypes
    for _ in range(kac):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


def ses_ayarla(yon):
    if yon == "ac":
        _tus(0xAF, 5)
        return "Sesi açtım."
    if yon == "kis":
        _tus(0xAE, 5)
        return "Sesi kıstım."
    _tus(0xAD)
    return "Sesi kapattım." if yon == "kapat" else "Tamam."


def medya(eylem):
    vk = {"durdur": 0xB3, "devam": 0xB3, "sonraki": 0xB0, "onceki": 0xB1}[eylem]
    _tus(vk)
    return "Tamam."


def ekran_goruntusu():
    from PIL import ImageGrab
    klasor = os.path.join(os.path.expanduser("~"), "Pictures", "Jarvis")
    os.makedirs(klasor, exist_ok=True)
    yol = os.path.join(klasor, datetime.datetime.now().strftime("ekran_%Y%m%d_%H%M%S.png"))
    ImageGrab.grab(all_screens=True).save(yol)
    os.startfile(klasor)
    return "Ekran görüntüsünü aldım, Resimler klasöründe Jarvis içinde."


def kilitle():
    import ctypes
    ctypes.windll.user32.LockWorkStation()
    return "Bilgisayarı kilitliyorum."


def saat_kac():
    s = datetime.datetime.now()
    return f"Saat {s.hour}:{s.minute:02d}."


def tarih():
    s = datetime.datetime.now()
    return f"Bugün {s.day} {AYLAR[s.month - 1]} {s.year}, {GUNLER[s.weekday()]}."


def hatirlatici_kur(dakika, mesaj):
    dakika = float(dakika)

    def _cal():
        bip(); bip()
        konus(f"{HITAP.capitalize()}, hatırlatma: {mesaj}")

    threading.Timer(dakika * 60, _cal).start()
    if dakika < 1:
        return f"Tamam, {int(dakika * 60)} saniye sonra hatırlatacağım."
    dk = int(dakika) if dakika == int(dakika) else dakika
    return f"Tamam, {dk} dakika sonra hatırlatacağım."


def not_al(metin):
    yol = os.path.join(KLASOR, "notlarim.txt")
    with open(yol, "a", encoding="utf-8") as f:
        f.write(datetime.datetime.now().strftime("%d.%m.%Y %H:%M") + "  " + metin + "\n")
    return "Not aldım."


def gorsel_olustur(tarif, en=1024, boy=1024):
    """Ücretsiz Pollinations servisiyle görsel üretir, kaydeder ve açar."""
    import urllib.request
    konus("Hemen çiziyorum, birkaç saniye sürebilir.")
    EKRAN.durum("dusunuyor", "Görsel çiziliyor…")
    tohum = random.randint(1, 10_000_000)
    url = ("https://image.pollinations.ai/prompt/" + urllib.parse.quote(tarif)
           + f"?width={int(en)}&height={int(boy)}&nologo=true&enhance=true&seed={tohum}")
    klasor = os.path.join(os.path.expanduser("~"), "Pictures", "Jarvis")
    os.makedirs(klasor, exist_ok=True)
    yol = os.path.join(klasor, datetime.datetime.now().strftime("gorsel_%Y%m%d_%H%M%S.jpg"))
    istek = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Jarvis"})
    son_hata = None
    for _ in range(2):
        try:
            with urllib.request.urlopen(istek, timeout=120) as r, open(yol, "wb") as f:
                f.write(r.read())
            os.startfile(yol)
            return "Görsel hazır, ekranda açtım. Resimler klasöründe Jarvis içine kaydettim."
        except Exception as e:
            son_hata = e
    log("Görsel hatası:", son_hata)
    return "Görsel servisine şu an ulaşamadım, biraz sonra tekrar dener misin?"


def ekran_resmi_b64(en_buyuk=1600):
    """Birincil ekranın görüntüsünü küçültüp base64 JPEG döndürür."""
    try:
        import io
        import base64
        from PIL import ImageGrab
        resim = ImageGrab.grab()
        resim.thumbnail((en_buyuk, en_buyuk))
        tampon = io.BytesIO()
        resim.convert("RGB").save(tampon, format="JPEG", quality=78)
        return base64.b64encode(tampon.getvalue()).decode()
    except Exception as e:
        log("Ekran görüntüsü alınamadı:", e)
        return None


def ekrana_bak(soru="Ekranda ne var?"):
    """Ekranı yüksek çözünürlükte Claude'a gösterir (API anahtarı gerekir)."""
    if not BEYIN or not BEYIN.aktif:
        return "Ekrana bakabilmem için ayarlar dosyasına API anahtarı eklemen gerekiyor."
    veri = ekran_resmi_b64(1600)
    if not veri:
        return "Ekran görüntüsünü alamadım."
    yanit = BEYIN.istemci.messages.create(
        model=AYAR["MODEL"], max_tokens=500,
        system="Kullanıcının bilgisayar ekranının görüntüsüne bakıp Türkçe, kısa ve net cevap ver. Cevap sesli okunacak; markdown kullanma.",
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": veri}},
            {"type": "text", "text": soru}]}])
    return " ".join(b.text for b in yanit.content if b.type == "text").strip()


def notlari_oku():
    yol = os.path.join(KLASOR, "notlarim.txt")
    if not os.path.exists(yol):
        return "Hiç notun yok."
    with open(yol, encoding="utf-8") as f:
        satirlar = [s.strip() for s in f if s.strip()][-5:]
    if not satirlar:
        return "Hiç notun yok."
    return "Son notların: " + ". ".join(s.split("  ", 1)[-1] for s in satirlar) + "."


# ----------------------------------------------------------------------------
# Komut anlama (yerel, internetsiz kurallar)
# ----------------------------------------------------------------------------

CIKIS = ("görüşürüz", "kendini kapat", "jarvis kapan", "programı kapat", "uyu jarvis", "hoşça kal")


def yerel_komut(metin):
    """Basit komutları yapay zekâya sormadan anında yapar. Anlamazsa None."""
    m = tr_kucuk(metin).strip(" .!?")
    if not m:
        return None

    if any(k in m for k in CIKIS):
        return "__CIKIS__"

    if re.search(r"saat (kaç|ne)", m) or m in ("saat", "saati söyle"):
        return saat_kac()
    if re.search(r"(bugün|tarih|günlerden|ayın kaçı|hangi gün)", m) and len(m) < 40 and "hava" not in m:
        return tarih()

    # Hatırlatıcı / zamanlayıcı
    if re.search(r"(hatırlat|zamanlayıcı|alarm kur|haber ver)", m):
        sayi = sayi_bul(m)
        if sayi is not None:
            if "saat" in m and "sonra" in m and "dakika" not in m:
                dakika = sayi * 60
            elif "saniye" in m:
                dakika = sayi / 60
            else:
                dakika = sayi
            mesaj = re.sub(r".*?(dakika|saniye|saat)\s*(sonra)?\s*", "", m, count=1)
            mesaj = re.sub(r"\b(bana|hatırlat\w*|haber ver\w*|zamanlayıcı\w*|kur)\b", "", mesaj).strip(" ,.")
            return hatirlatici_kur(dakika, mesaj or "zaman doldu")

    # Notlar
    if m.startswith("not al") or m.startswith("not et"):
        icerik = re.sub(r"^not (al|et)\s*[:,]?\s*", "", m)
        return not_al(icerik) if icerik else "Ne not almamı istersin? 'Not al' deyip devamını söyle."
    if "notlarımı oku" in m or "notlarım" in m:
        return notlari_oku()

    # Ses / medya
    if re.search(r"ses(i)? (aç|yükselt|arttır|artır)", m):
        return ses_ayarla("ac")
    if re.search(r"ses(i)? (kıs|azalt|düşür)", m):
        return ses_ayarla("kis")
    if re.search(r"ses(i)? (kapat|sustur)", m) or m == "sessiz":
        return ses_ayarla("kapat")
    if re.search(r"(müziği|şarkıyı|videoyu)? ?(durdur|duraklat)", m) and len(m) < 25:
        return medya("durdur")
    if re.search(r"(sonraki|diğer) (şarkı|parça)", m):
        return medya("sonraki")
    if re.search(r"önceki (şarkı|parça)", m):
        return medya("onceki")

    # Görsel üretme: "deniz kenarında otel görseli yap", "bir kedi çiz"
    gm = re.match(r"(.+?)\s+(görsel|resim|resmi|fotoğraf|çizim|logo|afiş|poster)\w*\s+(?:yap|çiz|oluştur|üret|hazırla)\w*$", m) \
        or re.match(r"(?:bana\s+)?(.+?)\s+çiz(?:er misin|sene|)$", m)
    if gm and not BEYIN_AKTIF():
        tarif = re.sub(r"^(bana|bir)\s+", "", gm.group(1)).strip()
        if gm.lastindex and gm.lastindex >= 2 and gm.group(2) in ("logo", "afiş", "poster"):
            tarif += " " + gm.group(2)
        return gorsel_olustur(tarif)

    if re.search(r"ekran(ımda|da) ne (var|görüyorsun)|ekranıma bak", m):
        return ekrana_bak(metin)

    if re.search(r"hava (nasıl|durumu)|kaç derece|yağmur yağ|dışarısı nasıl", m):
        sehir = re.match(r"(.+?)'?(?:da|de|ta|te)?\s+hava", m)
        sehir = sehir.group(1) if sehir and sehir.group(1) not in ("bugün", "yarın", "şu an", "dışarıda") else None
        return hava_durumu(sehir)
    if re.search(r"sistem (durumu|raporu)|sistemler nasıl|batarya|pil (durumu|kaç)", m):
        return sistem_durumu()

    if "ekran görüntüsü" in m:
        return ekran_goruntusu()
    if re.search(r"(bilgisayarı|ekranı) kilitle", m):
        return kilitle()

    # YouTube
    yt = re.match(r"(?:youtube'?(?:da|ta|dan)?)\s+(.+?)\s+(?:aç|çal|oynat|bul)$", m) \
        or re.match(r"(.+?)\s+(?:youtube'?(?:da|ta|dan))\s+(?:aç|çal|oynat|bul)$", m) \
        or re.match(r"(.+?)\s+(?:şarkısını|şarkısı|videosunu)\s+(?:aç|çal|oynat)$", m)
    if yt:
        return youtube_ac(yt.group(1))

    # Google arama
    ara = re.match(r"(?:google'?(?:da|dan)?)\s+(.+?)\s*(?:ara|bul|arat)?$", m) \
        or (None if BEYIN_AKTIF() else re.match(r"(.+?)\s+(?:ara|arat|araştır)$", m))
    if ara and not m.endswith("aç"):
        return web_ara(ara.group(1))

    # Uygulama / site aç
    ac = re.match(r"(.+?)\s*(?:'?[yı]?[ıiuü]?)\s*(?:aç|başlat|çalıştır)$", m)
    if ac:
        hedef = re.sub(r"(['’]?(yı|yi|yu|yü|ı|i|u|ü|nı|ni|nu|nü))$", "", ac.group(1).strip())
        if hedef and hedef not in ("sesi", "ses"):
            bilinen = any(k in hedef for k in list(SITELER) + list(UYGULAMALAR))
            if bilinen or not BEYIN_AKTIF():
                return uygulama_ac(hedef)

    if m in ("teşekkürler", "teşekkür ederim", "sağ ol", "sağol", "eyvallah"):
        return random.choice(["Rica ederim.", "Ne demek, her zaman.", "Emrindeyim."])
    if m in ("nasılsın", "naber", "ne haber"):
        return "Gayet iyiyim, sen nasılsın? Ne yapalım?"

    return None


# ----------------------------------------------------------------------------
# Yapay zekâ beyni (Claude) - isteğe bağlı
# ----------------------------------------------------------------------------

ARACLAR = [
    {"name": "uygulama_ac", "description": "Bilgisayarda bir uygulama veya web sitesi açar (chrome, whatsapp, youtube, gmail, meta business suite...).",
     "input_schema": {"type": "object", "properties": {"ad": {"type": "string"}}, "required": ["ad"]}},
    {"name": "web_ara", "description": "Google'da arama sayfasını tarayıcıda açar.",
     "input_schema": {"type": "object", "properties": {"sorgu": {"type": "string"}}, "required": ["sorgu"]}},
    {"name": "youtube_ac", "description": "YouTube'da video/şarkı araması açar.",
     "input_schema": {"type": "object", "properties": {"sorgu": {"type": "string"}}, "required": ["sorgu"]}},
    {"name": "hatirlatici_kur", "description": "Belirli dakika sonra sesli hatırlatma yapar.",
     "input_schema": {"type": "object", "properties": {"dakika": {"type": "number"}, "mesaj": {"type": "string"}}, "required": ["dakika", "mesaj"]}},
    {"name": "ses_ayarla", "description": "Bilgisayarın sesini açar, kısar veya kapatır.",
     "input_schema": {"type": "object", "properties": {"yon": {"type": "string", "enum": ["ac", "kis", "kapat"]}}, "required": ["yon"]}},
    {"name": "not_al", "description": "Kullanıcının notlar dosyasına not ekler.",
     "input_schema": {"type": "object", "properties": {"metin": {"type": "string"}}, "required": ["metin"]}},
    {"name": "notlari_oku", "description": "Son notları okur.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "ekran_goruntusu", "description": "Ekran görüntüsü alıp kaydeder.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "gorsel_olustur",
     "description": "Yapay zekâ ile görsel/resim/logo/afiş üretir ve ekranda açar. 'tarif' alanına görseli ayrıntılı anlatan "
                    "İNGİLİZCE bir prompt yaz (konu, stil, ışık, renkler, kompozisyon). Görselin içinde yazı isteniyorsa yazıyı tırnak içinde ekle. "
                    "Kullanıcı önceki görselde değişiklik isterse önceki promptu güncelleyip yeniden çağır. "
                    "Instagram gönderisi için 1080x1080, hikâye/reels için 1080x1920, yatay afiş için 1920x1080 kullan.",
     "input_schema": {"type": "object", "properties": {
         "tarif": {"type": "string"}, "en": {"type": "integer"}, "boy": {"type": "integer"}}, "required": ["tarif"]}},
    {"name": "ekrana_bak", "description": "Kullanıcının o anki ekranının görüntüsünü alıp soruyu ekrana bakarak cevaplar "
                                          "(ekranda ne var, bu mesajı özetle, bu müşteriye ne cevap vereyim gibi).",
     "input_schema": {"type": "object", "properties": {"soru": {"type": "string"}}, "required": ["soru"]}},
]

ARAC_FONK = {
    "uygulama_ac": lambda a: uygulama_ac(a["ad"]),
    "web_ara": lambda a: web_ara(a["sorgu"]),
    "youtube_ac": lambda a: youtube_ac(a["sorgu"]),
    "hatirlatici_kur": lambda a: hatirlatici_kur(a["dakika"], a["mesaj"]),
    "ses_ayarla": lambda a: ses_ayarla(a["yon"]),
    "not_al": lambda a: not_al(a["metin"]),
    "notlari_oku": lambda a: notlari_oku(),
    "ekran_goruntusu": lambda a: ekran_goruntusu(),
    "gorsel_olustur": lambda a: gorsel_olustur(a["tarif"], a.get("en", 1024), a.get("boy", 1024)),
    "ekrana_bak": lambda a: ekrana_bak(a["soru"]),
}

BEYIN = None


def BEYIN_AKTIF():
    return BEYIN is not None and BEYIN.aktif


class Beyin:
    def __init__(self):
        self.istemci = None
        self.gecmis = []
        if AYAR["ANTHROPIC_API_KEY"]:
            try:
                import anthropic
                self.istemci = anthropic.Anthropic(api_key=AYAR["ANTHROPIC_API_KEY"])
            except Exception as e:
                log("Claude bağlanamadı:", e)

    @property
    def aktif(self):
        return self.istemci is not None

    def sistem(self):
        s = datetime.datetime.now()
        return (
            "Sen JARVIS'sin: kullanıcının Windows bilgisayarında çalışan, Türkçe konuşan sesli asistan. "
            f"Kullanıcıya '{HITAP}' diye hitap edebilirsin. Cevapların sesli okunacak: kısa (1-3 cümle), "
            "doğal konuşma dilinde, madde işareti, emoji ve markdown kullanma. Sayıları okunur biçimde yaz. "
            "Bir işlem istenirse uygun aracı kullan, sonra ne yaptığını tek cümleyle söyle. Görsel çizebilirsin. "
            + ("Her mesajla birlikte kullanıcının o anki ekran görüntüsünü görürsün; 'bu', 'şu', 'ekrandaki' gibi "
               "sorularda ona bakarak cevap ver, ilgisiz sorularda ekrandan hiç bahsetme. Ekranın sağ altındaki dönen "
               "mavi halka ve yazılar senin kendi arayüzün, onları anlatma. " if EKRANI_GOR else "Ekrana bakabilirsin. ")
            + ("Bilgisayarın faresini ve klavyesini 'computer' araçlarıyla kullanabilirsin: kullanıcı 'şuraya bas', "
               "'şunu yaz', 'gönder'e bas', 'şu mesajı aç' gibi ekranda bir şey yapmanı isterse adım adım yap; her "
               "adımdan sonra gelen ekran görüntüsüyle sonucu kontrol et. Sadece istenen işi yap, fazlasını yapma. "
               "Ödeme yapmak, şifre ya da kart bilgisi girmek, bir şeyi kalıcı silmek gibi geri alınamaz işlerde önce "
               "kullanıcıya sor; kullanıcı açıkça istediyse mesaj göndermek serbest. Yazacağın metni kullanıcı tam "
               "söylemediyse kısa ve kibar bir metin sen yaz. Bitince ne yaptığını tek cümleyle söyle. "
               if BILGISAYAR_KONTROL else "")
            + "Kullanıcı tur/seyahat acentesi işi yapıyor; tur, otel, vize sorularında yardımcı ol. "
            f"Şu an: {s.day} {AYLAR[s.month-1]} {s.year} {GUNLER[s.weekday()]}, saat {s.hour}:{s.minute:02d}."
        )

    def _dusunceleri_temizle(self):
        """Biten turlardaki 'thinking' bloklarını geçmişten çıkarır.
        (Ekran görüntüsü sadece son soruya eklendiği için eski düşünce imzaları geçersiz kalır.)"""
        for m in self.gecmis:
            if m["role"] == "user" and isinstance(m["content"], list):
                for blok in m["content"]:
                    if isinstance(blok, dict) and blok.get("type") == "tool_result" and isinstance(blok.get("content"), list):
                        blok["content"] = [c for c in blok["content"] if c.get("type") != "image"] or "Tamam."
            if m["role"] == "assistant" and isinstance(m["content"], list):
                kalan = [b for b in m["content"]
                         if (b.get("type") if isinstance(b, dict) else getattr(b, "type", "")) not in ("thinking", "redacted_thinking")]
                m["content"] = kalan or [{"type": "text", "text": "Tamam."}]

    def sor(self, metin):
        self.gecmis.append({"role": "user", "content": metin})
        self.gecmis = self.gecmis[-16:]
        while self.gecmis and self.gecmis[0]["role"] != "user" or (
                self.gecmis and not isinstance(self.gecmis[0]["content"], str)):
            self.gecmis.pop(0)
        sira = len(self.gecmis) - 1
        resim = None
        if EKRANI_GOR or BILGISAYAR_KONTROL:
            try:
                resim = bilgisayar.b64(bilgisayar.ekran_resmi()) if bilgisayar else ekran_resmi_b64(1280)
            except Exception as e:
                log("Ekran görüntüsü alınamadı:", e)
        try:
            for _ in range(30):
                mesajlar = list(self.gecmis)
                if resim:
                    mesajlar[sira] = {"role": "user", "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": resim}},
                        {"type": "text", "text": "[Ekranımın şu anki görüntüsü ektedir; gerekmiyorsa bahsetme.]\n" + metin}]}
                yanit = self.istemci.messages.create(
                    model=AYAR["MODEL"], max_tokens=800, system=self.sistem(),
                    tools=ARACLAR, messages=mesajlar)
                self.gecmis.append({"role": "assistant", "content": list(yanit.content)})
                if yanit.stop_reason != "tool_use":
                    self._dusunceleri_temizle()
                    return " ".join(b.text for b in yanit.content if b.type == "text").strip() or "Tamam."
                sonuclar = []
                durdu = False
                for b in yanit.content:
                    if b.type != "tool_use":
                        continue
                    if durdu:
                        sonuclar.append({"type": "tool_result", "tool_use_id": b.id, "content": "Kullanıcı durdurdu."})
                        continue
                    bilgisayar_eylemi = (getattr(b, "toolset_name", None) == "computer"
                                         or (bilgisayar and b.name in bilgisayar.EYLEMLER and b.name not in ARAC_FONK))
                    if bilgisayar_eylemi:
                        if not BILGISAYAR_KONTROL:
                            icerik = "Bilgisayar kontrolü kapalı."
                        else:
                            EKRAN.durum("dusunuyor", "Ekranda çalışıyorum · durdurmak için Esc'yi basılı tut")
                            try:
                                icerik = bilgisayar.eylem(b.name, b.input)
                            except bilgisayar.Durduruldu as e:
                                durdu = True
                                icerik = f"Kullanıcı durdurdu ({e}). Başka işlem yapma."
                            except Exception as e:
                                icerik = f"Hata: {e}"
                        log(f"  ekran: {b.name} {json_kisa(b.input)}")
                        sonuclar.append({"type": "tool_result", "tool_use_id": b.id, "content": icerik})
                        continue
                    try:
                        sonuc = ARAC_FONK[b.name](b.input)
                    except Exception as e:
                        sonuc = f"Hata: {e}"
                    log(f"  araç: {b.name} -> {sonuc}")
                    sonuclar.append({"type": "tool_result", "tool_use_id": b.id, "content": str(sonuc)})
                self.gecmis.append({"role": "user", "content": sonuclar})
                if durdu:
                    self._dusunceleri_temizle()
                    return "Durdum."
            self._dusunceleri_temizle()
            return "Tamam, hallettim."
        except Exception as e:
            log("Claude hatası:", e)
            self.gecmis = []
            return "Şu an yapay zekâya ulaşamıyorum. İnternet bağlantını ya da API anahtarını kontrol eder misin?"


# ----------------------------------------------------------------------------
# Ana döngü
# ----------------------------------------------------------------------------

YAZI_MODU = "--yazi" in sys.argv
MANUEL = threading.Event()        # ekrandaki mikrofon düğmesi
ISLEM_KILIDI = threading.Lock()   # aynı anda tek komut


# ----------------------------------------------------------------------------
# Hava durumu, sistem durumu, karşılama
# ----------------------------------------------------------------------------

HAVA_KODLARI = {
    "113": "Açık", "116": "Parçalı bulutlu", "119": "Bulutlu", "122": "Kapalı", "143": "Puslu",
    "176": "Yer yer yağmurlu", "179": "Yer yer kar yağışlı", "182": "Yer yer karla karışık yağmur",
    "185": "Yer yer donan çisenti", "200": "Yer yer gök gürültülü", "227": "Tipi", "230": "Kar fırtınası",
    "248": "Sisli", "260": "Dondurucu sis", "263": "Yer yer çisenti", "266": "Çisenti", "281": "Donan çisenti",
    "284": "Yoğun donan çisenti", "293": "Yer yer hafif yağmurlu", "296": "Hafif yağmurlu",
    "299": "Ara ara yağmurlu", "302": "Yağmurlu", "305": "Ara ara kuvvetli yağmurlu", "308": "Kuvvetli yağmurlu",
    "311": "Hafif donan yağmur", "314": "Donan yağmur", "317": "Hafif karla karışık yağmur",
    "320": "Karla karışık yağmur", "323": "Yer yer hafif kar yağışlı", "326": "Hafif kar yağışlı",
    "329": "Yer yer kar yağışlı", "332": "Kar yağışlı", "335": "Yer yer yoğun kar yağışlı", "338": "Yoğun kar yağışlı",
    "350": "Buz taneli", "353": "Hafif sağanak yağmurlu", "356": "Sağanak yağmurlu", "359": "Şiddetli sağanak yağmurlu",
    "362": "Hafif karla karışık sağanak", "365": "Karla karışık sağanak", "368": "Hafif kar sağanaklı",
    "371": "Kar sağanaklı", "374": "Hafif buz taneli", "377": "Buz taneli", "386": "Gök gürültülü hafif yağmurlu",
    "389": "Gök gürültülü yağmurlu", "392": "Gök gürültülü hafif kar yağışlı", "395": "Gök gürültülü kar yağışlı",
}


def hava_bilgisi(sehir=None):
    """wttr.in'den hava durumu (anahtar gerekmez). {'temp','hiss','desc','yer'} ya da None."""
    import json
    import urllib.request
    sehir = (sehir or AYAR.get("SEHIR") or "").strip()
    url = "https://wttr.in/" + urllib.parse.quote(sehir) + "?format=j1&lang=tr"
    try:
        istek = urllib.request.Request(url, headers={"User-Agent": "curl/8 Jarvis"})
        with urllib.request.urlopen(istek, timeout=10) as r:
            v = json.loads(r.read().decode("utf-8"))
        c = v["current_condition"][0]
        desc = HAVA_KODLARI.get(str(c.get("weatherCode", ""))) \
            or (c.get("lang_tr") or c.get("weatherDesc"))[0]["value"].strip()
        yer = (sehir[:1].replace("i", "İ").upper() + sehir[1:]) if sehir else v.get("nearest_area", [{}])[0].get("areaName", [{}])[0].get("value", "")
        return {"temp": int(c["temp_C"]), "hiss": int(c["FeelsLikeC"]), "desc": desc.capitalize(), "yer": yer}
    except Exception as e:
        log("Hava durumu alınamadı:", e)
        return None


def hava_durumu(sehir=None):
    h = hava_bilgisi(sehir)
    if not h:
        return "Hava durumu bilgisine şu an ulaşamıyorum."
    if not sehir:
        EKRAN.veri("setWeather", h)
    yer = f"{h['yer']} için " if h["yer"] else ""
    return f"Hava {yer}{h['temp']} derece, {h['desc'].lower()}. Hissedilen {h['hiss']} derece."


def sistem_bilgisi():
    try:
        import psutil
        b = psutil.sensors_battery()
        return {"cpu": psutil.cpu_percent(interval=None), "ram": psutil.virtual_memory().percent,
                "bat": round(b.percent) if b else None, "sarj": bool(b and b.power_plugged)}
    except Exception:
        return {"cpu": None, "ram": None, "bat": None, "sarj": False}


def sistem_durumu():
    s = sistem_bilgisi()
    if s["cpu"] is None:
        return "Sistem bilgisine ulaşamıyorum."
    metin = f"İşlemci yüzde {round(s['cpu'])}, bellek yüzde {round(s['ram'])} kullanımda."
    if s["bat"] is not None:
        metin += f" Batarya yüzde {s['bat']}" + (", şarjda." if s["sarj"] else ".")
    return metin + " Tüm sistemler normal."


def selamlama():
    s = datetime.datetime.now()
    if 5 <= s.hour < 12:
        selam = "Günaydın"
    elif 12 <= s.hour < 18:
        selam = "İyi günler"
    elif 18 <= s.hour < 23:
        selam = "İyi akşamlar"
    else:
        selam = "İyi geceler"
    metin = f"{selam} {HITAP}. Saat {s.hour}:{s.minute:02d}."
    h = hava_bilgisi()
    if h:
        EKRAN.veri("setWeather", h)
        metin += f" Dışarıda hava {h['temp']} derece, {h['desc'].lower()}."
    return metin + " Tüm sistemler çevrimiçi."


ARACLAR += [
    {"name": "hava_durumu", "description": "Güncel hava durumunu getirir. Şehir verilmezse kullanıcının bulunduğu yer.",
     "input_schema": {"type": "object", "properties": {"sehir": {"type": "string"}}}},
    {"name": "sistem_durumu", "description": "Bilgisayarın işlemci, bellek ve batarya durumunu söyler.",
     "input_schema": {"type": "object", "properties": {}}},
]
ARAC_FONK["hava_durumu"] = lambda a: hava_durumu(a.get("sehir"))
if BILGISAYAR_KONTROL:
    ARACLAR.append({"type": "computer_toolset_20260801"})


def json_kisa(veri):
    import json
    m = json.dumps(veri, ensure_ascii=False)
    return m if len(m) < 120 else m[:117] + "..."
ARAC_FONK["sistem_durumu"] = lambda a: sistem_durumu()


# ----------------------------------------------------------------------------
# Ana döngü
# ----------------------------------------------------------------------------

def isle(metin, beyin):
    """Komutu işler; cevap metnini döndürür. Çıkış için '__CIKIS__'."""
    log(f"SEN: {metin}")
    EKRAN.mesaj("sen", metin)
    EKRAN.durum("dusunuyor")
    try:
        cevap = yerel_komut(metin)
        if cevap is not None:
            return cevap
        if beyin.aktif:
            return beyin.sor(metin)
        return web_ara(metin) + " Daha akıllı cevaplar için ayarlar dosyasına API anahtarı ekleyebilirsin."
    except Exception as e:
        log("Komut hatası:", e)
        return "Bunu yaparken bir sorun çıktı."


def yazi_dongusu(beyin):
    print("Yazı modu. Komut yaz (çıkmak için 'görüşürüz').")
    while True:
        try:
            metin = input("SEN> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not metin:
            continue
        cevap = isle(metin, beyin)
        if cevap == "__CIKIS__":
            konus("Görüşürüz.")
            break
        konus(cevap)


def kapan():
    """Jarvis'i (ve ekranı) kapatır."""
    try:
        if hasattr(EKRAN, "kapat"):
            EKRAN.kapat()
        elif EKRAN.pencere is not None:
            EKRAN.pencere.destroy()
    except Exception:
        pass
    time.sleep(0.3)
    os._exit(0)


def komut_calistir(metin, beyin):
    """Tek bir komutu işleyip cevabı söyler. Kapanma istenirse True döner."""
    with ISLEM_KILIDI:
        cevap = isle(metin, beyin)
        if cevap == "__CIKIS__":
            konus(f"Görüşürüz {HITAP}. İhtiyacın olursa buradayım.")
            return True
        konus(cevap)
        return False


def ses_dongusu(beyin):
    TANIYICI.baslat()
    try:
        kulak = Kulak()
    except Exception as e:
        log("Mikrofon açılamadı:", e)
        try:
            import sounddevice as sd
            log("Mikrofonların listesi:\n" + str(sd.query_devices()))
        except Exception:
            pass
        EKRAN.durum("hata", "Mikrofon bulunamadı. Komutları aşağıya yazabilirsin.")
        if not EKRAN.aktif:
            if sys.stdin and sys.stdin.isatty():
                input("Enter'a basıp kapat...")
        else:
            konus(selamlama() + " Mikrofonuna ulaşamıyorum, komutlarını yazarak verebilirsin.")
            EKRAN.durum("bekliyor", "Mikrofon yok · komutları aşağıya yaz")
        return

    # Mikrofon seviyesini ekrana aktar
    def _seviye_gonder():
        while True:
            if EKRAN.durum_adi in ("dinliyor", "bekliyor"):
                EKRAN.seviye(kulak.son_seviye)
            time.sleep(0.08)
    if EKRAN.aktif:
        threading.Thread(target=_seviye_gonder, daemon=True).start()

    uyanma = None
    yontem = AYAR["UYANMA_YONTEMI"].lower()
    if yontem in ("otomatik", "model"):
        try:
            log("'Hey Jarvis' modeli yükleniyor...")
            uyanma = UyanmaModeli()
        except Exception as e:
            log("Uyanma modeli yüklenemedi, kelime dinleme moduna geçiyorum:", e)

    EKRAN.veri("setInfo", {"uyanma": "Hey Jarvis" if uyanma else "“Jarvis” kelimesi"})
    if (AYAR.get("SES_MOTORU", "otomatik") or "otomatik").lower() in ("otomatik", "piper", "cevrimdisi"):
        EKRAN.durum("baslatiliyor", "Türkçe ses hazırlanıyor…")
        _piper_yukle()
    konus(selamlama())
    EKRAN.durum("bekliyor", f"“{'Hey Jarvis' if uyanma else 'Jarvis'}” de ya da aşağıya yaz")

    def dinle_ve_calistir(bekleme=6):
        EKRAN.durum("dinliyor")
        komut = kulak.yaziya_cevir(kulak.cumle_kaydet(bekleme=bekleme))
        if not komut:
            EKRAN.durum("bekliyor")
            return None
        return komut_calistir(komut, beyin)

    while True:
        try:
            kapanacak = None
            if uyanma:
                kulak.temizle()
                uyanma.sifirla()
                while not MANUEL.is_set() and not uyanma.duydu_mu(kulak.parca()):
                    pass
                MANUEL.clear()
                log("Uyandım!")
                bip()
                kapanacak = dinle_ve_calistir()
            else:
                metin = kulak.yaziya_cevir(kulak.cumle_kaydet(bekleme=0, en_uzun=10))
                if MANUEL.is_set():
                    MANUEL.clear()
                    bip()
                    kapanacak = dinle_ve_calistir()
                elif metin:
                    var, kalan = uyanma_kelimesi_ayikla(metin)
                    if not var:
                        continue
                    log("Uyandım!")
                    bip()
                    kapanacak = komut_calistir(kalan, beyin) if kalan else dinle_ve_calistir()
                else:
                    continue

            if kapanacak is None:
                bip(False)
                continue
            if kapanacak:
                kapan()

            # Kısa takip: cevaptan sonra 4 sn içinde konuşursan yeniden 'Jarvis' demene gerek yok
            while True:
                EKRAN.durum("dinliyor", "Devam edebilirsin…")
                takip = kulak.yaziya_cevir(kulak.cumle_kaydet(bekleme=4))
                if not takip:
                    EKRAN.durum("bekliyor")
                    break
                if komut_calistir(takip, beyin):
                    kapan()
        except KeyboardInterrupt:
            break
        except Exception as e:
            log("Beklenmedik hata:", e)
            EKRAN.durum("bekliyor")
            time.sleep(1)


# ----------------------------------------------------------------------------
# HUD penceresi
# ----------------------------------------------------------------------------

class EkranAPI:
    """hud.html içindeki JavaScript'in çağırdığı fonksiyonlar."""

    def __init__(self, beyin):
        self._beyin = beyin
        self._hazir = threading.Event()

    def hazir(self):
        self._hazir.set()

    def komut(self, metin):
        def _is():
            if komut_calistir(metin, self._beyin):
                kapan()
        threading.Thread(target=_is, daemon=True).start()

    def dinle(self):
        MANUEL.set()


def hud_baslat(beyin):
    import webview
    api = EkranAPI(beyin)
    tam_ekran = AYAR.get("TAM_EKRAN", "hayir").lower() in ("evet", "1", "true")
    pencere = webview.create_window(
        "J.A.R.V.I.S.", url=os.path.join(KLASOR, "hud.html"), js_api=api,
        width=1280, height=760, min_size=(720, 520), background_color="#02070d",
        fullscreen=tam_ekran)

    def _arka_plan():
        api._hazir.wait(15)
        EKRAN.pencere = pencere
        arka_plan_islerini_baslat(beyin)

    webview.start(lambda: threading.Thread(target=_arka_plan, daemon=True).start())
    os._exit(0)


def arka_plan_islerini_baslat(beyin):
    """Ekran açıldıktan sonra: bilgiler, sistem istatistikleri, hava, dinleme."""
    ses_adi = AYAR["SES"].split("-")[-1].replace("Neural", "")
    EKRAN.veri("setInfo", {
        "beyin": ("Claude · " + AYAR["MODEL"].replace("claude-", "").split("-")[0].title()) if beyin.aktif else "Temel mod",
        "ses": ses_adi})
    EKRAN.veri("setStats", sistem_bilgisi())

    def _istatistik():
        while True:
            EKRAN.veri("setStats", sistem_bilgisi())
            time.sleep(2)

    def _hava():
        while True:
            time.sleep(15 * 60)
            h = hava_bilgisi()
            if h:
                EKRAN.veri("setWeather", h)

    threading.Thread(target=_istatistik, daemon=True).start()
    threading.Thread(target=_hava, daemon=True).start()
    ses_dongusu(beyin)


def seffaf_baslat(beyin):
    """Masaüstünün üstünde şeffaf Jarvis katmanı."""
    global EKRAN
    konum = AYAR.get("KONUM", "sag-alt") or "sag-alt"
    try:
        from parlak_ekran import ParlakEkran
        ekran = ParlakEkran(konum=konum, konum_dosyasi=os.path.join(KLASOR, "konum.txt"))
    except Exception as e:
        log("Parlak arayüz yüklenemedi, sade şeffaf arayüze geçiyorum:", e)
        from seffaf_ekran import SeffafEkran
        try:
            saydamlik = float(AYAR.get("SAYDAMLIK", "0.92") or 0.92)
        except ValueError:
            saydamlik = 0.92
        ekran = SeffafEkran(konum=konum, saydamlik=saydamlik)
    EKRAN = ekran

    def _komut(metin):
        def _is():
            if komut_calistir(metin, beyin):
                kapan()
        threading.Thread(target=_is, daemon=True).start()

    ekran.on_komut = _komut
    ekran.on_dinle = MANUEL.set
    ekran.on_kapat = lambda: threading.Thread(target=lambda: (konus(f"Görüşürüz {HITAP}."), kapan()), daemon=True).start()
    ekran.on_hazir = lambda: threading.Thread(target=arka_plan_islerini_baslat, args=(beyin,), daemon=True).start()
    ekran.calistir()   # pencere kapanana kadar burada kalır
    os._exit(0)


def kayit_dosyasina_yonlendir():
    """Pencere olmadan (pythonw) çalışırken çıktıları jarvis_kayit.txt dosyasına yazar."""
    if sys.stdout is not None and "pythonw" not in os.path.basename(sys.executable).lower():
        return
    yol = os.path.join(KLASOR, "jarvis_kayit.txt")
    try:
        if os.path.exists(yol) and os.path.getsize(yol) > 2_000_000:
            os.replace(yol, yol + ".eski")
        f = open(yol, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = f
    except Exception:
        pass


def tek_kopya():
    """Jarvis zaten açıksa ikinciyi başlatma. Açık değilse True."""
    if sys.platform != "win32":
        return True
    import ctypes
    global _KOPYA_KILIDI
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateMutexW.restype = ctypes.c_void_p
    _KOPYA_KILIDI = k32.CreateMutexW(None, False, "Local\\JarvisTekKopya")
    return ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS


def main():
    kayit_dosyasina_yonlendir()
    if "--yazi" not in sys.argv and not tek_kopya():
        print("Jarvis zaten açık.")
        return
    if sys.platform == "win32" and bilgisayar:
        bilgisayar.dpi_ayarla()
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    print("=" * 50)
    print("  J.A.R.V.I.S.  -  Türkçe sesli asistan")
    print("=" * 50)
    global BEYIN
    beyin = BEYIN = Beyin()
    log("Yapay zekâ beyni:", "AÇIK (" + AYAR["MODEL"] + ")" if beyin.aktif else "KAPALI (sadece temel komutlar)")
    if YAZI_MODU:
        yazi_dongusu(beyin)
        return
    arayuz = AYAR.get("ARAYUZ", "seffaf").lower()
    if "--konsol" in sys.argv:
        arayuz = "konsol"
    elif "--pencere" in sys.argv:
        arayuz = "pencere"
    if arayuz == "seffaf":
        try:
            seffaf_baslat(beyin)
            return
        except Exception as e:
            log("Şeffaf ekran açılamadı, pencereli ekrana geçiyorum:", e)
            global EKRAN
            EKRAN = Ekran()
            arayuz = "pencere"
    if arayuz == "pencere":
        try:
            hud_baslat(beyin)
            return
        except Exception as e:
            log("Ekran açılamadı, konsol modunda devam ediyorum:", e)
    ses_dongusu(beyin)


if __name__ == "__main__":
    main()
