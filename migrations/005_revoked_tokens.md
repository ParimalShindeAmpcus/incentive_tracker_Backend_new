# SEC-10 Revoked Tokens

Tokens generated via `POST /api/v1/auth/login` and `POST /api/v1/auth/refresh` now include a unique identifier `jti`.
Upon logout, these `jti` values are extracted and added to this new table to prevent reuse of already-issued, unexpired tokens.

## `revoked_tokens`

- `id`: Primary key
- `jti`: Unique token identifier. Indexed for fast lookup during authentication.
- `user_id`: Optional reference to the user who the token belonged to.
- `token_type`: String `access` or `refresh`.
- `expires_at`: The actual expiration of the JWT. Used to safely purge records from this table once the tokens would have naturally expired anyway.
- `revoked_at`: Timestamp when the token was invalidated.

Created via `Base.metadata.create_all` during initialization.
