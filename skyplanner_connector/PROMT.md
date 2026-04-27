# PROMPT.md — SkyPlanner APS Connector Kurulum, Kod İnceleme ve Test Talimatı

## 0. Rolün
Sen deneyimli bir **Odoo 17 Developer / Technical Consultant** gibi davran.
Amacın, verilen `skyplanner_connector_final.zip` içindeki Odoo modülünü test/staging ortamına kurmak, kod yapısını incelemek, eksik/hatalı noktaları düzeltmek ve QA testlerini çalıştırılabilir hale getirmektir.

Bu iş canlı ortamda yapılmayacak. Önce sadece test/staging/lokal Odoo 17 ortamında çalışılacak.

---

## 1. Proje Özeti
Bu modülün amacı, **Odoo 17 MRP** ile **SkyPlanner APS** arasında çift yönlü planlama entegrasyonu kurmaktır.

Temel akış:

1. Odoo Manufacturing Order oluşturulur.
2. Work Orders oluşur.
3. MO, SkyPlanner APS'e gönderilir.
4. SkyPlanner finite capacity scheduling yapar.
5. Odoo planı geri alır.
6. Kullanıcı onayıyla planlanan başlangıç/bitiş tarihleri Odoo workorder kayıtlarına yazılır.

Kritik tasarım kuralı:

> SkyPlanner sadece plan önerir. Odoo execution state her zaman korunur. `progress` veya `done` durumundaki workorder kayıtları asla overwrite edilmez. `Apply Plan` otomatik cron ile çalışmamalı, sadece explicit kullanıcı aksiyonuyla çalışmalıdır.

---

## 2. Kullanılacak Dosya
Sadece şu ZIP kullanılacak:

```text
skyplanner_connector_final.zip
```

Aşağıdaki dosyalar arşiv/yedek kabul edilecek, kuruluma dahil edilmeyecek:

```text
skyplanner_connector.zip
skyplanner_connector_v2.zip
skyplanner_connector_v3.zip
skyplanner_connector_v4.zip
```

---

## 3. Beklenen Odoo Addon Yapısı
ZIP açıldığında beklenen klasör yapısı:

```text
skyplanner_connector/
├── __init__.py
├── __manifest__.py
├── controllers/
├── data/
├── jobs/
├── models/
├── security/
├── services/
├── tests/
├── views/
└── wizard/
```

Önce bu yapı doğrulanmalı. Eksik dosya/klasör varsa raporlanmalı.

---

## 4. Ortam Gereksinimleri
Kurulum yapılacak ortamda şunlar olmalı:

```text
Odoo 17.0 Community veya Enterprise
Python 3.10+
PostgreSQL 14+
MRP / Manufacturing app aktif
SkyPlanner test hesabı
SkyPlanner API token
SkyPlanner Base URL
Default Customer ID
```

Python bağımlılığı:

```bash
pip install requests
```

Doğrulama:

```bash
python3 -c "import requests; print(requests.__version__)"
```

---

## 5. OCA queue_job Kurulumu
Bu modül `queue_job` bağımlılığı kullanır. Önce OCA queue kurulmalıdır.

Örnek kurulum:

```bash
cd /opt/odoo/custom

git clone https://github.com/OCA/queue.git --branch 17.0 queue
```

`odoo.conf` içinde addons path güncellenmeli:

```ini
addons_path = /opt/odoo/addons,/opt/odoo/custom/queue,/opt/odoo/custom
```

Önerilen worker ayarı:

```ini
workers = 2
max_cron_threads = 1
```

Odoo restart:

```bash
sudo systemctl restart odoo
```

Sonra Odoo içinde:

```text
Apps → Update Apps List → queue_job install
```

Eğer `Module Not Found: queue_job` hatası alınırsa:

1. OCA queue klasörü doğru yerde mi kontrol et.
2. `addons_path` içinde `/opt/odoo/custom/queue` var mı kontrol et.
3. Odoo restart edildi mi kontrol et.
4. Apps list güncellendi mi kontrol et.
5. Önce `queue_job`, sonra `skyplanner_connector` kurulmalı.

