# AWS Route 53 Clone

A polished mock of the Route 53 console built with Next.js, FastAPI, and SQLite. It provides persistent authentication sessions, hosted zone CRUD, and DNS record CRUD without connecting to AWS.

## Included power features

- Import records from BIND zone files or a prior JSON export.
- Export any hosted zone as BIND (`.zone`) or JSON.
- Persisted dark mode toggle in the console header.
- Keyboard shortcuts: press `N` to open the create form and `Esc` to close a dialog.
- Select multiple records and delete them in one operation.

## Run locally

1. Start the API:
   ```bash
   cd backend
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8000
   ```
2. In another terminal, start the web app:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
3. Open http://localhost:3000 and sign in with any email/password. The default `admin@example.com` / `demo` is prefilled.

For deployment, set `frontend/.env.example`'s `NEXT_PUBLIC_API_URL` to the public FastAPI URL and set the backend `FRONTEND_ORIGINS` value to the Netlify site URL. The API health check is available at `GET /health`.

## Architecture

- `backend/app/main.py` exposes REST endpoints and keeps route handlers cohesive.
- `backend/app/schemas.py` validates API inputs; `database.py` initializes and accesses SQLite.
- `frontend/app/page.tsx` contains the responsive console shell and connected Route 53 views; `frontend/lib/api.ts` centralizes authenticated requests.
- SQLite is stored at `backend/route53.db` and is created automatically at API startup.

## Schema

`users` store mock identities; `sessions` store persistent opaque tokens; `hosted_zones` own `records` through a foreign key with cascading deletes. Records include name, type, value, TTL, and routing policy.

## API

- Auth: `POST /auth/login`, `POST /auth/logout`, `GET /auth/session`
- Hosted zones: `GET|POST /hosted-zones`, `GET|PUT|DELETE /hosted-zones/{id}`
- Records: `GET|POST /hosted-zones/{zone_id}/records`, `GET|PUT|DELETE /hosted-zones/{zone_id}/records/{record_id}`
- Import/export: `POST /hosted-zones/{zone_id}/import`, `GET /hosted-zones/{zone_id}/export?format=json|bind`
- Bulk records: `POST /hosted-zones/{zone_id}/records/bulk-delete`

List endpoints accept `q`, `page`, and `page_size`; records additionally accept `type`.

## Assumptions / Mocked Data / Notes

- This is a Route 53 management-plane clone; it does not perform real DNS resolution, propagation, health evaluation, or AWS API calls.
- Login is intentionally mocked. Any non-empty email and password are accepted, and a demo user/session is persisted in SQLite.
- IAM, AWS accounts, organizations, billing, VPC associations, Traffic Flow, Resolver, Profiles, and Health Checks are represented only by placeholder UI sections or metadata.
- Hosted-zone IDs and record IDs are locally generated; they are not valid AWS identifiers and cannot be used with AWS.
- Public/private hosted-zone behavior is stored as application metadata only. No VPC or network isolation is implemented.
- Supported record types are `A`, `AAAA`, `CNAME`, `TXT`, `MX`, `NS`, `PTR`, `SRV`, and `CAA`. General fields are validated, but full RFC-level validation for every record value is not implemented.
- BIND import supports common lines containing name, TTL, `IN`, type, and value. Complex directives, multiline records, `$INCLUDE`, and advanced routing policies may be skipped.
- SQLite is suitable for local development and a single-instance demo. Production scaling should migrate persistence to PostgreSQL and sessions to a shared store such as Redis.
- The static frontend requires `NEXT_PUBLIC_API_URL` at build time. The backend requires `FRONTEND_ORIGINS`; these values must be configured separately in Netlify and the backend host.
- Browser local storage is used for the mock bearer token. Production authentication should use short-lived, server-managed sessions in secure HttpOnly cookies.
- Data is intentionally isolated to the deployed database. The repository does not include real customer, AWS, DNS, or credential data.
