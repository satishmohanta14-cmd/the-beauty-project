import asyncio
import urllib.parse
import asyncpg

password = '@$MvDAAEG5d$@W8'
encoded_password = urllib.parse.quote_plus(password)
database_url = f"postgresql://postgres:{encoded_password}@db.heqthfmfzeurlgwnibks.supabase.co:5432/postgres"

async def test_conn():
    print(f"Connecting to: {database_url[:30]}...")
    try:
        conn = await asyncpg.connect(database_url, ssl="require")
        ver = await conn.fetchval("SELECT version();")
        print("Connected successfully!")
        print("PostgreSQL Version:", ver)
        has_vector = await conn.fetchval("SELECT count(*) FROM pg_extension WHERE extname = 'vector';")
        print("pgvector extension installed:", bool(has_vector))
        if not has_vector:
            print("Installing pgvector extension...")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            print("pgvector installed successfully!")
        await conn.close()
    except Exception as e:
        print("Connection failed:", e)

if __name__ == "__main__":
    asyncio.run(test_conn())