---

## 6. SkyPlanner Connector Kurulumu
Modül ZIP dosyası custom addons altına çıkarılmalı:

```bash
unzip skyplanner_connector_final.zip -d /opt/odoo/custom/
```

Klasör kontrolü:

```bash
ls /opt/odoo/custom/skyplanner_connector/
```

Odoo restart:

```bash
sudo systemctl restart odoo
```

Odoo içinde:

```text
Apps → Update Apps List
SkyPlanner APS Connector → Activate
```

Kurulum sırasında bağımlılık, manifest, XML, security veya Python hatası alınırsa:

1. Hata mesajını aynen raporla.
2. İlgili dosyayı bul.
3. Odoo 17 uyumluluğunu kontrol et.
4. Düzeltme önerisini ver.
5. Gerekirse patch üret.

---

## 7. Settings Yapılandırması
Kurulumdan sonra şu menüden ayarlar yapılmalı:

```text
Settings → SkyPlanner APS
```

Doldurulacak alanlar:

| Alan | Değer |
|---|---|
| API Token | SkyPlanner tarafından verilen token |
| Base URL | `https://{site}.skyplanner.app/production-planning/api/v3` |
| Default Customer ID | `/customers` GET cevabındaki müşteri ID |
| API Timeout | 30 |
| Auto Export after Push | İlk testte False |

Kritik header kuralı:

```text
Authorization-Token kullanılacak.
Authorization: Bearer kullanılmayacak.
```

Yani API çağrıları şu mantıkla yapılmalı:

```http
Authorization-Token: {api_token}
```

---

## 8. Default Customer ID Bulma
Default Customer ID SkyPlanner API üzerinden bulunur:

```text
SkyPlanner UI → API Documentation → /customers → GET
```

Response içindeki `id` değeri alınır ve Odoo Settings → SkyPlanner APS → Default Customer ID alanına girilir.

Eğer `ValueError: No SkyPlanner customer ID` hatası alınırsa bu alan eksiktir.

---

## 9. Workcenter Sync Akışı
MO push yapmadan önce ilgili workcenter kayıtları SkyPlanner'a sync edilmelidir.

Odoo yolu:

```text
Manufacturing → Configuration → Workcenters
```

Her workcenter için iki SkyPlanner kaydı gerekir:

| Tip | Endpoint | Açıklama |
|---|---|---|
| Workstation | `/workstations` | Fiziksel makine/kaynak |
| Workstage | `/workstages` | Süreç tipi, örn. Kaynak, Montaj |

Tek workcenter sync adımları:

1. Workcenter aç.
2. SkyPlanner APS sekmesine git.
3. External ID Workstation gir: örn. `WC-KAYNAK-01`.
4. Workstage Name gir: örn. `Kaynak`.
5. `1. Sync Workstation` butonuna bas.
6. `2. Sync Workstage` butonuna bas.
7. `APS Ready = True` olduğunu kontrol et.

Beklenen sonuç:

```text
SkyPlanner Workstation ID > 0
SkyPlanner Workstage ID > 0
APS Ready = True
```

Kritik kural:

> Workstation ve Workstage sync edilmeden MO push yapılmamalıdır. APS Ready false ise push engellenmelidir.

---

## 10. Normal Kullanım Akışı
Ana kullanıcı akışı şu şekilde olmalı:

1. MO oluştur.
2. MO confirm et.
3. Workorder kayıtları oluştu mu kontrol et.
4. MO formunda `Send to APS` butonuna bas.
5. APS Status `Sent` olmalı.
6. SkyPlanner tarafında MO/order görünmeli.
7. Export yap.
8. SkyPlanner Gantt üzerinde planlama yap.
9. Odoo MO üzerinde `Get Plan` butonuna bas.
10. Wizard içinde `Load Plan` ile planı görüntüle.
11. Simulate sırasında Odoo tarihleri değişmemeli.
12. `Apply Plan` butonuna bas.
13. Queue job çalışmalı.
14. Workorder `date_planned_start` ve `date_planned_finished` güncellenmeli.
15. `progress` ve `done` durumundaki workorder kayıtları değişmemeli.

