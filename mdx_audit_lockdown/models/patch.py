
# -*- coding: utf-8 -*-
from odoo import api, fields, models
import hashlib
import base64
from odoo.http import request
class BaseAuditPatch(models.AbstractModel):
    _inherit = "base"
    MAX_TEXT = 200
    def _mdx_audit_get_rules(self):
        # Skip auditing during module install/upgrade to avoid severe slowdown
        if self.env.context.get("install_mode") or self.env.context.get("module"):
            return self.env["mdx.audit.rule"]

        # Prevent auditing of the audit system itself to avoid recursion/noise
        if self._name.startswith("mdx.audit."):
            return self.env["mdx.audit.rule"]

        Rule = self.env["mdx.audit.rule"].sudo()
        rules = Rule.search([("active", "=", True)])
        # Filter by model: either model_ids is empty (applies to all) or includes this model
        return rules.filtered(lambda r: r._rule_applies_to_model(self._name))
    def _mdx_audit_format_value(self, field, value):
        """Return a short, safe string for audit logs."""
        if value in (None, False):
            return False
        ttype = getattr(field, "ttype", False) or getattr(field, "type", False)
        # BINARY (foto, dosya) -> size + hash
        if ttype == "binary":
            if not value:
                return False
            if isinstance(value, str):
                try:
                    raw = base64.b64decode(value, validate=False)
                    size = len(raw)
                    h = hashlib.sha256(raw).hexdigest()[:16]
                    return f"[binary] {size}B sha256:{h}"
                except Exception:
                    h = hashlib.sha256(value.encode("utf-8", "ignore")).hexdigest()[:16]
                    return f"[binary] (base64) sha256:{h}"
            return "[binary]"
        # TEXT/HTML -> truncate
        if ttype in ("text", "html"):
            s = value if isinstance(value, str) else str(value)
            if len(s) > self.MAX_TEXT:
                h = hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()[:10]
                return s[: self.MAX_TEXT] + f"... [len={len(s)} sha1:{h}]"
            return s
        # Many2one recordset -> id + name
        try:
            if ttype == "many2one" and hasattr(value, "id"):
                return f"{value._name}({value.id}) {value.display_name}"
        except Exception:
            pass
        
        return value if isinstance(value, str) else str(value)
    def _mdx_audit_create_log(self, *, operation, record, field=None, old=None, new=None, rule=None):
    
        Log = self.env["mdx.audit.log"].sudo()
        # model_id
        model_id = False
        try:
            model_rec = self.env["ir.model"].sudo()._get(record._name)
            model_id = model_rec.id if model_rec else False
        except Exception:
            model_id = False
        field_id = False
        field_name = False
        field_type = False
        # field metadata + format + old==new skip
        if field:
            # field can be ir.model.fields record OR python Field (rec._fields[name])
            field_id = getattr(field, "id", False) if hasattr(field, "id") else False
            field_name = getattr(field, "name", False) if hasattr(field, "name") else getattr(field, "string", False)
            field_type = getattr(field, "ttype", False) or getattr(field, "type", False)
            old_fmt = self._mdx_audit_format_value(field, old)
            new_fmt = self._mdx_audit_format_value(field, new)
            # aynıysa log atma
            if old_fmt == new_fmt:
                return
            old = old_fmt
            new = new_fmt
        else:
            # field yoksa yine de stringe çevir (create/unlink gibi)
            old = old if old is None or isinstance(old, str) else str(old)
            new = new if new is None or isinstance(new, str) else str(new)
        Log.create({
            "event_datetime": fields.Datetime.now(),
            "user_id": self.env.user.id,
            "operation": operation,
            "model_id": model_id,
            "model": record._name,
            "res_id": record.id,
            "field_id": field_id,
            "field_name": field_name,
            "field_type": field_type,
            "old_value": old,
            "new_value": new,
            "request_uid": self.env.context.get("mdx_request_uid"),
            "rule_id": rule.id if rule else False,
            "ip_address": self._mdx_audit_get_request_ip(),
        })
    def _mdx_audit_get_request_ip(self):
        try:
            if request and request.httprequest:
                route = getattr(request.httprequest, "access_route", None)
                if route:
                    return route[0]
                return request.httprequest.remote_addr
        except Exception:
            pass
        return False    
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if self.env.context.get("mdx_audit_disable"):
            return records
        rules = records._mdx_audit_get_rules()
        if not rules:
            return records
        for rule in rules:
            if not rule.track_create:
                continue
            # only apply rule if it matches the current user/groups
            try:
                if not rule._rule_applies_to_user(self.env.user):
                    continue
            except Exception:
                # fail-safe: if rule check errors, skip this rule
                continue
            for rec in records:
                rec.with_context(mdx_audit_disable=True)._mdx_audit_create_log(
                    operation="create",
                    record=rec,
                    rule=rule,
                )
        return records
    def write(self, vals):
        if self.env.context.get("mdx_audit_disable"):
            return super().write(vals)
        rules = self._mdx_audit_get_rules()
        if not rules:
            return super().write(vals)
        # 1) OLD values (before write)
        old_values = {}  # {field_name: {rec_id: old}}
        for rule in rules:
            if not rule.track_write:
                continue
            # skip rules that do not apply to the current user
            try:
                if not rule._rule_applies_to_user(self.env.user):
                    continue
            except Exception:
                continue
            tracked_fields = rule.field_ids
            for field_name in vals.keys():
                if field_name not in self._fields:
                    continue
                if tracked_fields and not any(f.name == field_name for f in tracked_fields):
                    continue
                if field_name not in old_values:
                    old_values[field_name] = {}
                for rec in self:
                    try:
                        old_values[field_name][rec.id] = rec[field_name]
                    except Exception:
                        old_values[field_name][rec.id] = None
        # 2) DO write
        res = super().write(vals)
        # 3) LOG diffs (after write)
        for rule in rules:
            if not rule.track_write:
                continue
            # skip rules that do not apply to the current user
            try:
                if not rule._rule_applies_to_user(self.env.user):
                    continue
            except Exception:
                continue
            tracked_fields = rule.field_ids
            excluded_fields = rule.excluded_field_ids
            
            for field_name in vals.keys():
                if field_name not in self._fields:
                    continue
                
                # 1. Whitelist Logic (Eğer tracked_fields doluysa sadece onlar)
                if tracked_fields:
                    if not any(f.name == field_name for f in tracked_fields):
                        continue
                
                # 2. Blacklist Logic (Eğer tracked_fields BOŞSA, excluded_fields'e bak)
                else:
                    if excluded_fields and any(f.name == field_name for f in excluded_fields):
                        continue
                for rec in self:
                    field_rec = self.env["ir.model.fields"].sudo()._get(rec._name, field_name)
                    if not field_rec:
                        # fallback to python field (not ir.model.fields)
                        field_rec = rec._fields[field_name]
                    rec.with_context(mdx_audit_disable=True)._mdx_audit_create_log(
                        operation="write",
                        record=rec,
                        field=field_rec,
                        old=old_values.get(field_name, {}).get(rec.id),
                        new=vals.get(field_name),
                        rule=rule,
                        
                    )
        return res
    def unlink(self):
        if self.env.context.get("mdx_audit_disable"):
            return super().unlink()
        rules = self._mdx_audit_get_rules()
        if not rules:
            return super().unlink()
        for rule in rules:
            if not rule.track_unlink:
                continue
            try:
                if not rule._rule_applies_to_user(self.env.user):
                    continue
            except Exception:
                continue
            for rec in self:
                rec.with_context(mdx_audit_disable=True)._mdx_audit_create_log(
                    operation="unlink",
                    record=rec,
                    rule=rule,
                )
        return super().unlink()