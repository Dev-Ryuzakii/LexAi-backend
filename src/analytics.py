"""
Usage analytics built from the api_usage table.

Scope: a dashboard session sees all of the user's traffic; an API key sees only its own.
Response times are reported in seconds.
"""
import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from flask import g, jsonify, make_response, request
from sqlalchemy import case, func

from database import APIKey, ApiUsage

MAX_EXPORT_ROWS = 100000


def _parse_date(value: Optional[str], end_of_day: bool = False) -> Optional[datetime]:
    """Accept YYYY-MM-DD or an ISO timestamp. A bare end date includes that whole day."""
    if not value:
        return None
    value = value.strip().replace('Z', '')
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f'Invalid date: {value!r}. Use YYYY-MM-DD.')
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    if end_of_day and len(value) == 10:
        parsed = parsed + timedelta(days=1) - timedelta(microseconds=1)
    return parsed


def _scoped(db):
    p = g.principal
    query = db.query(ApiUsage).filter(ApiUsage.user_id == p['user_id'])
    if p['kind'] == 'api_key':
        query = query.filter(ApiUsage.api_key_id == p['key_id'])
    return query


def _range(query, start: Optional[datetime], end: Optional[datetime]):
    if start:
        query = query.filter(ApiUsage.created_at >= start)
    if end:
        query = query.filter(ApiUsage.created_at <= end)
    return query


def _summary(query) -> Dict[str, Any]:
    total, ok, errors, avg_time = query.with_entities(
        func.count(ApiUsage.id),
        func.sum(case((ApiUsage.status_code < 400, 1), else_=0)),
        func.sum(case((ApiUsage.status_code >= 400, 1), else_=0)),
        func.avg(ApiUsage.response_time),
    ).one()
    return {
        'total_requests': total or 0,
        'successful_requests': int(ok or 0),
        'error_requests': int(errors or 0),
        'avg_response_time': round(float(avg_time or 0), 4),
    }


def _change(before: float, after: float) -> Dict[str, float]:
    absolute = after - before
    percentage = (absolute / before * 100) if before else (100.0 if after else 0.0)
    return {'absolute': round(absolute, 4), 'percentage': round(percentage, 2)}


def _bucket(ts: datetime, group_by: str) -> datetime:
    if group_by == 'hour':
        return ts.replace(minute=0, second=0, microsecond=0)
    if group_by == 'week':
        day = ts.replace(hour=0, minute=0, second=0, microsecond=0)
        return day - timedelta(days=day.weekday())
    if group_by == 'month':
        return ts.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return ts.replace(hour=0, minute=0, second=0, microsecond=0)


