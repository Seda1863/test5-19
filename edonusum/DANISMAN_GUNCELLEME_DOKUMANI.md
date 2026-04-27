# E-Dönüşüm Modülü V2 Güncelleme Dokümanı — Danışman Ekip

**Modül:** E-Dönüşüm (edonusum)  
**Platform:** Odoo 18  
**Güncellenme Tarihi:** Haziran 2025 (V2) / Nisan 2026 (V2.1 — Hata Yönetimi) / Temmuz 2025 (V2.2 — İrsaliye Güncellemeleri)  
**Referans Standart:** GIB UBL-TR 1.2.1 / Kod Listeleri V1.42  

---

## 1. Güncellemenin Amacı

Bu güncelleme, GIB'in (Gelir İdaresi Başkanlığı) Ocak 2025 tarihli e-Fatura standardı değişikliklerini Odoo sistemine entegre eder. Güncelleme sonrasında:

- **4 yeni senaryo** (İlaç/Tıbbi Cihaz, Yatırım Teşvik, İDİS, İDİS İrsaliye) desteklenir
- **6 yeni fatura tipi** (Teknoloji Desteği, YTB Satış/İade/İstisna/Tevkifat/Tevkifat İade) kullanılabilir
- GIB'in Schematron kurallarına tam uyum sağlanır
- Yanlış senaryo-tip kombinasyonu girişi engellenir
- Fatura XML'leri güncel standarda uygun üretilir

---

## 2. Yeni Senaryolar

### 2.1 İlaç ve Tıbbi Cihaz (ILAC_TIBBICIHAZ)

- **Ne zaman kullanılır:** İlaç veya tıbbi cihaz içeren faturalarda
- **Fark:** Eski İlaç/Tıbbi Cihaz senaryosu deaktif edilmiştir. Yeni sürüm GIB'in güncel gereksinimleriyle uyumludur
- **Gereksinimler:** En az bir fatura satırında ilaç/tıbbi cihaz türü ve karekod bilgisi girilmelidir

### 2.2 Yatırım Teşvik (YATIRIMTESVIK)

- **Ne zaman kullanılır:** Yatırım teşvik belgesi kapsamındaki alımlarda
- **Gereksinimler:** "Yatırım Teşvik Belgesi No" alanı zorunludur (Format: `B/yyy/nnn`)
- **Desteklenen tipler:** Satış, İstisna, İade, Tevkifat, Tevkifat İade
- **Satır bilgileri:** Harcama tipi kodu, makine adı, seri no, makine sicil no girilebilir

### 2.3 İDİS (İthalatta Damga Vergisi İstisna Sistemi)

- **Ne zaman kullanılır:** İDİS kapsamındaki ithalat faturalarında
- **Gereksinimler:** "Sevkiyat No" alanı zorunludur (Format: `SE-nnnnnnn`)
- **Satır bilgileri:** Her satır için etiket numarası girilebilir

### 2.4 İDİS İrsaliye (IDISIRSALIYE)

- **Ne zaman kullanılır:** İDİS kapsamındaki irsaliye faturalarında
- **Gereksinimler:** İDİS ile aynı

---

## 3. Yeni Fatura Tipleri

| Tip | Açıklama | Kullanım Alanı |
|-----|----------|----------------|
| **Teknoloji Geliştirme Desteği** | TEKNOLOJIDESTEK | Teknolojik ürün desteği kapsamındaki faturalar |
| **YTB Satış** | Yatırım Teşvik kapsamında satış | e-Arşiv faturalarda |
| **YTB İade** | Yatırım Teşvik kapsamında iade | e-Arşiv faturalarda |
| **YTB İstisna** | Yatırım Teşvik kapsamında istisna | e-Arşiv faturalarda |
| **YTB Tevkifat** | Yatırım Teşvik kapsamında tevkifat | e-Arşiv faturalarda |
| **YTB Tevkifat İade** | Yatırım Teşvik kapsamında tevkifat iade | e-Arşiv faturalarda |

> **Not:** YTB fatura tipleri sadece **e-Arşiv** senaryosunda kullanılır. e-Fatura senaryolarında YATIRIMTESVIK senaryosu üzerinden standart tipler (SATIS, ISTISNA vb.) kullanılır.

---

## 4. Senaryo ile Tip Eşleşme Kuralları

Sistem artık yanlış senaryo-tip kombinasyonlarını otomatik olarak engeller. Aşağıdaki tablo hangi senaryoda hangi tiplerin kullanılabileceğini gösterir:

