# 🤖 Türkçe J.A.R.V.I.S.

Windows için **Türkçe sesli asistan**. "Hey Jarvis" de, ne istediğini söyle; saati söyler, uygulama açar, müzik çalar, hatırlatma kurar, görsel çizer. İstersen yapay zekâ beyniyle her soruna cevap verir, ekranına bakar, hatta fareyi ve klavyeyi kullanarak senin yerine iş yapar.

Masaüstünün üstünde **şeffaf bir arayüzle** çalışır: köşede dönen bir reaktör, sağ üstte saat, hava durumu ve sistem bilgisi. Arkadaki pencerelerini kapatmaz.

---

## ✨ Neler yapabilir?

| | |
|---|---|
| 🕐 **Temel komutlar** | Saat, tarih, hava durumu, işlemci/bellek/pil durumu |
| 🚀 **Uygulama açma** | Chrome, WhatsApp, Telegram, hesap makinesi, Gmail... |
| 🎵 **Müzik** | "YouTube'da Tarkan aç", sesi aç/kıs, sonraki şarkı |
| 🔎 **Arama** | "Google'da Dubai vize ücreti ara" |
| ⏰ **Hatırlatma ve not** | "10 dakika sonra annemi aramayı hatırlat", "Not al..." |
| 🎨 **Görsel çizme** | "Bana deniz kenarında bir otel çiz" (ücretsiz, anahtar gerekmez) |
| 🧠 **Yapay zekâ beyni** | Her soruya cevap, mesaj yazma, fikir verme *(API anahtarı gerekir)* |
| 👀 **Ekranı görme** | "Ekranımda ne var?", "Bu mesaja ne cevap vereyim?" *(API anahtarı gerekir)* |
| 🖱️ **Bilgisayarı kullanma** | "Chrome'da yeni sekme aç ve hava durumunu ara" *(API anahtarı gerekir)* |
| 🔇 **İnternetsiz ses** | Bilgisayarda çalışan Türkçe erkek sesi (Piper) |

---

## 💻 Gereksinimler

- **Windows 10 veya 11** (64-bit)
- Mikrofon (laptopun kendi mikrofonu yeter)
- İnternet (kurulum için; çevrimdışı ses ve Whisper kurulursa günlük kullanımda çoğu şey internetsiz çalışır)
- Python'a gerek yok, kurulum kendisi yükler

---

## 📥 İndirme ve kurulum

1. Bu sayfanın üstündeki yeşil **`<> Code`** düğmesine tıkla, **Download ZIP**'i seç.
2. İnen ZIP dosyasına sağ tıkla, **Tümünü ayıkla** de. Klasörü kalıcı bir yere koy (ör. `Belgeler\Jarvis`).
3. Klasördeki **`Kurulum.bat`** dosyasına çift tıkla.
   - Python yoksa kendisi yükler, gerekli paketleri indirir (5-10 dakika sürebilir).
   - Windows *"Bilgisayarınız korundu"* uyarısı verirse **Ek bilgi → Yine de çalıştır** de.
4. **(Önerilir)** `Turkce Ses Kur.bat` → internetsiz Türkçe erkek sesini kurar (~63 MB).
5. **(Önerilir)** `Gelismis Ses Tanima Kur.bat` → Whisper ses tanımayı kurar (~480 MB). Seni çok daha doğru anlar.
6. Masaüstünde oluşan **Jarvis** kısayoluna çift tıkla. Hepsi bu! 🎉

---

## 🧠 Yapay zekâ beynini açmak (isteğe bağlı)

Anahtarsız da temel komutların hepsi çalışır. Her şeyi sorabilmek, ekranı gösterebilmek ve bilgisayarı kullandırabilmek için:

1. [console.anthropic.com](https://console.anthropic.com) adresinden bir **Claude API anahtarı** al (`sk-ant-...` ile başlar). Kullandıkça ücretlidir.
2. `ayarlar.txt` dosyasını Not Defteri ile aç, şu satıra yapıştır:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```
3. Jarvis'i kapatıp yeniden aç.

> ⚠️ API anahtarını kimseyle paylaşma, GitHub'a yükleme.

---

## 🎙️ Kullanım

- **"Hey Jarvis"** de, bip sesinden sonra komutunu söyle.
- Cevaptan sonra 4 saniye içinde konuşursan tekrar "Hey Jarvis" demene gerek yok.
- **Reaktör:** sol tık = dinle, sağ tık = menü (komut yaz / paneli gizle / kapat), sürükle = taşı.
- **Renkler:** mavi = dinliyor, turuncu = düşünüyor, kırmızı = sorun var.
- **Kapatmak için:** "Görüşürüz" de ya da reaktöre sağ tık → Jarvis'i kapat.
- Siyah pencereli yazı modu için `Jarvis Yazi Modu.bat`.

### Örnek komutlar
```
Saat kaç?                         Hava nasıl? / İstanbul'da hava nasıl?
Chrome'u aç                       WhatsApp aç
YouTube'da Sezen Aksu aç          Sesi kıs / Müziği durdur
Google'da en yakın eczane ara     Ekran görüntüsü al
15 dakika sonra çayı hatırlat     Not al yarın faturayı öde
Bana bir kedi çiz                 Bilgisayarı kilitle
```
API anahtarı eklediysen:
```
Ekranımda ne var?
Bu mesaja kibar bir cevap yaz
Chrome'da yeni sekme aç ve Roma'daki müzeleri ara
```

### 🛑 Bilgisayar kontrolünde acil durdurma
Jarvis fareyi/klavyeyi kullanırken durdurmak için **fareyi ekranın sol üst köşesine götür** ya da **Esc'yi basılı tut**. Ödeme, şifre, kalıcı silme gibi işlerde önce sana sorar. İstemiyorsan `ayarlar.txt` içinde `BILGISAYAR_KONTROL=hayir` yap.

---

## ⚙️ Ayarlar (`ayarlar.txt`)

| Ayar | Ne işe yarar |
|---|---|
| `HITAP` | Sana nasıl hitap etsin (efendim, patron, adın...) |
| `SEHIR` | Hava durumu şehri (boş = otomatik) |
| `ARAYUZ` | `seffaf` / `pencere` / `konsol` |
| `SES_MOTORU`, `SES`, `SES_HIZI` | Ses seçimi ve konuşma hızı |
| `EKRANI_GOR` | Her soruda ekrana baksın mı |
| `BILGISAYAR_KONTROL` | Fare/klavye kullanabilsin mi |
| `UYANMA_HASSASIYETI` | 0.3 kolay uyanır – 0.7 zor uyanır |
| `MIKROFON` | Hangi mikrofonu kullansın |
| `TANIMA`, `TANIMA_MODELI` | Ses tanıma motoru (Whisper / Google) |

Bir ayarı değiştirince Jarvis'i kapatıp yeniden aç.

---

## 🛠️ Sorun çözme

- **Beni duymuyor:** Windows Ayarlar → Gizlilik → Mikrofon izinlerini aç. Gerekirse `ayarlar.txt` içinde `MIKROFON=` satırına mikrofonunun numarasını ya da adını yaz.
- **Zor uyanıyor:** `UYANMA_HASSASIYETI=0.35` yap. **Kendi kendine uyanıyor:** `0.65` yap.
- **"Hey Jarvis" hiç çalışmıyor:** `UYANMA_YONTEMI=kelime` yap, cümlede "Jarvis" demen yeter ("Jarvis saat kaç").
- **Başka bir sorun:** Klasördeki `jarvis_kayit.txt` dosyasına bak, hata orada yazar.

---

Daha ayrıntılı Türkçe anlatım için klasördeki **`BENIOKU.txt`** dosyasına bakabilirsin.
