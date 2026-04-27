# account_dbs_tr

Odoo 18 Turkiye DBS (Dogrudan Borclandirma Sistemi) cekirdek modulu.

## MVP Kapsami
- DBS sozlesme yonetimi
- Faturalardan DBS batch olusturma
- Manual adaptor ile export/ACK import
- Statement satirindan DBS referansina gore otomatik esleme

## Genisleme
Banka ozel adaptorler `dbs.adapter.<code>` abstract modelini miras alip `export_batch` ve `import_ack` metodlarini implement eder.

## ACK Polling (cron)
- `cron_poll_ack` artik `integration_type=api/sftp` sozlesmelerde adaptor uzerinden ACK dosyasi ceker.
- API icin temel parametreler: `ack_endpoint` (veya `endpoint`), opsiyonel `token`, `ack_headers`, `ack_method`, `ack_payload`.
- SFTP icin temel parametreler: `host`, `username`, `path`, opsiyonel `password` veya `private_key/private_key_path`.

## ACK Header Strict Mode
- `import_ack` varsayilan olarak strict header dogrulama yapar.
- Beklenen header: `line_ref;status;reject_code;message`
- Isterseniz `technical_params` icine `ack_strict_header: false` yazarak gevsetebilirsiniz.
