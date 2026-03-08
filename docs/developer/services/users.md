# Users Service

The users service manages customer profiles and avatar images. It is deliberately the smallest service in the Arrive platform, handling only three routes. This simplicity is intentional: user identity lives in Cognito, and the users service exists solely to store mutable profile data that Cognito custom attributes are not well suited for, such as display names, phone numbers, and profile pictures.

All source code lives under `services/users/src/`.


## Architecture Overview

The service runs as a single Lambda function behind an HTTP API Gateway. There are no background workers, no async jobs, and no cross-service event integrations. The service touches two AWS resources: a DynamoDB table for profile data and an S3 bucket for avatar images.

Key source files:

- **app.py** -- Router. Three routes plus a health check.
- **handlers/users.py** -- All business logic: get profile, update profile, create avatar upload URL.
- **utils.py** -- Shared imports hub. DynamoDB table reference, S3 client, and re-exported shared-layer functions.


## Why a Separate Service

The users service could have been folded into the restaurants service or implemented
as Cognito custom attributes. It exists as a standalone service for three reasons:

1. **Cognito attribute limitations**: Cognito custom attributes are write-once in terms
   of schema and have strict size limits (max 2048 characters per attribute). Profile
   fields like display name and phone number change frequently and benefit from the
   flexibility of a DynamoDB record that can be extended without modifying the Cognito
   user pool schema.

2. **Blast radius isolation**: A bug in profile management should not affect restaurant
   operations or order processing. Separate Lambda functions mean separate concurrency
   limits, separate error rates, and separate deployment pipelines. A surge in profile
   updates cannot starve the orders service of Lambda concurrency.

3. **Data ownership clarity**: The users table is the single source of truth for mutable
   profile data. No other service writes to it. This eliminates the coordination problems
   that arise when multiple services share a table, and makes it clear which team owns
   the schema and migration path.


## Route Structure

The service exposes three routes plus a health check:

| Method | Path                              | Description                        |
|--------|-----------------------------------|------------------------------------|
| GET    | /v1/users/health                  | Health check (returns service name)|
| GET    | /v1/users/me                      | Retrieve authenticated user profile|
| PUT    | /v1/users/me                      | Update profile fields              |
| POST   | /v1/users/me/avatar/upload-url    | Get presigned S3 upload URL        |

All routes use the `/me` convention, meaning the user ID comes from the JWT token, not
the URL path. This prevents users from accessing or modifying other users' profiles by
guessing IDs. There is no admin endpoint for viewing other users' profiles -- the admin
portal reads user information from Cognito directly.


## Profile Management

### Get Profile

The `GET /v1/users/me` endpoint retrieves the authenticated user's profile from DynamoDB
using the `user_id` extracted from the Cognito JWT `sub` claim. If no profile exists,
it returns 404 rather than an empty object. The response is decorated with a presigned
S3 GET URL for the avatar image if a `picture` key is present on the record.

The `_with_picture_url()` decorator function processes the `picture` field through
`_extract_avatar_key()` to normalize it (handling raw keys, s3:// URLs, and full HTTPS
URLs), then generates a presigned GET URL with a configurable TTL. The raw key is
preserved in the `picture` field for equality checks, and the presigned URL is provided
as a separate `picture_url` field.

### Update Profile

The `PUT /v1/users/me` endpoint accepts partial updates to three fields: `name`, `phone_number`, and `picture`. All other fields (including `role`, `email`, and `user_id`) are immutable and are silently ignored if present in the request body.

Input validation is strict:

- **name**: Must be a non-empty string, maximum 255 characters. This prevents both blank display names and excessively long strings that could break UI layouts.
- **phone_number**: Must be a string, maximum 30 characters. The service does not enforce a phone number format because international formats vary widely, and format validation belongs in the client.
- **picture**: Must match the regex pattern `^avatars/[a-zA-Z0-9_-]+-\d+\.(jpg|png|webp|gif)$` and must start with `avatars/{user_id}-`. This two-layer validation ensures both correct format and correct ownership. Without the ownership check, a user could set their picture to another user's avatar key, effectively "stealing" their profile image.

The update uses a DynamoDB conditional expression (`attribute_exists(user_id)`) to ensure the profile already exists. If it does not exist, the handler returns 404 rather than silently creating a new record. This existence check prevents orphan profiles from being created by users who somehow bypassed the PostConfirmation trigger.

The update always sets `updated_at` to the current timestamp, even if no other fields changed. If only `updated_at` would be set (meaning no valid fields were provided), the handler returns 400 with "No valid fields to update."


## Avatar Upload Flow

Avatar uploads use a two-step presigned URL pattern:

