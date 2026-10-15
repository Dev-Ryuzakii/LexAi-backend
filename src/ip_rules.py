"""
Per-API-key IP allow/deny rules (enforced in api_service._check_ip_rules).

Deny rules always win. If a key has any allow rules, requests must come from one of them.
Addresses may be single IPs or CIDR ranges (IPv4 or IPv6).
"""
import ipaddress

from flask import g, jsonify

from database import APIKey, IPRule

MAX_RULES_PER_KEY = 50


def rule_json(rule: IPRule):
    return {'id': rule.id, 'ip_address': rule.ip_address, 'is_whitelist': rule.is_whitelist,
            'created_at': rule.created_at.isoformat() if rule.created_at else None}


def register_ip_rule_routes(app):
    from api_service import api_error, current_user_id, get_db, now_iso, require_session, validate_body

    def owned_key(db, key_id):
        return db.query(APIKey).filter_by(id=key_id, user_id=current_user_id()).first()

    @app.route('/api/v1/api-keys/<int:key_id>/ip-rules', methods=['GET'])
    @require_session
    def api_list_ip_rules(key_id):
        """List IP rules for one of your keys."""
        db = get_db()
        if not owned_key(db, key_id):
            return api_error(404, 'RES_001', 'API key not found')
        rules = db.query(IPRule).filter_by(api_key_id=key_id).order_by(IPRule.id).all()
        return jsonify({'ip_rules': [rule_json(r) for r in rules], 'total_count': len(rules),
                        'timestamp': now_iso(), 'request_id': g.request_id})

    @app.route('/api/v1/api-keys/<int:key_id>/ip-rules', methods=['POST'])
    @require_session
    @validate_body({
        'ip_address': {'type': str, 'required': True, 'max_length': 64},
        'is_whitelist': {'type': bool},
    })
    def api_add_ip_rule(key_id):
        """Allow or block an IP address or CIDR range for a key."""
        db = get_db()
        if not owned_key(db, key_id):
            return api_error(404, 'RES_001', 'API key not found')
        try:
            network = ipaddress.ip_network(g.body['ip_address'], strict=False)
        except ValueError:
            return api_error(400, 'VAL_001', 'ip_address must be an IP address or CIDR range, e.g. 192.168.1.0/24')
        if db.query(IPRule).filter_by(api_key_id=key_id).count() >= MAX_RULES_PER_KEY:
            return api_error(400, 'VAL_001', f'A key can have at most {MAX_RULES_PER_KEY} IP rules')
        # Store single hosts without the /32 or /128 suffix so they read as the user typed them.
        normalized = str(network.network_address) if network.num_addresses == 1 else str(network)
        rule = IPRule(api_key_id=key_id, ip_address=normalized, is_whitelist=g.body.get('is_whitelist', True))
        db.add(rule)
        db.commit()
        return jsonify({'success': True, 'message': 'IP rule added', 'rule': rule_json(rule),
                        'timestamp': now_iso(), 'request_id': g.request_id}), 201

    @app.route('/api/v1/api-keys/<int:key_id>/ip-rules/<int:rule_id>', methods=['DELETE'])
    @require_session
    def api_delete_ip_rule(key_id, rule_id):
        """Remove an IP rule."""
        db = get_db()
        if not owned_key(db, key_id):
            return api_error(404, 'RES_001', 'API key not found')
        rule = db.query(IPRule).filter_by(id=rule_id, api_key_id=key_id).first()
        if not rule:
            return api_error(404, 'RES_001', 'IP rule not found')
        db.delete(rule)
        db.commit()
        return jsonify({'success': True, 'message': 'IP rule removed', 'rule_id': rule_id,
                        'timestamp': now_iso(), 'request_id': g.request_id})
