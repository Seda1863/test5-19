# -*- coding: utf-8 -*-

import logging
from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MdxSeriesManagerMixin(models.AbstractModel):
    _name = 'mdx.series.manager.mixin'
    _description = 'Fatura Seri Yönetimi Mixin'

    def reserve_series_number(self, series_record, invoice_record):
        """
        SAVEPOINT ile atomik seri numarası rezervasyonu yapar.
        GIB formatı: {SeriKodu}{Yıl}{9HaneliSıra} = 16 karakter
        Örnek: MDX2026000000001
        :param series_record: mdx.fatura.seri kaydı
        :param invoice_record: account.move kaydı
        :return: dict {number, invoice_number, savepoint_name, series_id}
        """
        savepoint_name = 'series_reserve_%d_%d' % (series_record.id, invoice_record.id)
        self.env.cr.execute('SAVEPOINT "%s"' % savepoint_name)

        try:
            # Seri kaydını update lock ile kilitle
            self.env.cr.execute(
                "SELECT index FROM mdx_fatura_seri WHERE id = %s FOR UPDATE",
                (series_record.id,)
            )

            # Fatura tarihinden yıl bilgisini al
            issue_date = invoice_record.invoice_date or fields.Date.today()
            year = str(issue_date.year)

            # Yıl değişimi kontrolü: bu yıl ilk fatura mı?
            current_year = issue_date.year
            if hasattr(invoice_record, 'invoice_date'):
                # account.move (fatura)
                existing_in_year = self.env["account.move"].search([
                    ("fatura_seri_id", "=", series_record.id),
                    ("state", "in", ["draft", "posted"]),
                    ("invoice_date", ">=", "%d-01-01" % current_year),
                    ("invoice_date", "<=", "%d-12-31" % current_year),
                    ("id", "!=", invoice_record.id),
                ], limit=1)
            else:
                existing_in_year = True  # stock.picking için yıl sıfırlama yapma

            if not existing_in_year:
                # Bu yıl ilk fatura — index'i 1'den başlat
                new_index = 1
            else:
                new_index = series_record.index

            series_record.write({
                'index': new_index + 1,
                'last_used_date': fields.Date.today(),
            })

            # GIB formatı: SeriKodu + 4 haneli yıl + 9 haneli sıra = 16 karakter
            invoice_number = '%s%s%s' % (series_record.code, year, str(new_index).zfill(9))

            _logger.info(
                "Seri %s numarası %d rezerve edildi (fatura %d)",
                series_record.code, new_index, invoice_record.id,
            )

            return {
                'number': new_index,
                'invoice_number': invoice_number,
                'savepoint_name': savepoint_name,
                'series_id': series_record.id,
            }

        except Exception as e:
            self.env.cr.execute('ROLLBACK TO SAVEPOINT "%s"' % savepoint_name)
            _logger.error("Seri numarası rezervasyonu başarısız: %s", str(e))
            raise UserError("Seri numarası rezervasyonu başarısız: %s" % str(e))

    def release_series_number(self, reservation):
        """
        Hata durumunda SAVEPOINT'e geri dönerek seri numarasını serbest bırakır.
        :param reservation: reserve_series_number() dönüş değeri
        :return: bool
        """
        savepoint_name = reservation.get('savepoint_name')
        if savepoint_name:
            try:
                self.env.cr.execute('ROLLBACK TO SAVEPOINT "%s"' % savepoint_name)
                _logger.info("Seri rezervasyonu geri alındı: %s", savepoint_name)
                return True
            except Exception as e:
                _logger.error("Seri rezervasyonu geri alma başarısız: %s", str(e))
                return False
        return False

    def confirm_series_number(self, reservation):
        """
        Başarılı gönderim sonrası SAVEPOINT'i onaylayarak seri numarasını kesinleştirir.
        :param reservation: reserve_series_number() dönüş değeri
        :return: bool
        """
        savepoint_name = reservation.get('savepoint_name')
        if savepoint_name:
            try:
                self.env.cr.execute('RELEASE SAVEPOINT "%s"' % savepoint_name)
                _logger.info("Seri rezervasyonu onaylandı: %s", savepoint_name)
                return True
            except Exception as e:
                _logger.error("Seri rezervasyonu onaylama başarısız: %s", str(e))
                return False
        return False

    def validate_series_sequence(self, series_record, expected_number):
        """
        Seri numarasının sıralı olduğunu doğrular.
        :param series_record: mdx.fatura.seri kaydı
        :param expected_number: Beklenen sıra numarası
        :return: True
        :raises: UserError
        """
        current_index = series_record.index

        if expected_number != current_index + 1:
            raise UserError(
                "Seri numarası sıralı değil!\n"
                "Beklenen: %d\n"
                "Gelen: %d\n"
                "Lütfen seri ayarlarını kontrol edin." % (current_index + 1, expected_number)
            )

        return True
