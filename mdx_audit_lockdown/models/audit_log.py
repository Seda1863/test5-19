# -*- coding: utf-8 -*-
from odoo import api, models, fields, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta


class MdxAuditLog(models.Model):
    """
    MDX Denetim (Audit) Log modeli.
    Kullanıcı işlemlerini ve değişikliklerini kaydeder.
    """
    _name = "mdx.audit.log"
    _description = "MDX Denetim Logu"
    _order = "id desc"

    ip_address = fields.Char(string="IP Adresi", index=True)

    event_datetime = fields.Datetime(
        string="Tarih/Saat",
        default=fields.Datetime.now,
        required=True,
        index=True,
    )

    user_id = fields.Many2one(
        "res.users",
        string="Kullanıcı",
        required=True,
        index=True,
        ondelete="restrict",
    )

    operation = fields.Selection(
        [("create", "Oluşturma"), ("write", "Güncelleme"), ("unlink", "Silme")],
        string="İşlem Türü",
        required=True,
        index=True,
    )

    model_id = fields.Many2one(
        "ir.model",
        string="Model (Teknik)",
        index=True,
        ondelete="set null",
    )

    model = fields.Char(
        string="Model (Teknik)",
        index=True,
        help="Teknik model adı örn: res.partner",
    )
    res_id = fields.Integer(string="Kayıt ID", index=True)

    field_id = fields.Many2one(
        "ir.model.fields",
        string="Alan",
        ondelete="set null",
    )
    rule_id = fields.Many2one(
        "mdx.audit.rule",
        string="Kural",
        ondelete="set null",
        index=True,
    )

    rule_name = fields.Char(
        string="Kural Adı",
        related="rule_id.name",
        store=False,
        readonly=True,
        index=True,
    )

    field_name = fields.Char(string="Alan Adı", index=True)
    field_type = fields.Char(string="Alan Tipi")

    old_value = fields.Text(string="Eski Değer")
    new_value = fields.Text(string="Yeni Değer")

    request_uid = fields.Char(string="İstek UID", index=True)

    def action_open_target(self):
        """
        Hedef kaydı açmak için kullanılır.
        """
        self.ensure_one()
        if not self.model or not self.res_id:
            return False

        if self.model not in self.env:
            raise UserError(_("Hedef model bulunamadı: %s") % self.model)

        rec = self.env[self.model].sudo().browse(self.res_id)
        if not rec.exists():
            raise UserError(_("Hedef kayıt bulunamadı: %s(%s)") % (self.model, self.res_id))

        return {
            "type": "ir.actions.act_window",
            "name": _("Hedef Kayıt"),
            "res_model": self.model,
            "res_id": self.res_id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def action_view_audit_logs(self):
        """
        Denetim loglarını tarih filtreleriyle açar.
        """
        # Tarih değerlerini hesapla
        today = fields.Date.context_today(self)
        dt_start = datetime.combine(today, datetime.min.time())
        dt_end = datetime.combine(today, datetime.max.time()).replace(microsecond=0)
        last7_start = dt_start - timedelta(days=7)

        # Context sözlüğü oluştur
        ctx = {
            "mdx_today_start": fields.Datetime.to_string(dt_start),
            "mdx_today_end": fields.Datetime.to_string(dt_end),
            "mdx_last7_start": fields.Datetime.to_string(last7_start),
        }

        # Action'ı al ve context'i birleştir
        action = self.env.ref("mdx_audit_lockdown.action_mdx_audit_log").read()[0]

        # Mevcut context'i al ve yeni değerleri ekle
        action_context = action.get("context", {})
        if isinstance(action_context, str):
            action_context = {}
        action_context.update(ctx)
        action["context"] = action_context

        return action

    @api.model
    def _get_audit_log_action_context(self):
        """
        Denetim logları için tarih filtrelerini hesaplar.
        """
        today = fields.Date.context_today(self)
        dt_start = datetime.combine(today, datetime.min.time())
        dt_end = datetime.combine(today, datetime.max.time()).replace(microsecond=0)
        last7_start = dt_start - timedelta(days=7)

        return {
            "mdx_today_start": fields.Datetime.to_string(dt_start),
            "mdx_today_end": fields.Datetime.to_string(dt_end),
            "mdx_last7_start": fields.Datetime.to_string(last7_start),
        }

    @api.model
    def _get_audit_log_action(self):
        """
        Denetim logları action'ını tarih filtreleriyle döndürür.
        """
        action = self.env.ref("mdx_audit_lockdown.action_mdx_audit_log").read()[0]
        action["context"] = self._get_audit_log_action_context()
        return action

    def fields_view_get(self, view_id=None, view_type="form", toolbar=False, submenu=False):
        """
        Search view domain'lerinde context.get('mdx_last7_start') gibi değerler
        kullanabilmek için context’e yardımcı datetime stringleri ekler.
        """
        res = super().fields_view_get(view_id=view_id, view_type=view_type, toolbar=toolbar, submenu=submenu)

        ctx = dict(self.env.context)
        ctx.update(self._get_audit_log_action_context())

        # response'daki context'i güncelle (search view için gerekli)
        if "context" in res:
            res_ctx = res.get("context", {})
            if isinstance(res_ctx, str):
                # Eğer string ise, dict'e çevir
                try:
                    res_ctx = eval(res_ctx)
                except Exception:
                    res_ctx = {}
            res_ctx.update(ctx)
            res["context"] = res_ctx
        else:
            res["context"] = ctx

        return res 