---

## 11. APS Status Değerleri
Beklenen status değerleri:

| Değer | Anlamı |
|---|---|
| `not_sent` | Henüz gönderilmedi |
| `sent` | SkyPlanner'a gönderildi |
| `exported` | Production Planning'e aktarıldı |
| `planned` | Plan alındı, simulate edildi |
| `applied` | Plan Odoo'ya yazıldı |
| `error` | Hata oluştu |

---

## 12. Manuel QA Testleri
Aşağıdaki testler sırayla uygulanmalı ve her biri için sonuç raporlanmalı.

### T-01 — API Bağlantı Testi
Amaç: Geçerli/geçersiz token davranışını doğrulamak.

Adımlar:

1. Settings → SkyPlanner APS içinde API Token alanına yanlış token gir.
2. Bir workcenter üzerinde `Sync Workstation` dene.
3. 401 hatasını gör.
4. Doğru tokenı geri gir.
5. Tekrar sync dene.

Beklenen:

```text
Yanlış token → HTTP 401 Authentication failed
Doğru token → Success
Sync Logs içinde error ve success kayıtları oluşur
```

### T-02 — Workcenter Sync
Amaç: Workstation + Workstage sync doğrulaması.

Beklenen:

```text
SkyPlanner Workstation ID > 0
SkyPlanner Workstage ID > 0
APS Ready = True
```

### T-03 — Workstage Deduplication
Amaç: Aynı Workstage Name ile duplicate oluşmamalı.

Adımlar:

1. İkinci workcenter oluştur/aç.
2. Aynı Workstage Name gir.
3. Aynı Workstage External ID kullan.
4. Sync et.

Beklenen:

```text
İki workcenter aynı skyplanner_workstage_id değerini kullanmalı
SkyPlanner tarafında aynı workstage ikinci kez oluşmamalı
```

### T-04 — MO Push / Send to APS
Amaç: Manufacturing Order'ın SkyPlanner'a gönderilmesini test etmek.

Ön koşul:

```text
En az 1 APS Ready workcenter
Confirmed MO
Workorder kayıtları oluşmuş
```

Beklenen:

```text
APS Status = Sent
SkyPlanner Order ID > 0
Her workorder için SkyPlanner Phaser Job ID > 0
Sync Logs success kayıtları oluşur
```

### T-05 — Export
Amaç: MO'nun SkyPlanner Production Planning/Gantt tarafında görünmesini test etmek.

Beklenen:

```text
APS Status = Exported
/phaser-orders/export endpoint success
SkyPlanner Gantt'ta process step görünür
```

### T-06 — Get Plan / Simulate
Amaç: Planlanan tarihleri Odoo'ya yazmadan görüntülemek.

Ön koşul:

```text
SkyPlanner tarafında planlama yapılmış olmalı
```

Beklenen:

```text
Wizard satırları gelir
Mevcut Start / Planlı Start / Mevcut End / Planlı End görünür
Odoo workorder tarihleri değişmez
APS Status = Planned
```

### T-07 — Apply Plan / Write-back
Amaç: Planı Odoo workorder kayıtlarına yazmak.

Beklenen:

```text
Queue job çalışır
APS Status = Applied
Workorder planned start/end tarihleri güncellenir
skyplanner_plan_version artar
Progress/done workorder tarihleri değişmez
```

### T-08 — State Koruması
Amaç: Progress durumundaki workorder overwrite edilmemeli.

Beklenen:

```text
Progress workorder wizard'da Protected görünür
Apply sonrası tarihi değişmez
Diğer uygun workorder kayıtları güncellenir
```

### T-09 — Version Koruması
Amaç: Eski plan versiyonu apply edilmemeli.

