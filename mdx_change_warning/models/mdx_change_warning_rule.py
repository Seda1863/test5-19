# -*- coding: utf-8 -*-
from odoo import models, fields, api


class MdxChangeWarningRule(models.Model):
    _name = 'mdx.change.warning.rule'
    _description = 'Değişiklik Uyarı Kuralı'
    _order = 'sequence, id'

    name = fields.Char(
        string='Kural Adı',
        required=True,
    )
    active = fields.Boolean(
        string='Aktif',
        default=True,
    )
    sequence = fields.Integer(
        string='Sıra',
        default=10,
    )

    # =============================================
    # KAPSAM: Uygulama + Model (opsiyonel)
    # =============================================
    module_ids = fields.Many2many(
        'ir.module.module',
        'mdx_change_warning_rule_module_rel',
        'rule_id',
        'module_id',
        string='Uygulamalar',
        domain=[('application', '=', True), ('state', '=', 'installed')],
        help='Boş bırakılırsa tüm uygulamalara uygulanır. Birden fazla seçilebilir.',
    )
    model_ids = fields.Many2many(
        'ir.model',
        'mdx_change_warning_rule_model_rel',
        'rule_id',
        'model_id',
        string='Modeller',
        domain=[('transient', '=', False)],
        help='Boş bırakılırsa seçilen uygulamadaki tüm modellere uygulanır. '
             'Uygulama da boşsa tüm modellere uygulanır.',
    )

    # =============================================
    # KURAL TİPLERİ (çoklu seçim - checkbox)
    # =============================================
    warn_on_edit = fields.Boolean(
        string='Düzenlerken Uyar',
        default=True,
    )
    warn_on_delete = fields.Boolean(
        string='Silerken Uyar',
    )
    prevent_delete = fields.Boolean(
        string='Silmeyi Engelle',
    )
    warn_on_archive = fields.Boolean(
        string='Arşivlerken Uyar',
    )

    # =============================================
    # UYARI AYARLARI
    # =============================================
    warning_message = fields.Text(
        string='Uyarı Mesajı',
        help='Boş bırakılırsa varsayılan mesaj kullanılır.',
    )
    user_ids = fields.Many2many(
        'res.users',
        'mdx_change_warning_rule_user_rel',
        'rule_id',
        'user_id',
        string='Uygulanacak Kullanıcılar',
        help='Boş bırakılırsa tüm kullanıcılara uygulanır.',
    )

    # =============================================
    # DASHBOARD: Tetiklenme İstatistikleri
    # =============================================
    trigger_count = fields.Integer(
        string='Tetiklenme Sayısı',
        default=0,
        readonly=True,
    )
    last_triggered = fields.Datetime(
        string='Son Tetiklenme',
        readonly=True,
    )
    last_triggered_by = fields.Many2one(
        'res.users',
        string='Son Tetikleyen',
        readonly=True,
    )

    @api.model
    def get_rules_for_model(self, model_name):
        """Frontend çağırır. Verilen model için geçerli kuralları döner."""
        import logging
        _logger = logging.getLogger(__name__)

        user = self.env.user
        rules = self.search([('active', '=', True)])

        # Model'in ait olduğu modülleri bul (birden fazla olabilir)
        model_modules = self._get_model_modules(model_name)
        _logger.info("[ChangeWarning] Model: %s, Modules: %s, User: %s (ID: %s)",
                     model_name, model_modules, user.name, user.id)

        result = []
        for rule in rules:
            # ─────────────────────────────────
            # KULLANICI FİLTRESİ
            # ─────────────────────────────────
            if rule.user_ids:
                if user.id not in rule.user_ids.ids:
                    _logger.debug("[ChangeWarning] Kural '%s' atlandı — kullanıcı filtresi uyuşmuyor", rule.name)
                    continue

            # ─────────────────────────────────
            # KAPSAM KONTROLÜ (Model + Uygulama)
            # ─────────────────────────────────
            if rule.model_ids:
                # Spesifik model seçilmiş → sadece o modellerde çalış
                rule_model_names = rule.model_ids.mapped('model')
                if model_name not in rule_model_names:
                    _logger.debug("[ChangeWarning] Kural '%s' atlandı — model uyuşmuyor (%s not in %s)",
                                 rule.name, model_name, rule_model_names)
                    continue
            elif rule.module_ids:
                # Uygulama seçilmiş ama model seçilmemiş → uygulamadaki tüm modeller
                rule_module_names = set(rule.module_ids.mapped('name'))
                if not model_modules.intersection(rule_module_names):
                    _logger.debug("[ChangeWarning] Kural '%s' atlandı — uygulama uyuşmuyor (%s ∩ %s = ∅)",
                                 rule.name, model_modules, rule_module_names)
                    continue
            # else: ne model ne uygulama seçili → TÜMÜNE uygulanır

            # ─────────────────────────────────
            # AKTİF KURAL TİPLERİ
            # ─────────────────────────────────
            active_types = []
            if rule.warn_on_edit:
                active_types.append('warn_on_edit')
            if rule.warn_on_delete:
                active_types.append('warn_on_delete')
            if rule.prevent_delete:
                active_types.append('prevent_delete')
            if rule.warn_on_archive:
                active_types.append('warn_on_archive')

            if not active_types:
                continue

            _logger.info("[ChangeWarning] Kural EŞLEŞTİ: '%s' → %s", rule.name, active_types)
            result.append({
                'id': rule.id,
                'name': rule.name,
                'action_types': active_types,
                'warning_message': rule.warning_message or '',
            })

        return result

    @api.model
    def log_trigger(self, rule_id):
        """Frontend Dialog gösterildiğinde tetiklenme loglar."""
        rule = self.browse(rule_id)
        if rule.exists():
            rule.sudo().write({
                'trigger_count': rule.trigger_count + 1,
                'last_triggered': fields.Datetime.now(),
                'last_triggered_by': self.env.uid,
            })

    def action_view_logs(self):
        """Stat button'dan logları göster"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'{self.name} - Loglar',
            'res_model': 'mdx.change.warning.log',
            'view_mode': 'list,pivot,graph',
            'domain': [('rule_id', '=', self.id)],
            'context': {'default_rule_id': self.id},
        }

    @api.model
    def _get_model_modules(self, model_name):
        """Model'in ait olduğu modülleri bul (set olarak döner).
        Birden fazla modül aynı modele katkıda bulunabilir."""
        modules = set()

        # Yöntem 1: ir.model.data üzerinden model tanımını bul
        model_data = self.env['ir.model.data'].sudo().search([
            ('model', '=', 'ir.model'),
            ('name', '=', 'model_' + model_name.replace('.', '_')),
        ])
        for md in model_data:
            if md.module:
                modules.add(md.module)

        # Yöntem 2: Model adından ana modülü tahmin et
        # Örn: stock.picking → stock, account.move → account
        parts = model_name.split('.')
        if parts:
            modules.add(parts[0])  # İlk kısım genelde ana modül

        # Yöntem 3: Yaygın Odoo modül eşleştirmeleri
        MODULE_MAP = {
            'account': ['account', 'accounting'],
            'stock': ['stock'],
            'sale': ['sale', 'sale_management'],
            'purchase': ['purchase'],
            'hr': ['hr', 'hr_holidays', 'hr_expense'],
            'project': ['project'],
            'crm': ['crm'],
            'mrp': ['mrp'],
            'pos': ['point_of_sale'],
            'website': ['website', 'website_sale'],
        }
        for key, module_names in MODULE_MAP.items():
            if model_name.startswith(key + '.') or model_name == key:
                modules.update(module_names)

        return modules


class MdxChangeWarningLog(models.Model):
    _name = 'mdx.change.warning.log'
    _description = 'Değişiklik Uyarı Logu'
    _order = 'create_date desc'

    rule_id = fields.Many2one(
        'mdx.change.warning.rule',
        string='Kural',
        required=True,
        ondelete='cascade',
    )
    user_id = fields.Many2one(
        'res.users',
        string='Kullanıcı',
        default=lambda self: self.env.uid,
    )
    model_name = fields.Char(string='Model')
    record_id = fields.Integer(string='Kayıt ID')
    action_type = fields.Selection([
        ('warn_on_edit', 'Düzenleme'),
        ('warn_on_delete', 'Silme'),
        ('prevent_delete', 'Silme Engeli'),
        ('warn_on_archive', 'Arşivleme'),
    ], string='İşlem Tipi')
    user_response = fields.Selection([
        ('confirmed', 'Onayladı'),
        ('cancelled', 'İptal Etti'),
        ('blocked', 'Engellendi'),
    ], string='Kullanıcı Yanıtı')
