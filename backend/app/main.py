import json
import os
import re
import secrets
import uuid
from typing import Optional
from fastapi import FastAPI, Depends, Header, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from .database import db, init_db
from .schemas import LoginInput, ZoneInput, RecordInput, ImportInput, BulkDeleteInput

app = FastAPI(title='Route 53 Clone API', version='1.0.0')
FRONTEND_ORIGINS = [origin.strip() for origin in os.getenv('FRONTEND_ORIGINS', 'http://localhost:3000').split(',') if origin.strip()]
app.add_middleware(CORSMiddleware, allow_origins=FRONTEND_ORIGINS, allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

@app.on_event('startup')
def startup(): init_db()

@app.get('/health')
def health():
    return {'status': 'ok', 'service': 'route53-api'}

def session_user(authorization: Optional[str] = Header(None)):
    token = authorization.removeprefix('Bearer ').strip() if authorization else ''
    with db() as conn:
        row = conn.execute('SELECT u.id, u.email, u.name, u.account_id FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=?', (token,)).fetchone()
    if not row: raise HTTPException(401, 'Your session has expired. Please sign in again.')
    return dict(row)

def page_params(page: int, page_size: int):
    if page < 1 or not 1 <= page_size <= 100: raise HTTPException(422, 'page must be positive and page_size must be 1–100')
    return (page - 1) * page_size

@app.post('/auth/login')
def login(payload: LoginInput):
    with db() as conn:
        user = conn.execute('SELECT * FROM users WHERE email=?', (payload.email.strip().lower(),)).fetchone()
        if not user:
            conn.execute('INSERT INTO users(email,name,account_id) VALUES(?,?,?)', (payload.email.strip().lower(), 'Route 53 Administrator', '1234-5678-9012'))
            user = conn.execute('SELECT * FROM users WHERE email=?', (payload.email.strip().lower(),)).fetchone()
        token = secrets.token_urlsafe(32)
        conn.execute('INSERT INTO sessions(token,user_id) VALUES(?,?)', (token, user['id']))
    return {'token': token, 'user': {'email': user['email'], 'name': user['name'], 'account_id': user['account_id']}}

@app.post('/auth/logout', status_code=204)
def logout(authorization: Optional[str] = Header(None)):
    token = authorization.removeprefix('Bearer ').strip() if authorization else ''
    with db() as conn: conn.execute('DELETE FROM sessions WHERE token=?', (token,))
    return Response(status_code=204)

@app.get('/auth/session')
def session(user=Depends(session_user)): return {'user': user}

@app.get('/hosted-zones')
def list_zones(q: str = '', page: int = 1, page_size: int = 10, user=Depends(session_user)):
    offset = page_params(page, page_size); needle = f'%{q.strip()}%'
    with db() as conn:
        total = conn.execute('SELECT COUNT(*) FROM hosted_zones WHERE name LIKE ? OR comment LIKE ?', (needle, needle)).fetchone()[0]
        rows = conn.execute('''SELECT z.*, COUNT(r.id) AS record_count FROM hosted_zones z LEFT JOIN records r ON r.zone_id=z.id
          WHERE z.name LIKE ? OR z.comment LIKE ? GROUP BY z.id ORDER BY z.name LIMIT ? OFFSET ?''', (needle, needle, page_size, offset)).fetchall()
    return {'items': [dict(r) for r in rows], 'total': total, 'page': page, 'page_size': page_size}

@app.post('/hosted-zones', status_code=201)
def create_zone(payload: ZoneInput, user=Depends(session_user)):
    zone = {'id': 'Z' + uuid.uuid4().hex[:12].upper(), **payload.model_dump()}
    with db() as conn:
        conn.execute('INSERT INTO hosted_zones(id,name,comment,private_zone) VALUES(:id,:name,:comment,:private_zone)', zone)
    return {**zone, 'record_count': 0}

@app.get('/hosted-zones/{zone_id}')
def get_zone(zone_id: str, user=Depends(session_user)):
    with db() as conn: row = conn.execute('SELECT * FROM hosted_zones WHERE id=?', (zone_id,)).fetchone()
    if not row: raise HTTPException(404, 'Hosted zone not found')
    return dict(row)

@app.put('/hosted-zones/{zone_id}')
def update_zone(zone_id: str, payload: ZoneInput, user=Depends(session_user)):
    with db() as conn:
        if not conn.execute('SELECT 1 FROM hosted_zones WHERE id=?', (zone_id,)).fetchone(): raise HTTPException(404, 'Hosted zone not found')
        conn.execute('UPDATE hosted_zones SET name=:name, comment=:comment, private_zone=:private_zone WHERE id=:id', {**payload.model_dump(), 'id': zone_id})
    return {'id': zone_id, **payload.model_dump()}

@app.delete('/hosted-zones/{zone_id}', status_code=204)
def delete_zone(zone_id: str, user=Depends(session_user)):
    with db() as conn:
        if not conn.execute('DELETE FROM hosted_zones WHERE id=?', (zone_id,)).rowcount: raise HTTPException(404, 'Hosted zone not found')
    return Response(status_code=204)

@app.get('/hosted-zones/{zone_id}/export')
def export_zone(zone_id: str, format: str = 'json', user=Depends(session_user)):
    if format not in ('json', 'bind'): raise HTTPException(422, 'format must be json or bind')
    with db() as conn:
        zone = conn.execute('SELECT * FROM hosted_zones WHERE id=?', (zone_id,)).fetchone()
        if not zone: raise HTTPException(404, 'Hosted zone not found')
        records = [dict(r) for r in conn.execute('SELECT name,type,value,ttl,routing_policy FROM records WHERE zone_id=? ORDER BY name,type', (zone_id,))]
    if format == 'json': return {'format': 'json', 'content': json.dumps({'hosted_zone': dict(zone), 'records': records}, indent=2)}
    lines = [f'; Exported from Route 53 Clone', f'$ORIGIN {zone["name"].rstrip(".")}.', '$TTL 300']
    lines.extend(f'{r["name"]}\t{r["ttl"]}\tIN\t{r["type"]}\t{r["value"]}' for r in records)
    return {'format': 'bind', 'content': '\n'.join(lines) + '\n'}

@app.post('/hosted-zones/{zone_id}/import')
def import_records(zone_id: str, payload: ImportInput, user=Depends(session_user)):
    allowed = {'A', 'AAAA', 'CNAME', 'TXT', 'MX', 'NS', 'PTR', 'SRV', 'CAA'}
    with db() as conn:
        zone = conn.execute('SELECT name FROM hosted_zones WHERE id=?', (zone_id,)).fetchone()
        if not zone: raise HTTPException(404, 'Hosted zone not found')
        if payload.format == 'json':
            try: parsed = json.loads(payload.content); entries = parsed.get('records', parsed) if isinstance(parsed, dict) else parsed
            except json.JSONDecodeError: raise HTTPException(422, 'Invalid JSON export file')
            if not isinstance(entries, list): raise HTTPException(422, 'JSON must contain a records array')
            candidates = [(str(x.get('name','')).strip(), str(x.get('type','')).upper(), str(x.get('value','')).strip(), int(x.get('ttl',300)), str(x.get('routing_policy','Simple'))) for x in entries if isinstance(x, dict)]
        else:
            origin = zone['name'].rstrip('.')
            candidates = []
            for raw in payload.content.splitlines():
                line = raw.split(';', 1)[0].strip()
                if not line: continue
                if line.upper().startswith('$ORIGIN'):
                    parts=line.split(); origin=parts[1].rstrip('.') if len(parts)>1 else origin; continue
                if line.startswith('$'): continue
                parts = re.split(r'\s+', line, maxsplit=4)
                if len(parts) < 4: continue
                name, ttl, dns_class, record_type = parts[:4]; value = parts[4] if len(parts) > 4 else ''
                if not ttl.isdigit() or dns_class.upper() != 'IN': continue
                if name == '@': name = origin
                elif not name.endswith('.'): name = f'{name}.{origin}'
                else: name = name.rstrip('.')
                candidates.append((name, record_type.upper(), value, int(ttl), 'Simple'))
        valid = [(n,t,v,ttl,p) for n,t,v,ttl,p in candidates if n and t in allowed and v and 0 <= ttl <= 2147483647]
        for name, record_type, value, ttl, policy in valid:
            conn.execute('INSERT INTO records(id,zone_id,name,type,value,ttl,routing_policy) VALUES(?,?,?,?,?,?,?)', (uuid.uuid4().hex, zone_id, name, record_type, value, ttl, policy))
    return {'imported': len(valid), 'skipped': len(candidates) - len(valid)}

def require_zone(conn, zone_id):
    if not conn.execute('SELECT 1 FROM hosted_zones WHERE id=?', (zone_id,)).fetchone(): raise HTTPException(404, 'Hosted zone not found')

@app.get('/hosted-zones/{zone_id}/records')
def list_records(zone_id: str, q: str = '', type: str = '', page: int = 1, page_size: int = 25, user=Depends(session_user)):
    offset = page_params(page, page_size); needle = f'%{q.strip()}%'; type_needle = f'%{type.strip()}%'
    with db() as conn:
        require_zone(conn, zone_id)
        total = conn.execute('SELECT COUNT(*) FROM records WHERE zone_id=? AND (name LIKE ? OR value LIKE ?) AND type LIKE ?', (zone_id, needle, needle, type_needle)).fetchone()[0]
        rows = conn.execute('SELECT * FROM records WHERE zone_id=? AND (name LIKE ? OR value LIKE ?) AND type LIKE ? ORDER BY name,type LIMIT ? OFFSET ?', (zone_id, needle, needle, type_needle, page_size, offset)).fetchall()
    return {'items': [dict(r) for r in rows], 'total': total, 'page': page, 'page_size': page_size}

@app.post('/hosted-zones/{zone_id}/records', status_code=201)
def create_record(zone_id: str, payload: RecordInput, user=Depends(session_user)):
    record = {'id': uuid.uuid4().hex, 'zone_id': zone_id, **payload.model_dump()}
    with db() as conn:
        require_zone(conn, zone_id); conn.execute('INSERT INTO records(id,zone_id,name,type,value,ttl,routing_policy) VALUES(:id,:zone_id,:name,:type,:value,:ttl,:routing_policy)', record)
    return record

@app.post('/hosted-zones/{zone_id}/records/bulk-delete')
def bulk_delete_records(zone_id: str, payload: BulkDeleteInput, user=Depends(session_user)):
    with db() as conn:
        require_zone(conn, zone_id)
        placeholders = ','.join('?' for _ in payload.record_ids)
        deleted = conn.execute(f'DELETE FROM records WHERE zone_id=? AND id IN ({placeholders})', (zone_id, *payload.record_ids)).rowcount
    return {'deleted': deleted}

@app.get('/hosted-zones/{zone_id}/records/{record_id}')
def get_record(zone_id: str, record_id: str, user=Depends(session_user)):
    with db() as conn: row = conn.execute('SELECT * FROM records WHERE id=? AND zone_id=?', (record_id, zone_id)).fetchone()
    if not row: raise HTTPException(404, 'Record not found')
    return dict(row)

@app.put('/hosted-zones/{zone_id}/records/{record_id}')
def update_record(zone_id: str, record_id: str, payload: RecordInput, user=Depends(session_user)):
    with db() as conn:
        if not conn.execute('SELECT 1 FROM records WHERE id=? AND zone_id=?', (record_id, zone_id)).fetchone(): raise HTTPException(404, 'Record not found')
        conn.execute('UPDATE records SET name=:name,type=:type,value=:value,ttl=:ttl,routing_policy=:routing_policy WHERE id=:id', {**payload.model_dump(), 'id': record_id})
    return {'id': record_id, 'zone_id': zone_id, **payload.model_dump()}

@app.delete('/hosted-zones/{zone_id}/records/{record_id}', status_code=204)
def delete_record(zone_id: str, record_id: str, user=Depends(session_user)):
    with db() as conn:
        if not conn.execute('DELETE FROM records WHERE id=? AND zone_id=?', (record_id, zone_id)).rowcount: raise HTTPException(404, 'Record not found')
    return Response(status_code=204)
