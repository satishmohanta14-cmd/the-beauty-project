-- Ensure the pgvector extension is available in the target database.
-- This runs once when the container is first initialised.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- provides gen_random_uuid() on PG < 13