1. The client calls `POST /v1/users/me/avatar/upload-url` with an optional `content_type` field.
2. The handler generates an S3 key in the format `avatars/{user_id}-{unix_timestamp}.{ext}` and returns a presigned PUT URL valid for 300 seconds.
3. The client uploads the image directly to S3 using the presigned URL.
4. The client calls `PUT /v1/users/me` with the `picture` field set to the S3 key to update their profile.

### Why Presigned URLs

Presigned URLs keep binary image data out of the Lambda function entirely. The client uploads directly to S3, which is designed for large object storage and has much higher throughput limits than Lambda. This also means the API Gateway payload size limit (10 MB for HTTP APIs) is not a constraint on image size -- S3 presigned URLs support objects up to 5 GB.

### S3 Key Scoping

The S3 key includes the user ID as a prefix (`avatars/{user_id}-`), which serves two purposes:

1. **Access control**: The profile update handler verifies that the `picture` value starts with the authenticated user's prefix, preventing cross-user image references.
2. **Cleanup**: If avatar cleanup is ever needed, all of a user's images can be found by prefix listing.

The timestamp in the key name (`{user_id}-{unix_timestamp}`) ensures uniqueness across uploads without collision risk. It also provides a natural chronological ordering of a user's avatar history.

### Content Type Validation

The handler accepts four image types: JPEG, PNG, WebP, and GIF. The content type is embedded in the presigned URL's `ContentType` parameter, which S3 enforces during upload. If the client sends a file with a different content type, S3 rejects the upload. SVG and other non-raster formats are not supported because they can contain embedded scripts.

### Avatar Read URLs

When a profile is retrieved, the `_with_picture_url()` function checks if the `picture` field contains a valid avatar key and generates a presigned GET URL with a configurable TTL (default 900 seconds, controlled by `AVATAR_GET_URL_TTL_SECONDS`). The raw S3 key is preserved in the `picture` field, and the presigned URL is added as a separate `picture_url` field. This allows clients to cache the key for equality checks while using the URL for display.

The `_extract_avatar_key()` function is intentionally flexible: it can parse raw S3 keys, `s3://` scheme URLs, and full HTTPS presigned URLs, extracting the bare key in all cases. This handles the case where an older client might have stored a full URL in the `picture` field.


## PostConfirmation Trigger

The PostConfirmation trigger is a separate Lambda function defined in the root SAM
template (not in the users service's code directory). It fires when a new user confirms
their Cognito account and creates an initial profile record in the UsersTable with the
user's `sub`, `email`, and `cognito:username`.

This trigger ensures that every Cognito user has a corresponding profile record before
they ever call the users service. Without it, the first `GET /v1/users/me` call would
return 404, which would force every client to handle the "profile not yet created" case.
By pre-creating the profile at signup, the client can always assume that a successful
authentication implies a valid profile exists.

The trigger is idempotent: if the profile record already exists (which should not happen
in normal flow, but could occur if the trigger fires twice due to Lambda retry behavior),
the DynamoDB `put_item` will overwrite it with the same data.

### Data Flow

The complete profile lifecycle is:

1. User signs up and confirms their account in Cognito.
2. PostConfirmation trigger creates a minimal profile record (user_id, email, username).
3. User calls `GET /v1/users/me` and sees their profile.
4. User calls `PUT /v1/users/me` to set their display name and phone number.
5. User calls `POST /v1/users/me/avatar/upload-url`, uploads an image to S3, then
   calls `PUT /v1/users/me` with the S3 key to set their avatar.

Steps 3-5 can happen in any order, and steps 4-5 are optional. The service is designed
to work correctly whether the user completes none, some, or all of the optional steps.


## Security Considerations

### Ownership Enforcement

Every endpoint enforces ownership through the JWT `sub` claim. There is no way to read
or modify another user's profile through this service. The ownership check happens at
the authentication layer (extracting user_id from claims), not at the data layer, so
there is no TOCTOU race between checking ownership and accessing the data.

### Picture Field Validation

The `picture` field has the strictest validation in the service. It must match a specific
regex pattern (`^avatars/[a-zA-Z0-9_-]+-\d+\.(jpg|png|webp|gif)$`) AND must start with
`avatars/{user_id}-`. This two-layer check prevents:

- **Path traversal**: The regex blocks `../` sequences and any path outside the `avatars/`
  prefix.
- **Cross-user references**: The prefix check ensures the key contains the authenticated
  user's ID, preventing a user from pointing their profile to another user's uploaded image.
- **Arbitrary S3 key injection**: Without validation, a user could set their picture to
  any S3 key in the bucket, potentially referencing internal system files.


## Shared Module Integration

The users service imports from `utils.py`, which re-exports `get_user_claims` from `shared.auth` and `make_response` from `shared.serialization`. The DynamoDB table reference and S3 client are initialized at module load time (Lambda cold start) and reused across invocations, following the Lambda best practice of keeping AWS client initialization outside the handler function.