| Senaryo | Kullanılabilir Tipler |
|---------|----------------------|
| Ticari Fatura | Satış, Tevkifat, Tevkifat İade, İstisna, Özel Matrah, İhraç Kayıtlı |
| Temel Fatura | Satış, İade, Tevkifat, Tevkifat İade, İstisna, Özel Matrah, İhraç Kayıtlı |
| İhracat | Satış, İstisna |
| Kamu | Satış, İade, Tevkifat, Tevkifat İade, İstisna, Özel Matrah |
| Özel Fatura | Satış, İade, Tevkifat, Tevkifat İade, İstisna, Özel Matrah |
| Yolcu Beraber | Satış, İstisna |
| HKS | HKS Satış, HKS Komisyoncu |
| Enerji | Şarj, Şarj Anlık |
| İlaç/Tıbbi Cihaz | Satış, İstisna, Tevkifat, Tevkifat İade, İade, İhraç Kayıtlı |
| Yatırım Teşvik | Satış, İstisna, İade, Tevkifat, Tevkifat İade |
| İDİS | Satış, İstisna, İade, Tevkifat, Tevkifat İade, İhraç Kayıtlı |
| e-Arşiv Fatura | Tüm tipler (20 adet) |

> **Önemli:** Senaryo değiştirildiğinde, uyumsuz tip otomatik olarak temizlenir.

---

## 5. Yeni Alanlar — Fatura Ekranı

### 5.1 Senaryo Detayları Bölümü

Fatura formunda yeni bir "Senaryo Detayları" bölümü eklenmiştir. Alanlar ilgili senaryo seçildiğinde otomatik görünür olur:

| Alan | Görünürlük | Açıklama |
|------|-----------|----------|
| Yatırım Teşvik Belgesi No | YATIRIMTESVIK | Zorunlu — B/yyy/nnn formatında |
| İDİS Sevkiyat No | İDİS, İDİS İrsaliye | Zorunlu — SE-nnnnnnn formatında |
| Pasaport No | YOLCUBERABERFATURA | Yolcu pasaport numarası |
| Yolcu Uyruk | YOLCUBERABERFATURA | Yolcu uyruk bilgisi |
| Kamu IBAN | KAMU | Zorunlu — Ödeme IBAN bilgisi |

### 5.2 GIB İletim Durumu Bölümü

Fatura formunda iletim durumunu takip eden yeni bir bölüm:

| Alan | Açıklama |
|------|----------|
| İletim Durumu | Taslak → Gönderildi → Teslim Alındı → Kabul Edildi / Red Edildi / İptal (durum çubuğu) |
| İletim Tarihi | GIB'e gönderim zaman damgası |
| Red Nedeni | Sadece red durumunda görünür |
| XML Arşiv | Gönderilen XML'in indirilebilir kopyası |
| XML Hash | SHA-256 bütünlük doğrulaması |

### 5.3 Satır Alanları

Fatura satırlarına yeni kolonlar eklenmiştir (varsayılan olarak gizli, isteğe bağlı açılır):

| Alan | Kullanım |
|------|----------|
| İlaç/Tıbbi Cihaz Türü | İlaç / Tıbbi Cihaz seçimi |
| İlaç Karekod | ITS/ÜTS karekod |
| YTB Harcama Tipi | Yatırım teşvik harcama tipi kodu |
| Makine Adı | Makine/Teçhizat adı |
| Makine Seri No | Seri numarası |
| Makine Sicil No | Sicil numarası |
| İDİS Etiket No | İDİS etiket numarası |
| Teknoloji Cihaz Tipi | Bilgisayar/Tablet/Yazıcı/Diğer |
| IMEI/Seri No | Teknoloji cihaz IMEI veya seri no |
| HKS Künye No | HKS künye numarası |
| Satıcı DİB Satır Kodu | İhraç kayıtlı DİB satır kodu |
| Alıcı DİB Satır Kodu | İhraç kayıtlı DİB satır kodu |

---

## 6. Şirket Ayarları

Şirket ayarlarına yeni bölümler eklenmiştir:

### 6.1 E-Dönüşüm Ek Ayarları

- **KDV Tevkifat Alt Sınır:** Varsayılan 6.900 TL. Her yıl Maliye Bakanlığı tarafından güncellenen tutar buraya girilir.

### 6.2 QNB eFinans Bağlantı Ayarları

- **Test Modu:** Açık/Kapalı — test ortamında çalışmak için açılır
- **Test URL:** QNB test ortamı adresi
- **Üretim URL:** QNB canlı ortam adresi

---

## 7. Otomatik Kontroller (Validasyonlar)

Fatura onaylanırken (`Onayla` butonuna basıldığında) aşağıdaki kontroller otomatik çalışır:

