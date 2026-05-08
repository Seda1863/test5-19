# SkyPlanner Connector — Değişiklik Günlüğü

Modülün ilk commit'inden bugüne kadar yapılan tüm kod değişikliklerinin kronolojik kaydı.

---

## v19.0.1.0.0 — İlk Sürüm (2026-04-27)

**Commit:** `8b92bbc` — `feat: Add SkyPlanner APS Connector v19.0.1.0.0`

Modül sıfırdan oluşturuldu. Tüm dosyalar ilk kez eklendi.

### Eklenen Dosyalar

| Dosya | Açıklama |
|-------|----------|
| `__manifest__.py` | Modül tanımı, depends: `['mrp', 'queue_job']` |
| `services/api_client.py` | SkyPlanner REST client (`Authorization-Token` header, hata yönetimi) |
| `services/mapper.py` | Odoo → SkyPlanner payload builder; `extract_planned_dates()` |
| `services/planner.py` | Ana orkestrasyon: `push_production_order()`, `fetch_and_apply()` |
| `models/mrp_production.py` | `mrp.production` extend: APS alanları, Send/Get/Apply butonları |
| `models/mrp_workcenter.py` | `mrp.workcenter` extend: Workstation + Workstage sync |
| `models/skyplanner_sync_log.py` | Sync log modeli, webhook idempotency |
| `models/skyplanner_mapping.py` | Odoo ↔ SkyPlanner ID mapping tablosu |
| `models/res_config_settings.py` | Settings: API Token, Base URL, Customer ID, Timeout |
| `controllers/webhook.py` | `POST /skyplanner/webhook` endpoint |
| `jobs/sync_jobs.py` | Queue job sarmalayıcılar (`job_push_production_order`, `job_fetch_and_apply`) |
| `wizard/skyplanner_simulate_wizard.py` | Simulate wizard (HTML preview, yazma yok) |
| `views/mrp_production_views.xml` | MO formuna APS butonları + APS sekmesi |
| `views/mrp_workcenter_views.xml` | Workcenter formuna SkyPlanner APS sekmesi + sync butonları |
| `views/skyplanner_sync_log_views.xml` | Sync log list/form view |
| `views/skyplanner_mapping_views.xml` | Mapping tablosu view |
| `views/res_config_settings_views.xml` | Settings SkyPlanner APS bölümü |
| `views/skyplanner_menu.xml` | Manufacturing menüsü altına SkyPlanner menü ağacı |
| `security/skyplanner_groups.xml` | `group_skyplanner_user`, `group_skyplanner_manager` grupları |
| `security/ir.model.access.csv` | Model erişim hakları |
| `data/skyplanner_config_data.xml` | Varsayılan config parametreleri |

---

## Düzeltme — Odoo 19 Uyumluluğu (2026-04-30)

**Commit:** `7f2448c` — `Fix v19: skyplanner_connector - remove queue_job dep, fix groups_id, fix sync`

### `__manifest__.py`
- `depends` listesinden `queue_job` kaldırıldı.
  - **Neden:** OCA `queue_job` Odoo.sh'da submodule olmadan kurulu gelmiyor; modül install'da `Module Not Found` hatası veriyordu.

### `jobs/sync_jobs.py`
- `from odoo_jobs.RetryableJobError import ...` ve benzeri `queue_job`'a ait import'lar kaldırıldı.
- `with_delay()` çağrıları kaldırıldı; iş metodları senkron çalışacak şekilde düzenlendi.
  - **Neden:** `queue_job` bağımlılığı kaldırıldığı için bu import'lar modül yüklenirken `ImportError` veriyordu.

### `models/mrp_production.py`
- `action_apply_plan()` içinde `with_delay()` ile asenkron çağrı → doğrudan `planner.fetch_and_apply()` senkron çağrısına dönüştürüldü.

### `views/mrp_workcenter_views.xml`
- `ir.actions.server` kaydında `<field name="groups_id">` → `<field name="group_ids">` olarak güncellendi.
  - **Neden:** Odoo 19'da `ir.actions.server` modelinde alan adı `group_ids` oldu.

---

## Düzeltme — MO İsmi Sanitizasyonu (2026-04-30 / 2026-05-01)

**Commit:** `d0cf459` — `Fix: sanitize MO name for SkyPlanner number field`  
**Commit:** `dba7247` — `Fix: sanitize external_order_number field`

### `services/mapper.py` — `build_phaser_order()`
```python
# Önce:
'number': production.name,
'external_order_number': production.name,

# Sonra:
'number': production.name.replace('/', '-'),
'external_order_number': production.name.replace('/', '-'),
```
- **Neden:** Odoo üretim emri adları `WH/MO/00001` formatında `/` içeriyor. SkyPlanner `number` alanı URL segmenti olarak kullandığından `/` karakteri API hatasına yol açıyordu.

---

## Düzeltme — Odoo 19 + mapper partner_id (2026-05-01)

**Commit:** `b8f17d4` — `Fix v19: mapper partner_id + CodeEditor mode prop`

### `services/mapper.py` — `_resolve_customer_id()`
- `mrp.production.partner_id` lookup kaldırıldı; artık sadece `skyplanner.default_customer_id` config parametresine bakılıyor.
  - **Neden:** Odoo 19'da `mrp.production` modelinde `partner_id` alanı kaldırıldı. Partner üzerinden SkyPlanner customer ID arama mantığı çalışmıyordu.

### `views/skyplanner_sync_log_views.xml`
- `<field name="payload" widget="ace" options="{'mode': 'json'}"/>` → `options` kaldırıldı.
  - **Neden:** Odoo 19'da `ace` widget `mode` prop'unu kabul etmiyor; view parse hatası veriyordu.

---

## Düzeltme — Webhook, Export Butonu, planning_job_id (2026-05-08)