Odoo shell örneği:

```python
wo = env["mrp.workorder"].browse(WORKORDER_ID)
wo.skyplanner_apply_dates("2025-01-01 08:00:00", "2025-01-01 10:00:00", 1)
```

Beklenen:

```text
Return value False olmalı
Tarihler değişmemeli
skyplanner_plan_version aynı kalmalı
```

### T-10 — Webhook Endpoint
Amaç: `/skyplanner/webhook` endpoint test edilmeli.

Curl örneği:

```bash
curl -X POST http://localhost:8069/skyplanner/webhook \
  -H "Content-Type: application/json" \
  -H "Authorization-Token: {api_token}" \
  -d '{"event":"plan_updated","external_id":"test-001","phaser_order_id":42}'
```

Beklenen:

```json
{"status": "ok", "event": "plan_updated"}
```

Aynı istek tekrar gönderilirse:

```json
{"status": "duplicate", "message": "Already processed"}
```

Geçersiz token ile:

```json
{"status": "error", "message": "Unauthorized"}
```

### T-11 — Error Path / Retry
Amaç: Hata alınca log yazılması ve sonra retry yapılabilmesi.

Adımlar:

1. API Token'ı geçici olarak boz.
2. MO üzerinde `Send to APS` bas.
3. Hata mesajını kontrol et.
4. APS Status `error` olmalı.
5. Sync Logs içinde error olmalı.
6. Tokenı düzelt.
7. Tekrar `Send to APS` bas.

Beklenen:

```text
İlk deneme error
Retry sonrası success
MO Last APS Error temizlenir
Silent fail olmaz
```

---

## 13. Otomatik Test Suite
Test komutu:

```bash
python odoo-bin -i skyplanner_connector \
  --test-enable \
  --test-tags=skyplanner_api,skyplanner_mapper,skyplanner_sync_log,skyplanner_planner \
  -d test_db --stop-after-init
```

Sadece mapper testleri:

```bash
python odoo-bin -i skyplanner_connector \
  --test-enable \
  --test-tags=skyplanner_mapper \
  -d test_db --stop-after-init
```

Beklenen:

```text
Ran 34 tests in X.XXXs
OK
```

Testler başarısız olursa:

1. Hangi testin düştüğünü yaz.
2. Stack trace'i özetle.
3. Kök nedeni açıkla.
4. İlgili dosyada düzeltme öner.
5. Gerekirse patch hazırla.

---

## 14. Sık Hata Kontrol Listesi

| Hata | Muhtemel neden | Çözüm |
|---|---|---|
| `Module Not Found: queue_job` | OCA queue yok veya addons_path eksik | queue 17.0 branch ekle, restart, Apps update |
| `HTTP 401` | Token yanlış | API Token kontrol et, Authorization-Token header kullanılmalı |
| `HTTP 403` | SkyPlanner scheduling API kapalı | SkyPlanner support ile görüş |
| `No SkyPlanner customer ID` | Default Customer ID boş | `/customers` GET ile ID al |
| `Workcenter has no Workstage ID` | Workcenter sync eksik | Workstation + Workstage sync yap |
| `Apply Plan çalışmıyor` | queue_job worker çalışmıyor | workers, queue_job, failed jobs kontrol et |
| Planned date gelmiyor | Export veya schedule yapılmamış | Export + SkyPlanner Gantt planlama kontrol et |

---

## 15. Log Kontrol Komutları
Odoo log:

```bash
tail -f /var/log/odoo/odoo.log | grep -i skyplanner
```

Odoo UI:

```text
Manufacturing → SkyPlanner APS → Sync Logs
```

Queue job:

```text
Manufacturing → Technical → queue_job → Jobs
```

Failed jobs filtrelenmeli.

---

## 16. Güvenlik ve Roller
Beklenen roller:

| Grup | Yetki |
|---|---|
| SkyPlanner User | MO görüntüleme, Send to APS, Get Plan, Sync Log okuma |
| SkyPlanner Manager | Apply Plan, workcenter sync, Settings yapılandırma, log silme |