| Kontrol | Hata Durumunda Mesaj |
|---------|---------------------|
| Senaryo-Tip uyumu | "Geçersiz senaryo-tip kombinasyonu" |
| KAMU → IBAN zorunlu | "KAMU senaryosunda IBAN zorunludur" |
| İade tipleri → Referans fatura zorunlu | "İade faturalarında referans fatura bilgisi zorunludur" |
| SGK → alıcı VKN kontrolü | "SGK faturalarında alıcı VKN 7640235439 olmalıdır" |
| Teknoloji Desteği → TCKN zorunlu | "TEKNOLOJIDESTEK faturalarında alıcı TCKN zorunludur" |
| Yatırım Teşvik → Belge No zorunlu | "YATIRIMTESVIK senaryosunda YTB No zorunludur" |
| İDİS → Sevkiyat No zorunlu | "İDİS senaryosunda Sevkiyat No zorunludur" |
| İstisna → İstisna kodu zorunlu | "İSTİSNA faturalarında istisna kodu zorunludur" |
| İhraç Kayıtlı kontrolleri | İhracat ile ilgili ek kontroller |
| Konaklama Vergisi → 0059 kodu zorunlu | "KonaklamaVergisi faturalarında 0059 vergi kodu zorunludur" |

---

## 8. Süre Aşımı Otomatik Kontrolü

VUK Madde 231/5 uyarınca, fatura düzenlenme tarihinden itibaren 7 gün içinde GIB'e gönderilmesi gerekmektedir. Sistem her gün otomatik olarak:

- 7 günü geçen gönderilmemiş faturaları tespit eder
- Bu faturaları "Süre Aşımı" olarak işaretler
- Sistem loglarına uyarı kaydeder

---

## 9. Değişiklik Özeti

| Alan | Önceki Durum | Yeni Durum |
|------|-------------|-----------|
| Desteklenen senaryolar | 8 | **12** (4 yeni) |
| Desteklenen fatura tipleri | 16 | **22** (6 yeni) |
| Matris validasyon | Yoktu | **12×22 matris aktif** |
| Senaryo bazlı zorunlu alanlar | Kısıtlı | **5 yeni koşullu alan** |
| Satır detay alanları | Kısıtlı | **14 yeni alan** |
| GIB iletim takibi | Temel | **6 durumlu tam takip** |
| XML doğruluğu | Temel | **Sanitizasyon + 2 ondalık yuvarlama** |
| QNB hata yönetimi | Temel | **Retry mekanizması + Türkçe hata kodları** |
| Yasal uyum | Manuel | **Otomatik süre aşımı kontrolü (VUK 231/5)** |
| E-Fatura hata takibi | Yoktu | **İşlem takip ekranı + hata banner + retry sistemi** |
| Gönderim öncesi kontrol | Kısıtlı | **14 kategoride kapsamlı ön doğrulama** |
| Seri numarası güvenliği | Temel | **Atomik seri tahsis/geri alma (hata durumunda numara kaybolmaz)** |
| Otomatik yeniden deneme | Yoktu | **4 kademeli otomatik retry (5, 15, 60, 240 dk)** |
| Günlük hata raporu | Yoktu | **Her gün 21:30'da yöneticilere hata özeti** |

---

## 10. Hata Yönetimi ve İşlem Takip Sistemi (V2.1 — Nisan 2026)

Bu güncelleme ile e-Fatura gönderim sürecine kapsamlı bir hata yönetimi altyapısı eklenmiştir.

### 10.1 Fatura Formundaki Yeni Özellikler

#### Hata Banner'ı

Fatura gönderiminde hata oluştuğunda, fatura formunun üst kısmında **kırmızı bir hata banner'ı** görüntülenir:

- Hata mesajı ve kodu gösterilir
- **"Tekrar Dene"** butonu — faturayı yeniden gönderme wizard'ını açar
- **"İşlem Geçmişi"** butonu — bu faturanın tüm gönderim denemelerini listeler

#### İşlem Geçmişi Smart Button

Fatura formunda yeni bir **"İşlem Geçmişi"** butonu eklenmiştir. Bu buton:
- Faturanın kaç kez gönderilmeye çalışıldığını gösterir
- Tıklandığında her denemenin detayını (tarih, sonuç, hata kodu) listeler

### 10.2 Gönderim Öncesi Otomatik Kontroller

**e-Fatura Gönder** butonuna basıldığında, fatura GIB'e gönderilmeden önce aşağıdaki kontroller yapılır:

| Kontrol Grubu | Kontrol Edilen | Hata Durumunda |
|---------------|---------------|----------------|
| **Şirket Bilgileri** | VKN, adres, ülke, şehir | "Gönderici firma ... bilgisi eksik" |
| **Müşteri Bilgileri** | VKN/TCKN, adres, şehir, ad | "Alıcı ... bilgisi eksik" |
| **Fatura Satırları** | Ürün adı, miktar, birim, fiyat | "Satır ... eksik veya sıfır" |
| **Vergi Bilgileri** | Vergi varlığı, istisna kodu | "Vergi bilgisi eksik" / "%0 KDV istisna kodu zorunlu" |
| **Seri** | Seri seçimi | "Fatura serisi seçilmemiş" |
| **Alıcı Kayıt Durumu** | e-Fatura mükellefiyeti | "Alıcı e-fatura mükellefi değil" |

> **Faydası:** Bu kontroller sayesinde, eksik bilgi nedeniyle GIB'den dönecek hatalar daha fatura gönderilmeden **kullanıcıya anında gösterilir**.

### 10.3 Seri Numarası Güvenliği

Eski sistemde, fatura gönderiminde hata oluştuğunda seri numarası "harcanmış" oluyordu. Yeni sistemde:

- Seri numarası **geçici olarak tahsis** edilir
- Gönderim **başarılı** olursa numara **onaylanır** (kalıcılaşır)
- Gönderimde **hata** olursa numara **geri alınır** (sırada bir sonraki faturaya verilir)
- Bu sayede **seri numarası boşlukları oluşmaz**

### 10.4 Otomatik Yeniden Deneme (Retry)

Bazı hatalar geçici niteliktedir (sunucu meşgul, bağlantı kopması vb.). Bu tür hatalar için sistem **otomatik yeniden deneme** yapar:

| Deneme | Bekleme Süresi |
|--------|---------------|
| 1. yeniden deneme | 5 dakika sonra |
| 2. yeniden deneme | 15 dakika sonra |
| 3. yeniden deneme | 60 dakika sonra |
| 4. yeniden deneme | 240 dakika (4 saat) sonra |

- 4 denemeden sonra başarısız olursa, servis sorumlusuna **bildirim** gönderilir
- Kalıcı hatalar (yanlış VKN, format hatası vb.) için **otomatik retry yapılmaz**

### 10.5 Manuel Yeniden Deneme

Otomatik retry yapılamayan veya 4 denemeyi aşan faturalar için **"Tekrar Dene" wizard'ı** kullanılabilir:

| Seçenek | Açıklama |
|---------|----------|
| **Yeni UUID Üret** | Faturaya yeni benzersiz numara verir (varsayılan: açık) |
| **Seri Numarasını Sıfırla** | Yeni seri numarası atar (varsayılan: kapalı) |
| **Tekrar Gönder** | Normal retry (yeniden denenebilir hatalar için) |
| **Zorla Gönder** | Koşulsuz gönderim (yeniden denenemez hatalar için — dikkatli kullanın!) |

### 10.6 İşlem Takip Ekranı

E-Dönüşüm menüsünde yeni bir **"İşlem Takip"** bölümü eklenmiştir:

#### E-Fatura İşlemleri
Tüm gönderim işlemlerinin listesi:
- **Yeşil**: Başarıyla gönderilmiş
- **Kırmızı**: Hatalı
- **Sarı**: Retry planlanmış
- Her kayıtta: belge referansı, hata kodu, deneme sayısı, bir sonraki deneme zamanı

#### Hata Kodları
157 adet GIB hata kodunun listesi:
- Kod, açıklama, kategori, ciddiyet seviyesi
- Hangi kodların otomatik retry yapılabilir olduğu

### 10.7 Günlük Hata Raporu

Her gün **saat 21:30**'da sistem otomatik olarak:
- O günkü hatalı işlemlerin özetini hazırlar
- Retry sonuçlarını derler
- **Yöneticilere e-posta olarak gönderir**

---

## 11. Dikkat Edilmesi Gerekenler

1. **Eski İlaç/Tıbbi Cihaz senaryosu** deaktif edilmiştir. Bu senaryoyu kullanan mevcut faturalar etkilenmez, ancak **yeni faturalarda güncel senaryo** kullanılmalıdır.

2. **YTB fatura tipleri** sadece e-Arşiv senaryosunda kullanılır; e-Fatura senaryolarında "Yatırım Teşvik" senaryosu seçilir.

3. **KDV Tevkifat Alt Sınır** değeri her yıl güncellenmektedir. Şirket ayarlarından kontrol ediniz.

4. **UUID benzersizlik** kontrolü eklenmiştir. Aynı UUID ile birden fazla fatura girilemez.

