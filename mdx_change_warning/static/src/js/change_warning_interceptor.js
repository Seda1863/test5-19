/** @odoo-module **/

import { FormController } from "@web/views/form/form_controller";
import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { onMounted, onPatched } from "@odoo/owl";

const DEFAULT_MESSAGES = {
    warn_on_edit: "Bu kayıt üzerinde değişiklik yapıyorsunuz. Kaydetmek istediğinize emin misiniz?",
    warn_on_delete: "Bu kaydı silmek üzeresiniz. Bu işlem geri alınamaz!",
    prevent_delete: "Bu kayıt silinemez. Bunun yerine arşivleyebilirsiniz.",
    warn_on_archive: "Bu kaydı arşivlemek üzeresiniz. Devam etmek istiyor musunuz?",
};

const IGNORED_FIELDS = new Set([
    "write_date", "write_uid", "__last_update", "message_follower_ids",
    "message_ids", "activity_ids", "display_name",
]);

let rulesCache = {};
const CACHE_TTL = 10 * 1000;

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.orm = useService("orm");
        this.dialog = useService("dialog");

        // ========================================
        // DEĞİŞİKLİK TAKİBİ
        // record.update() patch — tüm widget tipleri yakalanır
        // Eski → Yeni değer takibi
        // ========================================
        this._userEdited = false;
        this._editedFields = new Set();
        this._oldValues = {};   // { fieldName: eskiDeğer }
        this._newValues = {};   // { fieldName: yeniDeğer }
        this._formReady = false;

        onMounted(() => {
            this._setupRecordTracking();
            setTimeout(() => { this._formReady = true; }, 1500);
        });
        onPatched(() => {
            this._setupRecordTracking();
        });
    },

    /**
     * Record.update() metodunu patch'le
     * Her alan değişikliğinde eski ve yeni değeri sakla
     */
    _setupRecordTracking() {
        const record = this.model.root;
        if (!record || record.__mdxChangeTracked) return;
        record.__mdxChangeTracked = true;

        const self = this;
        const originalUpdate = record.update.bind(record);

        record.update = async function (changes, options) {
            if (self._formReady && changes && typeof changes === 'object') {
                const keys = Object.keys(changes);
                if (keys.length > 0) {
                    self._userEdited = true;
                    for (const key of keys) {
                        if (IGNORED_FIELDS.has(key) || key.startsWith('__')) continue;

                        // İlk değişiklikte eski değeri kaydet
                        if (!self._editedFields.has(key)) {
                            try {
                                const currentVal = record.data[key];
                                self._oldValues[key] = self._formatValue(currentVal, key, record);
                            } catch {
                                self._oldValues[key] = '—';
                            }
                        }

                        self._editedFields.add(key);

                        // Yeni değeri kaydet
                        try {
                            self._newValues[key] = self._formatValue(changes[key], key, record);
                        } catch {
                            self._newValues[key] = String(changes[key] || '');
                        }
                    }
                }
            }
            return originalUpdate(changes, options);
        };
    },

    /**
     * Değeri okunabilir formata çevir
     * Many2one → display_name, Boolean → Evet/Hayır, vs.
     */
    _formatValue(value, fieldName, record) {
        if (value === null || value === undefined || value === false) return '(boş)';

        // Many2one: {id, display_name} veya recordProxy
        if (typeof value === 'object') {
            if (value.display_name) return value.display_name;
            if (value.name) return value.name;
            if (Array.isArray(value)) {
                if (value.length === 0) return '(boş)';
                return `[${value.length} kayıt]`;
            }
            return String(value);
        }

        // Boolean
        if (typeof value === 'boolean') return value ? 'Evet' : 'Hayır';

        // Date string
        if (typeof value === 'string' && value.match(/^\d{4}-\d{2}-\d{2}/)) {
            const d = new Date(value);
            if (!isNaN(d)) return d.toLocaleDateString('tr-TR');
        }

        return String(value);
    },

    _resetUserEdited() {
        this._userEdited = false;
        this._editedFields.clear();
        this._oldValues = {};
        this._newValues = {};
    },

    _resetTrackingForNewRecord() {
        this._resetUserEdited();
        this._formReady = false;
        const record = this.model.root;
        if (record) record.__mdxChangeTracked = false;
        setTimeout(() => {
            this._setupRecordTracking();
            this._formReady = true;
        }, 1500);
    },

    /**
     * Değiştirilen alanları eski → yeni formatında listele
     * Örn: "Müşteri: ABC Ltd ➡️ XYZ Corp"
     */
    _getEditedFieldDetails() {
        if (!this._userEdited) return [];
        const record = this.model.root;
        if (!record) return [];
        const fields = record.fields || {};
        const details = [];

        for (const name of this._editedFields) {
            const field = fields[name];
            const label = (field && field.string) ? field.string : name;
            const oldVal = this._oldValues[name] || '(boş)';
            const newVal = this._newValues[name] || '(boş)';
            details.push({ label, oldVal, newVal });
        }

        return details.length > 0 ? details : [{ label: '(alan bilgisi alınamadı)', oldVal: '', newVal: '' }];
    },

    // =============================================
    // 1. KAYDET BUTONU
    // =============================================
    async saveButtonClicked(params) {
        if (!this._userEdited) return super.saveButtonClicked(...arguments);

        const rules = await this._getEditRules();
        if (rules.length === 0) {
            this._resetUserEdited();
            return super.saveButtonClicked(...arguments);
        }

        const details = this._getEditedFieldDetails();
        const confirmed = await this._showEditWarning(rules, details);
        if (!confirmed) {
            // İPTAL → değişiklikleri geri al (eski haline dön)
            await this.model.root.discard();
            this._resetUserEdited();
            return;
        }

        this._resetUserEdited();
        return super.saveButtonClicked(...arguments);
    },

    // =============================================
    // 2. PAGER OKLARI (< >)
    // =============================================
    async onPagerUpdate() {
        if (!this._userEdited) {
            this._resetTrackingForNewRecord();
            return super.onPagerUpdate(...arguments);
        }

        const rules = await this._getEditRules();
        if (rules.length === 0) {
            this._resetTrackingForNewRecord();
            return super.onPagerUpdate(...arguments);
        }

        const details = this._getEditedFieldDetails();
        const confirmed = await this._showEditWarning(rules, details);
        if (!confirmed) {
            await this.model.root.discard();
            this._resetTrackingForNewRecord();
            return;
        }
        this._resetTrackingForNewRecord();
        return super.onPagerUpdate(...arguments);
    },

    // =============================================
    // 3. BREADCRUMB / MENÜ ile çıkış
    // =============================================
    async canBeDiscarded() {
        if (!this._userEdited) return super.canBeDiscarded(...arguments);

        const rules = await this._getEditRules();
        if (rules.length === 0) {
            this._resetUserEdited();
            return super.canBeDiscarded(...arguments);
        }

        const details = this._getEditedFieldDetails();
        const confirmed = await this._showEditWarning(rules, details);
        if (!confirmed) {
            await this.model.root.discard();
            this._resetUserEdited();
            return true;
        }
        this._resetUserEdited();
        return super.canBeDiscarded(...arguments);
    },

    // =============================================
    // 4. SİLME — deleteRecord override
    // =============================================
    async deleteRecord() {
        const rules = await this._getRulesForCurrentModel();

        const preventRules = rules.filter(r => r.action_types.includes("prevent_delete"));
        if (preventRules.length > 0) {
            await this._showBlockDialog(preventRules, "prevent_delete");
            return;
        }

        const deleteRules = rules.filter(r => r.action_types.includes("warn_on_delete"));
        if (deleteRules.length > 0) {
            const confirmed = await this._showRulesWarning(deleteRules, "warn_on_delete");
            if (!confirmed) return;
        }

        return super.deleteRecord(...arguments);
    },

    // =============================================
    // 5. ARŞİVLEME
    // =============================================
    async beforeExecuteActionButton(clickParams) {
        const actionName = clickParams.name || "";

        if (actionName === "action_archive" || actionName === "toggle_active") {
            const rules = await this._getRulesForCurrentModel();
            const archiveRules = rules.filter(r => r.action_types.includes("warn_on_archive"));
            if (archiveRules.length > 0) {
                const confirmed = await this._showRulesWarning(archiveRules, "warn_on_archive");
                if (!confirmed) return false;
            }
        }

        return super.beforeExecuteActionButton(...arguments);
    },

    // =============================================
    // YARDIMCI METHODLAR
    // =============================================

    async _getEditRules() {
        const rules = await this._getRulesForCurrentModel();
        return rules.filter(r => r.action_types.includes("warn_on_edit"));
    },

    async _getRulesForCurrentModel() {
        const record = this.model.root;
        if (!record) return [];
        const modelName = record.resModel;
        const now = Date.now();
        const cached = rulesCache[modelName];
        if (cached && (now - cached.timestamp) < CACHE_TTL) return cached.rules;

        try {
            const rules = await this.orm.call(
                "mdx.change.warning.rule", "get_rules_for_model", [modelName]
            );
            rulesCache[modelName] = { rules: rules || [], timestamp: now };
            return rules || [];
        } catch (e) {
            console.warn("[ChangeWarning]", e);
            return [];
        }
    },

    _logTrigger(rules, actionType, response) {
        const record = this.model.root;
        for (const rule of rules) {
            try {
                this.orm.call("mdx.change.warning.log", "create", [{
                    rule_id: rule.id,
                    model_name: record.resModel,
                    record_id: record.resId || 0,
                    action_type: actionType,
                    user_response: response,
                }]);
                this.orm.call("mdx.change.warning.rule", "log_trigger", [rule.id]);
            } catch { /* sessiz */ }
        }
    },

    /**
     * Düzenleme uyarısı — eski ➡️ yeni değer gösterir
     */
    _showEditWarning(rules, fieldDetails) {
        return new Promise((resolve) => {
            const bodyParts = [];
            for (const rule of rules) {
                bodyParts.push(`📋 Kural: ${rule.name}`);
                bodyParts.push(rule.warning_message || DEFAULT_MESSAGES.warn_on_edit);
            }
            bodyParts.push("");
            bodyParts.push("📝 Değiştirilen alanlar:");
            for (const d of fieldDetails) {
                if (d.oldVal && d.newVal) {
                    bodyParts.push(`  • ${d.label}: ${d.oldVal} ➡️ ${d.newVal}`);
                } else {
                    bodyParts.push(`  • ${d.label}`);
                }
            }

            let resolved = false;
            this.dialog.add(ConfirmationDialog, {
                title: _t("⚠️ Düzenleme Onayı"),
                body: bodyParts.join("\n"),
                confirmLabel: _t("Evet, Kaydet"),
                cancelLabel: _t("Değişiklikleri İptal Et"),
                confirm: () => { resolved = true; this._logTrigger(rules, "warn_on_edit", "confirmed"); resolve(true); },
                cancel: () => { resolved = true; this._logTrigger(rules, "warn_on_edit", "cancelled"); resolve(false); },
            }, {
                onClose: () => { if (!resolved) { this._logTrigger(rules, "warn_on_edit", "cancelled"); resolve(false); } },
            });
        });
    },

    _showRulesWarning(rules, actionType) {
        return new Promise((resolve) => {
            const bodyParts = [];
            for (const rule of rules) {
                bodyParts.push(`📋 Kural: ${rule.name}`);
                bodyParts.push(rule.warning_message || DEFAULT_MESSAGES[actionType] || "");
                bodyParts.push("");
            }
            const titles = { warn_on_delete: "🗑️ Silme Onayı", warn_on_archive: "📦 Arşivleme Onayı" };
            let resolved = false;
            this.dialog.add(ConfirmationDialog, {
                title: _t(titles[actionType] || "⚠️ Onay"),
                body: bodyParts.join("\n"),
                confirmLabel: _t("Evet, Devam Et"),
                cancelLabel: _t("İptal"),
                confirm: () => { resolved = true; this._logTrigger(rules, actionType, "confirmed"); resolve(true); },
                cancel: () => { resolved = true; this._logTrigger(rules, actionType, "cancelled"); resolve(false); },
            }, {
                onClose: () => { if (!resolved) { this._logTrigger(rules, actionType, "cancelled"); resolve(false); } },
            });
        });
    },

    _showBlockDialog(rules, actionType) {
        return new Promise((resolve) => {
            const bodyParts = [];
            for (const rule of rules) {
                bodyParts.push(`📋 Kural: ${rule.name}`);
                bodyParts.push(rule.warning_message || DEFAULT_MESSAGES[actionType] || "");
            }
            this._logTrigger(rules, actionType, "blocked");
            this.dialog.add(ConfirmationDialog, {
                title: _t("🚫 İşlem Engeli"),
                body: bodyParts.join("\n"),
                confirmLabel: _t("Tamam"),
            }, {
                onClose: () => resolve(false),
            });
        });
    },
});