Kritik:

```text
Apply Plan sadece SkyPlanner Manager grubuna görünmelidir.
Send to APS SkyPlanner User grubuna açık olabilir.
```

---

## 17. Production Öncesi Checklist
Canlıya geçmeden önce şu maddeler tamamlanmış olmalı:

```text
[ ] queue_job kurulu ve workers çalışıyor
[ ] skyplanner_connector_final.zip doğru addons klasöründe
[ ] requests Python env içinde mevcut
[ ] API Token dolu
[ ] Base URL dolu
[ ] Default Customer ID dolu
[ ] En az 1 workcenter APS Ready = True
[ ] T-01 API bağlantı testi başarılı
[ ] T-02 Workcenter sync başarılı
[ ] T-04 MO Send to APS başarılı
[ ] T-06 Get Plan simulate başarılı
[ ] T-07 Apply Plan başarılı
[ ] T-08 Progress/done state koruması başarılı
[ ] T-10 Webhook endpoint başarılı
[ ] Otomatik test suite başarılı
[ ] SkyPlanner Manager/User grupları doğru atanmış
[ ] Test sync logs temizlenmiş
[ ] Canlıya geçiş için onay alınmış
```

---

## 18. İstenen Çıktı Formatı
Bu işi yaparken her aşamada şu formatta rapor ver:

```markdown
# SkyPlanner Connector Kurulum/Test Raporu

## Ortam
- Odoo versiyonu:
- Python versiyonu:
- PostgreSQL versiyonu:
- DB adı:
- Branch / ortam:

## Kurulum Durumu
- queue_job:
- skyplanner_connector:
- requests:
- addons_path:

## Ayarlar
- Base URL:
- API Token: Girildi / Girilmedi
- Default Customer ID:
- Auto Export:

## Workcenter Sync
| Workcenter | Workstation ID | Workstage ID | APS Ready | Sonuç |
|---|---:|---:|---|---|

## MO Test
| MO | APS Status | SkyPlanner Order ID | Workorder Job IDs | Sonuç |
|---|---|---:|---|---|

## QA Testleri
| Test | Sonuç | Not |
|---|---|---|
| T-01 |  |  |
| T-02 |  |  |
| T-03 |  |  |
| T-04 |  |  |
| T-05 |  |  |
| T-06 |  |  |
| T-07 |  |  |
| T-08 |  |  |
| T-09 |  |  |
| T-10 |  |  |
| T-11 |  |  |

## Hatalar
| Hata | Kök Neden | Çözüm | Durum |
|---|---|---|---|

## Sonuç
- Canlıya hazır mı?
- Eksik kalan maddeler:
- Riskler:
- Önerilen sonraki adım:
```

---

## 19. Çalışma Prensibi
Kod değişikliği yapmadan önce:

1. Sorunu tespit et.
2. İlgili dosyayı belirt.
3. Nedenini açıkla.
4. Minimum değişiklikle çöz.
5. Test komutunu çalıştır.
6. Sonucu raporla.

Gereksiz refactor yapma.
Canlı veri üzerinde test yapma.
Token veya secret değerlerini loglara yazma.
Odoo execution state'i değiştiren otomatik cron yazma.
`progress` ve `done` workorder kayıtlarını overwrite etme.

---

## 20. İlk Yapılacak İş
Önce şunları kontrol et:

```text
1. Bu ortam gerçekten Odoo 17 mi?
2. queue_job kurulabiliyor mu?
3. skyplanner_connector_final.zip doğru açılıyor mu?
4. __manifest__.py içindeki bağımlılıklar Odoo 17 ile uyumlu mu?
5. Security CSV/XML dosyaları yükleniyor mu?
6. Views XML hatasız mı?
7. Settings alanları görünüyor mu?
8. Workcenter formunda SkyPlanner APS sekmesi görünüyor mu?
```

Bu 8 madde başarılı olmadan MO push testine geçme.