5. **Senaryo değiştirildiğinde** uyumsuz tip otomatik temizlenir — kullanıcı bilgilendirilir.

---

## 12. V2.2 — İrsaliye Tür ve Profil Güncellemeleri (Temmuz 2025)

### 12.1 Ne Değişti?

E-İrsaliye modülünde GIB standartlarına tam uyum sağlayan güncellemeler yapılmıştır:

| Değişiklik | Eski Durum | Yeni Durum |
|-----------|-----------|-----------|
| İrsaliye tip kodu | `MATBUUDAN` (hatalı yazım) | `MATBUDAN` (GIB standardı) |
| Senaryo-tip kontrolü | Kontrol yok | Otomatik validasyon |
| Matbu belge alanları | Opsiyonel | MATBUDAN seçildiğinde zorunlu |
| HKSIRSALIYE ek alanlar | Yok | Her satırda Künye No zorunlu |
| IDISIRSALIYE ek alanlar | Yok | Sevkiyat No + her satırda Etiket No zorunlu |

### 12.2 İrsaliye Senaryoları ve Kullanılabilir Tipler

| Senaryo | Açıklama | Kullanılabilir Tipler |
|---------|----------|----------------------|
| **TEMELIRSALIYE** | Standart sevk irsaliyesi | Sevk (SEVK), Matbudan (MATBUDAN) |
| **HKSIRSALIYE** | Hal Kayıt Sistemi irsaliyesi | Sevk (SEVK), Matbudan (MATBUDAN) |
| **IDISIRSALIYE** | İDİS (İnşaat Demiri İzleme) irsaliyesi | Sevk (SEVK), Matbudan (MATBUDAN) |

### 12.3 MATBUDAN Tipi Kullanımı

**Ne zaman kullanılır:** Önceden basılmış (matbu) bir irsaliye belgesinin elektronik ortama aktarılması gerektiğinde.

**Zorunlu alanlar:**
- **Matbu Belge No**: Matbu irsaliyenin belge numarası
- **Matbu Belge Tarihi**: Matbu irsaliyenin düzenlenme tarihi

> **Not:** MATBUDAN tipi tüm irsaliye senaryolarında (TEMELIRSALIYE, HKSIRSALIYE, IDISIRSALIYE) kullanılabilir.

### 12.4 HKSIRSALIYE — Hal Kayıt Sistemi İrsaliyesi

**Ne zaman kullanılır:** Hal Kayıt Sistemi'ne kayıtlı ürünlerin sevkiyatında.

**Ek zorunluluklar:**
- Her irsaliye satırında (stok hareketi) **HKS Künye No** girilmelidir
- Künye numarası tam **19 karakter** olmalıdır

**Formda nerede:**
- İrsaliye satırının detay formunda "İrsaliye Satır Bilgileri" bölümünde görünür

### 12.5 IDISIRSALIYE — İDİS İrsaliyesi

**Ne zaman kullanılır:** İnşaat Demiri İzleme Sistemi kapsamındaki sevkiyatlarda.

**Ek zorunluluklar:**
- İrsaliye üzerinde **İDİS Sevkiyat No** girilmelidir (Format: `SE-0000001`)
- Her irsaliye satırında **İDİS Etiket No** girilmelidir (Format: 2 harf + 7 rakam, örn: `AB1234567`)

**Formda nerede:**
- Sevkiyat No → E-İrsaliye Bilgileri grubunda (sadece İDİS senaryosunda görünür)
- Etiket No → İrsaliye satırının detay formunda "İrsaliye Satır Bilgileri" bölümünde görünür

### 12.6 Otomatik Tip Temizleme

İrsaliye formunda **senaryo değiştirildiğinde**, uyumsuz bir tip seçili ise otomatik olarak **SEVK** tipine döndürülür.

### 12.7 Dikkat Edilmesi Gerekenler

1. **Mevcut kayıtlar:** Veritabanında `MATBUUDAN` kodlu irsaliyeler varsa, modül güncellemesi sonrası `MATBUDAN` olarak güncellenecektir.
2. **HKSIRSALIYE** seçildiğinde, tüm satırlarda künye numarası girilmeden irsaliye gönderilemez.
3. **IDISIRSALIYE** seçildiğinde, sevkiyat numarası ve tüm satırlarda etiket numarası girilmeden irsaliye gönderilemez.
4. **Matbu belge alanları** sadece MATBUDAN tipi seçildiğinde formda görünür hale gelir.
5. **Versiyon:** Bu güncelleme ile modül versiyonu `18.18.78` olmuştur.