**Commit:** `bf5f8fd` — `fix(skyplanner): webhook http, export button, planning_job_id lookup`

### `controllers/webhook.py`
- Route `type='jsonrpc'` → `type='http'` olarak değiştirildi.
  - **Neden:** `type='jsonrpc'` Odoo JSON-RPC zarfı (`{"jsonrpc":"2.0","method":"call","params":{...}}`) bekliyor. SkyPlanner düz HTTP JSON POST gönderiyor. Eski kodla `kwargs` her zaman boş geliyordu — `event` parse edilemiyordu, webhook hiç çalışmıyordu.
- Body parse: `request.get_json_data()` / `kwargs` → `request.httprequest.get_data(as_text=True)` + `json.loads()`.
- Return'ler: `return {...}` dict → `request.make_json_response({...}, status=...)`.
  - HTTP 401, 400, 500 status kodları eklendi.

### `models/mrp_production.py`
- `action_export_to_aps()` metodu eklendi.
  - **Neden:** `POST /phaser-orders/export` için MO formunda manuel buton yoktu. T-05 testi (`Export`) bu buton olmadan yapılamıyordu. `auto_export=False` durumunda export hiç tetiklenemiyordu.

### `views/mrp_production_views.xml`
- `"Export to Planning"` butonu eklendi: `skyplanner_sync_state == 'sent'` iken görünür.

### `services/planner.py` — `_resolve_planning_job_id()`
```python
# Önce (hatalı):
jobs_resp = client.get('/phaser-jobs', params={'contain': 'jobs', 'limit': 1})
phaser_jobs = jobs_resp.get('phaser-jobs', [])
for pj in phaser_jobs:
    if pj.get('id') == wo.skyplanner_phaser_job_id:
        ...

# Sonra (doğru):
pj_resp = client.get(f'/phaser-jobs/{wo.skyplanner_phaser_job_id}')
pj = pj_resp.get('phaser-job') or pj_resp
planning_job_id = pj.get('production_planning_job_id')
```
- **Neden:** `limit=1` ile listeleme yapıp döngüde ID eşleştirme neredeyse hiç işe yaramıyordu — API rastgele 1 kayıt dönüyordu. Direkt ID ile GET çok daha güvenilir.

---

## Düzeltme — ISO 8601 Datetime Parse (2026-05-08)

**Commit:** `f1073b8` — `fix(skyplanner): parse ISO 8601 datetimes from SkyPlanner API`

### `services/planner.py`
- `_to_odoo_dt()` module-level yardımcı fonksiyon eklendi.
- `fetch_and_apply()` içinde `extract_planned_dates()` sonrasına dönüşüm eklendi.

**Sorun:** SkyPlanner `planned_start_time` / `planned_end_time` değerlerini ISO 8601 formatında gönderiyor:
```
2026-05-08T08:42:00+00:00
2026-05-08T08:42:00Z
```
Odoo `fields.Datetime.write()` ise `%Y-%m-%d %H:%M:%S` (naive UTC) formatı bekliyor. Hata:
```
ValueError: time data '2026-05-08T08:42:00+00:00' does not match format '%Y-%m-%d %H:%M:%S'
```

**Çözüm:** `_to_odoo_dt()` fonksiyonu:
1. `dateutil.parser.isoparse()` ile parse eder (tüm ISO 8601 varyantları desteklenir)
2. `datetime.fromisoformat()` fallback (dateutil yoksa)
3. Timezone-aware → UTC → naive dönüşümü
4. `%Y-%m-%d %H:%M:%S` string olarak döner

**Desteklenen formatlar:**

| Giriş | Çıkış |
|-------|-------|
| `2026-05-08T08:42:00+00:00` | `2026-05-08 08:42:00` |
| `2026-05-08T08:42:00Z` | `2026-05-08 08:42:00` |
| `2026-05-08 08:42:00` | `2026-05-08 08:42:00` (değişmeden) |
| `2026-05-08T11:42:00+03:00` | `2026-05-08 08:42:00` (UTC'ye çevrildi) |

Hem **Get Plan** (simulate preview) hem **Apply Plan** (write-back) aynı `_to_odoo_dt()` fonksiyonunu kullandığından gösterilen tarih ile yazılan tarih her zaman aynı.

---

## Özet — Değişen Dosyalar

| Dosya | Değişiklik Sayısı | Konu |
|-------|-------------------|------|
| `services/planner.py` | 3 commit | planning_job_id lookup, datetime parse |
| `services/mapper.py` | 3 commit | MO name sanitize, partner_id kaldırma |
| `controllers/webhook.py` | 1 commit | type='http', plain JSON parse |
| `models/mrp_production.py` | 2 commit | queue_job kaldırma, export butonu |
| `jobs/sync_jobs.py` | 1 commit | queue_job import temizliği |
| `__manifest__.py` | 1 commit | queue_job bağımlılığı kaldırma |
| `views/mrp_production_views.xml` | 1 commit | Export butonu |
| `views/mrp_workcenter_views.xml` | 1 commit | group_ids Odoo 19 fix |
| `views/skyplanner_sync_log_views.xml` | 1 commit | ace widget mode prop kaldırma |

---

## Değişmeyen Tasarım Kararları

Aşağıdaki kurallar ilk sürümden bu yana hiç değişmedi:

- **SkyPlanner = planlama önerisi.** Odoo execution state her zaman korunur.
- **`progress` / `done` workorder kayıtları asla overwrite edilmez.**
- **Apply Plan sadece explicit kullanıcı aksiyonuyla tetiklenir, cron ile değil.**
- **Her API çağrısı Sync Log'a yazılır. Silent fail yasak.**
- **Authentication: `Authorization-Token` header (Bearer değil).**
