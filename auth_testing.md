# CQAS Authentication Testing

Use the seeded account `admin@cqas.local` / `admin123`.

1. POST `/api/auth/login` with JSON credentials and retain the `access_token` cookie.
2. GET `/api/auth/me` with the cookie; verify the safe user object is returned.
3. GET `/api/projects`; verify the seeded Navapark demo project is visible.
4. POST `/api/auth/logout`; verify subsequent `/api/auth/me` returns 401.
5. Register a unique email and verify it can log in.