def register_analytics_routes(app):
    from api_service import api_error, current_user_id, get_db, now_iso, require_auth

    def dates(*names: Tuple[str, bool]):
        try:
            return [_parse_date(request.args.get(n), end_of_day=eod) for n, eod in names]
        except ValueError as e:
            raise _BadRequest(str(e))

    class _BadRequest(Exception):
        pass

    @app.errorhandler(_BadRequest)
    def _bad_request(e):
        return api_error(400, 'VAL_001', str(e))

    @app.route('/api/v1/analytics/quota', methods=['GET'])
    @require_auth
    def api_quota_usage():
        """Monthly quota use. Sessions see the total across all active keys."""
        now = datetime.utcnow()
        try:
            year = int(request.args.get('year', now.year))
            month = int(request.args.get('month', now.month))
            start = datetime(year, month, 1)
        except ValueError:
            return api_error(400, 'VAL_001', 'year and month must form a valid date')
        end = (start + timedelta(days=32)).replace(day=1)

        db = get_db()
        p = g.principal
        usage = db.query(func.coalesce(func.sum(ApiUsage.units), 0)).filter(
            ApiUsage.user_id == current_user_id(),
            ApiUsage.api_key_id.isnot(None),
            ApiUsage.created_at >= start, ApiUsage.created_at < end,
        )
        if p['kind'] == 'api_key':
            usage = usage.filter(ApiUsage.api_key_id == p['key_id'])
            quota = p['monthly_quota']
        else:
            quota = db.query(func.coalesce(func.sum(APIKey.monthly_quota), 0)).filter(
                APIKey.user_id == current_user_id(), APIKey.is_active.is_(True)).scalar()
        used = int(usage.scalar() or 0)
        quota = int(quota or 0)
        return jsonify({'quota_usage': {
            'used': used,
            'quota': quota,
            'remaining': max(quota - used, 0),
            'percentage_used': round(used / quota * 100, 2) if quota else 0.0,
            'period': f'{year:04d}-{month:02d}',
        }, 'timestamp': now_iso()})

    @app.route('/api/v1/analytics/stats', methods=['GET'])
    @require_auth
    def api_usage_stats():
        """Request totals, success rate, response times, per-endpoint and per-status breakdowns."""
        start, end = dates(('start_date', False), ('end_date', True))
        query = _range(_scoped(get_db()), start, end)
        if request.args.get('endpoint'):
            query = query.filter(ApiUsage.endpoint == request.args['endpoint'])

        stats = _summary(query)
        sizes = query.with_entities(func.coalesce(func.sum(ApiUsage.request_size), 0),
                                    func.coalesce(func.sum(ApiUsage.response_size), 0)).one()
        breakdown = query.with_entities(ApiUsage.endpoint, func.count(ApiUsage.id), func.avg(ApiUsage.response_time)) \
            .group_by(ApiUsage.endpoint).order_by(func.count(ApiUsage.id).desc()).all()
        by_status = query.with_entities(ApiUsage.status_code, func.count(ApiUsage.id)).group_by(ApiUsage.status_code).all()

        total = stats['total_requests']
        return jsonify({'statistics': {
            **stats,
            'success_rate': round(stats['successful_requests'] / total * 100, 2) if total else 0.0,
            'total_request_size': int(sizes[0]),
            'total_response_size': int(sizes[1]),
            'endpoint_breakdown': [{'endpoint': e, 'count': c, 'avg_response_time': round(float(t or 0), 4)}
                                   for e, c, t in breakdown],
            'status_code_stats': {str(code): count for code, count in by_status},
        }, 'timestamp': now_iso()})

    @app.route('/api/v1/analytics/timeline', methods=['GET'])
    @require_auth
    def api_usage_timeline():
        """Requests over time, grouped by hour, day, week or month."""
        try:
            days = min(max(int(request.args.get('days', 30)), 1), 366)
        except ValueError:
            return api_error(400, 'VAL_001', 'days must be a number')
        group_by = request.args.get('group_by', 'day')
        if group_by not in ('hour', 'day', 'week', 'month'):
            return api_error(400, 'VAL_001', 'group_by must be hour, day, week or month')

        since = datetime.utcnow() - timedelta(days=days)
        rows = _scoped(get_db()).filter(ApiUsage.created_at >= since).with_entities(
            ApiUsage.created_at, ApiUsage.status_code, ApiUsage.response_time).all()
        buckets: Dict[datetime, Dict[str, Any]] = defaultdict(lambda: {'count': 0, 'successful': 0, 'errors': 0, 'time': 0.0})
        for created_at, status, response_time in rows:
            b = buckets[_bucket(created_at, group_by)]
            b['count'] += 1
            b['successful' if status < 400 else 'errors'] += 1
            b['time'] += response_time
        timeline = [{
            'period': period.isoformat(),
            'count': b['count'],
            'successful': b['successful'],
            'errors': b['errors'],
            'avg_response_time': round(b['time'] / b['count'], 4),
        } for period, b in sorted(buckets.items())]
        return jsonify({'timeline': timeline, 'period': {'days': days, 'group_by': group_by}, 'timestamp': now_iso()})

    @app.route('/api/v1/analytics/top-endpoints', methods=['GET'])
    @require_auth
    def api_top_endpoints():
        """Most-called endpoints."""
        start, end = dates(('start_date', False), ('end_date', True))
        try:
            limit = min(max(int(request.args.get('limit', 10)), 1), 100)
        except ValueError:
            return api_error(400, 'VAL_001', 'limit must be a number')
        rows = _range(_scoped(get_db()), start, end).with_entities(
            ApiUsage.endpoint, func.count(ApiUsage.id), func.avg(ApiUsage.response_time),
            func.coalesce(func.sum(ApiUsage.response_size), 0),
        ).group_by(ApiUsage.endpoint).order_by(func.count(ApiUsage.id).desc()).limit(limit).all()
        return jsonify({'top_endpoints': [{
            'endpoint': e, 'count': c, 'avg_response_time': round(float(t or 0), 4), 'total_response_size': int(s),
        } for e, c, t, s in rows], 'limit': limit, 'timestamp': now_iso()})

    @app.route('/api/v1/analytics/compare', methods=['GET'])
    @require_auth
    def api_compare_periods():
        """Compare two date ranges."""
        p1s, p1e, p2s, p2e = dates(('period1_start', False), ('period1_end', True),
                                   ('period2_start', False), ('period2_end', True))
        if not all((p1s, p1e, p2s, p2e)):
            return api_error(400, 'VAL_001', 'period1_start, period1_end, period2_start and period2_end are required')
        db = get_db()
        s1 = _summary(_range(_scoped(db), p1s, p1e))
        s2 = _summary(_range(_scoped(db), p2s, p2e))
        return jsonify({'comparison': {
            'period1': {'start': p1s.isoformat(), 'end': p1e.isoformat(), 'stats': s1},
            'period2': {'start': p2s.isoformat(), 'end': p2e.isoformat(), 'stats': s2},
            'changes': {k: _change(s1[k], s2[k]) for k in s1},
        }, 'timestamp': now_iso(), 'request_id': g.request_id})

    @app.route('/api/v1/analytics/export', methods=['GET'])
    @require_auth
    def api_export_analytics():
        """Download raw request logs as CSV or JSON."""
        start, end = dates(('start_date', False), ('end_date', True))
        fmt = request.args.get('format', 'json')
        if fmt not in ('csv', 'json'):
            return api_error(400, 'VAL_001', 'format must be csv or json')
        rows = _range(_scoped(get_db()), start, end).order_by(ApiUsage.created_at).limit(MAX_EXPORT_ROWS).all()
        records: List[Dict[str, Any]] = [{
            'timestamp': r.created_at.isoformat(), 'method': r.method, 'endpoint': r.endpoint,
            'status_code': r.status_code, 'response_time': r.response_time, 'request_size': r.request_size,
            'response_size': r.response_size, 'units': r.units, 'api_key_id': r.api_key_id,
        } for r in rows]
        return file_response(records, fmt, 'lexai-usage')


def csv_safe(value: Any) -> Any:
    """Stop spreadsheet apps from treating exported text as a formula."""
    if isinstance(value, str) and value[:1] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + value
    return value


def file_response(records: List[Dict[str, Any]], fmt: str, name: str):
    if fmt == 'csv':
        buffer = io.StringIO()
        if records:
            writer = csv.DictWriter(buffer, fieldnames=list(records[0].keys()))
            writer.writeheader()
            for record in records:
                writer.writerow({k: csv_safe(v) for k, v in record.items()})
        response = make_response(buffer.getvalue())
        response.mimetype = 'text/csv'
    else:
        response = make_response(json.dumps(records, default=str, indent=2))
        response.mimetype = 'application/json'
    response.headers['Content-Disposition'] = f'attachment; filename="{name}.{fmt}"'
    return response
