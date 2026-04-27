# -*- coding: utf-8 -*-
import base64
import binascii
import csv
import io
import json
import re
from urllib import error as url_error
from urllib import request as url_request

from odoo import _, models
from odoo.exceptions import UserError


class DbsAdapterBase(models.AbstractModel):
    _name = 'dbs.adapter.base'
    _description = 'DBS Adapter Base'

    def export_batch(self, batch, lines=None):
        raise UserError(_('Bu adaptor export_batch implement etmelidir.'))

    def import_ack(self, contract, content_bytes):
        raise UserError(_('Bu adaptor import_ack implement etmelidir.'))

    def fetch_ack_payloads(self, contract):
        if not contract:
            return []
        contract.ensure_one()
        integration_type = (contract.integration_type or 'manual').strip().lower()
        params = self._get_contract_params(contract)
        if integration_type == 'api':
            return self._fetch_ack_via_api(contract, params)
        if integration_type == 'sftp':
            return self._fetch_ack_via_sftp(contract, params)
        return []

    def _get_contract_params(self, contract):
        if not contract:
            return {}
        if hasattr(contract, '_get_technical_params_dict'):
            return contract._get_technical_params_dict()
        return {}

    def _to_bool(self, value, default=False):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in ('1', 'true', 'yes', 'y', 'on'):
            return True
        if text in ('0', 'false', 'no', 'n', 'off'):
            return False
        return default

    def _normalize_ack_status(self, status):
        lowered = (status or '').strip().lower()
        if lowered in ('ok', 'accepted', 'success'):
            return 'accepted'
        if lowered in ('rejected', 'error', 'fail'):
            return 'rejected'
        if lowered == 'settled':
            return 'settled'
        return 'accepted'

    def _is_ack_strict_mode(self, contract):
        context_value = self.env.context.get('dbs_ack_strict_header')
        if context_value is not None:
            return self._to_bool(context_value, default=True)
        params = self._get_contract_params(contract)
        return self._to_bool(params.get('ack_strict_header'), default=True)

    def _validate_ack_headers(self, headers, strict_header=True):
        normalized_headers = [(h or '').strip().lower() for h in headers]
        expected = ['line_ref', 'status', 'reject_code', 'message']
        required = {'line_ref', 'status'}
        if strict_header and normalized_headers != expected:
            raise UserError(
                _('ACK header strict validation hatasi. Beklenen: %(expected)s | Gelen: %(actual)s') % {
                    'expected': ';'.join(expected),
                    'actual': ';'.join(normalized_headers),
                }
            )
        missing = sorted(required - set(normalized_headers))
        if missing:
            raise UserError(_('ACK dosyasi zorunlu header(lar)i eksik: %s') % ', '.join(missing))

    def _parse_ack_csv_rows(self, content_bytes, strict_header=True):
        if not content_bytes:
            return []

        decoded = None
        tried = []
        for encoding in ('utf-8-sig', 'cp1254', 'latin-1'):
            try:
                decoded = content_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                tried.append(encoding)

        if decoded is None:
            raise UserError(_('ACK dosyasi okunamadi. Desteklenen encoding: %s') % ', '.join(tried))

        stream = io.StringIO(decoded)
        reader = csv.reader(stream, delimiter=';')
        headers = None
        for raw in reader:
            if raw and any((item or '').strip() for item in raw):
                headers = [(item or '').strip() for item in raw]
                break

        if not headers:
            return []

        self._validate_ack_headers(headers, strict_header=strict_header)

        dict_reader = csv.DictReader(stream, delimiter=';', fieldnames=headers)
        rows = []
        for row in dict_reader:
            if not row:
                continue
            normalized_row = {
                (key or '').strip().lower(): (value or '').strip()
                for key, value in row.items()
            }
            if not any(normalized_row.values()):
                continue
            rows.append({
                'dbs_line_ref': normalized_row.get('line_ref', ''),
                'status': self._normalize_ack_status(normalized_row.get('status')),
                'reject_code': normalized_row.get('reject_code', ''),
                'message': normalized_row.get('message', ''),
            })
        return rows

    def _extract_filename_from_disposition(self, content_disposition):
        if not content_disposition:
            return False
        matches = re.findall(r'filename="?([^";]+)"?', content_disposition, flags=re.IGNORECASE)
        return matches[0] if matches else False

    def _decode_base64_data(self, value, field_name):
        try:
            return base64.b64decode((value or '').encode('utf-8'), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise UserError(_('%(field)s base64 decode hatasi: %(error)s') % {
                'field': field_name,
                'error': str(exc),
            })

    def _normalize_api_ack_item(self, item, index):
        if not item:
            return False
        if isinstance(item, str):
            return {
                'filename': f'ack_{index}.csv',
                'content_bytes': item.encode('utf-8'),
            }
        if not isinstance(item, dict):
            raise UserError(_('API ACK cevabinda satir tipi gecersiz: %s') % type(item).__name__)

        filename = (item.get('filename') or item.get('name') or f'ack_{index}.csv').strip()
        content_bytes = b''
        if item.get('content_base64') or item.get('payload_base64'):
            content_bytes = self._decode_base64_data(
                item.get('content_base64') or item.get('payload_base64'),
                'content_base64',
            )
        elif isinstance(item.get('content'), bytes):
            content_bytes = item.get('content')
        elif isinstance(item.get('payload'), bytes):
            content_bytes = item.get('payload')
        elif item.get('content') is not None or item.get('payload') is not None:
            value = item.get('content') if item.get('content') is not None else item.get('payload')
            if (item.get('encoding') or '').strip().lower() == 'base64':
                content_bytes = self._decode_base64_data(value, 'content')
            else:
                content_bytes = str(value).encode('utf-8')

        if not content_bytes:
            return False
        return {
            'filename': filename,
            'content_bytes': content_bytes,
        }

    def _normalize_api_ack_json(self, body):
        try:
            data = json.loads(body.decode('utf-8-sig'))
        except Exception as exc:
            raise UserError(_('API ACK JSON parse hatasi: %s') % str(exc))

        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            items = data.get('acks')
            if items is None:
                items = data.get('items')
            if items is None and any(key in data for key in ('content', 'payload', 'content_base64', 'payload_base64')):
                items = [data]
            if items is None:
                return []
        else:
            raise UserError(_('API ACK JSON cevabi list/dict olmali.'))

        payloads = []
        for index, item in enumerate(items, start=1):
            normalized = self._normalize_api_ack_item(item, index)
            if normalized:
                payloads.append(normalized)
        return payloads

    def _fetch_ack_via_api(self, contract, params):
        endpoint = (params.get('ack_endpoint') or params.get('endpoint') or '').strip()
        if not endpoint:
            raise UserError(_('API ACK cekimi icin endpoint/ack_endpoint zorunlu.'))

        method = (params.get('ack_method') or 'GET').strip().upper()
        timeout = int(params.get('ack_timeout') or 20)
        headers = {'Accept': 'application/json, text/csv, text/plain, */*'}
        if params.get('ack_headers'):
            if not isinstance(params.get('ack_headers'), dict):
                raise UserError(_('ack_headers JSON obje olmali.'))
            headers.update({str(key): str(value) for key, value in params['ack_headers'].items()})

        token = (params.get('token') or '').strip()
        if token and 'Authorization' not in headers:
            headers['Authorization'] = f'Bearer {token}'

        payload = params.get('ack_payload')
        data = None
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            headers.setdefault('Content-Type', 'application/json')

        request = url_request.Request(endpoint, data=data, method=method, headers=headers)
        try:
            with url_request.urlopen(request, timeout=timeout) as response:
                content = response.read()
                content_type = (response.headers.get('Content-Type') or '').lower()
                disposition = response.headers.get('Content-Disposition') or ''
        except url_error.HTTPError as exc:
            raise UserError(_('API ACK cekimi HTTP hatasi: %s') % str(exc))
        except url_error.URLError as exc:
            raise UserError(_('API ACK cekimi baglanti hatasi: %s') % str(exc))
        except Exception as exc:
            raise UserError(_('API ACK cekimi hatasi: %s') % str(exc))

        if not content:
            return []

        if 'json' in content_type or content[:1] in (b'{', b'['):
            return self._normalize_api_ack_json(content)

        filename = self._extract_filename_from_disposition(disposition) or (params.get('ack_filename') or 'ack.csv')
        return [{
            'filename': filename,
            'content_bytes': content,
        }]

    def _load_sftp_private_key(self, paramiko_module, params):
        private_key = params.get('private_key')
        private_key_path = params.get('private_key_path')
        passphrase = params.get('private_key_passphrase')
        if not private_key and not private_key_path:
            return None

        key_loaders = []
        for key_class_name in ('RSAKey', 'ECDSAKey', 'Ed25519Key', 'DSSKey'):
            key_class = getattr(paramiko_module, key_class_name, None)
            if key_class:
                key_loaders.append(key_class)

        for key_loader in key_loaders:
            try:
                if private_key:
                    return key_loader.from_private_key(io.StringIO(private_key), password=passphrase)
                return key_loader.from_private_key_file(private_key_path, password=passphrase)
            except Exception:
                continue

        raise UserError(_('SFTP private key yuklenemedi. key/private_key_path formatini kontrol edin.'))

    def _fetch_ack_via_sftp(self, contract, params):
        missing = [key for key in ('host', 'username', 'path') if not params.get(key)]
        if missing:
            raise UserError(_('SFTP ACK cekimi icin eksik teknik parametre(ler): %s') % ', '.join(missing))

        try:
            import paramiko
        except Exception as exc:
            raise UserError(_('SFTP ACK cekimi icin paramiko kutuphanesi gerekli: %s') % str(exc))

        host = params.get('host')
        port = int(params.get('port') or 22)
        username = params.get('username')
        password = params.get('password')
        remote_path = str(params.get('path') or '').rstrip('/') or '/'
        timeout = int(params.get('timeout') or 20)
        filename_pattern = params.get('ack_filename_pattern') or r'.*\.(csv|txt)$'
        archive_path = str(params.get('ack_archive_path') or '').strip().rstrip('/')
        delete_after_fetch = self._to_bool(params.get('ack_delete_after_fetch'), default=False)
        if archive_path:
            delete_after_fetch = False

        try:
            matcher = re.compile(filename_pattern, flags=re.IGNORECASE)
        except re.error as exc:
            raise UserError(_('SFTP ack_filename_pattern regex hatasi: %s') % str(exc))

        pkey = self._load_sftp_private_key(paramiko, params)
        transport = None
        sftp_client = None
        try:
            transport = paramiko.Transport((host, port))
            transport.banner_timeout = timeout
            transport.connect(username=username, password=password, pkey=pkey)
            sftp_client = paramiko.SFTPClient.from_transport(transport)

            entries = sorted(sftp_client.listdir_attr(remote_path), key=lambda entry: entry.filename)
            payloads = []
            for entry in entries:
                filename = entry.filename
                if not matcher.search(filename):
                    continue

                remote_file = f'{remote_path}/{filename}'
                with sftp_client.open(remote_file, 'rb') as handle:
                    content_bytes = handle.read()
                payloads.append({
                    'filename': filename,
                    'content_bytes': content_bytes,
                })

                if archive_path:
                    sftp_client.rename(remote_file, f'{archive_path}/{filename}')
                elif delete_after_fetch:
                    sftp_client.remove(remote_file)
            return payloads
        except Exception as exc:
            raise UserError(_('SFTP ACK cekimi hatasi: %s') % str(exc))
        finally:
            if sftp_client:
                sftp_client.close()
            if transport:
                transport.close()


class DbsAdapterManual(models.AbstractModel):
    _name = 'dbs.adapter.manual'
    _description = 'DBS Adapter Manual'
    _inherit = 'dbs.adapter.base'

    def export_batch(self, batch, lines=None):
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        writer.writerow(['line_ref', 'customer_code', 'invoice', 'due_date', 'amount'])
        lines_to_send = lines if lines is not None else batch.line_ids.filtered(lambda l: l.state == 'to_send')
        for line in lines_to_send:
            writer.writerow([
                line.dbs_line_ref,
                line.partner_customer_code or '',
                line.move_id.name or line.move_id.ref or '',
                line.due_date or '',
                f'{line.amount:.2f}',
            ])
        if lines_to_send:
            lines_to_send.write({'state': 'sent'})

        payload = output.getvalue().encode('utf-8')
        filename = f'{batch.name}.csv'
        return {
            'payload': base64.b64encode(payload),
            'filename': filename,
            'bank_reference': batch.name,
        }

    def import_ack(self, contract, content_bytes):
        strict_header = self._is_ack_strict_mode(contract)
        return self._parse_ack_csv_rows(content_bytes, strict_header=strict_header)
