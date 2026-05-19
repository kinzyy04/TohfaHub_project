import sys
import asyncio
import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app

# Set the selector event loop policy on Windows for psycopg async compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="session")
async def engine():
    """Create a session-wide SQLAlchemy engine and setup tables."""
    test_db_url = settings.TEST_DATABASE_URL
    if not test_db_url:
        raise ValueError("TEST_DATABASE_URL is not configured in environment/.env")
        
    test_engine = create_async_engine(test_db_url, echo=False)
    
    # Drop and create all tables for the clean test database
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        
    yield test_engine
    
    # Drop all tables at the end of the test session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        
    await test_engine.dispose()

@pytest.fixture
async def db(engine):
    """Wrap each test in a transaction that is rolled back on teardown."""
    async with engine.connect() as connection:
        # Begin the transaction on the connection
        transaction = await connection.begin()
        
        # Create a session bound to the connection
        Session = async_sessionmaker(
            bind=connection,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        
        async with Session() as session:
            yield session
            # Rollback the transaction to revert all database operations in the test
            await transaction.rollback()

@pytest.fixture
async def client(db):
    """HTTPX AsyncClient targeting the FastAPI application with overridden get_db."""
    async def override_get_db():
        yield db
        
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()

async def create_user_token_helper(client: AsyncClient, role: str) -> str:
    """Helper function to sign up and login a fresh user with a specific role."""
    unique_id = uuid.uuid4().hex
    email = f"{role}_{unique_id}@example.com"
    password = "SecurePassword123!"
    
    # Signup a new user
    signup_response = await client.post(
        "/api/v1/auth/signup",
        json={"email": email, "password": password, "role": role}
    )
    assert signup_response.status_code == 201
    
    # Login to obtain token
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password, "role": role}
    )
    assert login_response.status_code == 200
    return login_response.json()["access_token"]

@pytest.fixture
async def buyer_token(client) -> str:
    """Create a fresh buyer user and return their access token."""
    return await create_user_token_helper(client, "buyer")

@pytest.fixture
async def seller_token(client) -> str:
    """Create a fresh seller user and return their access token."""
    return await create_user_token_helper(client, "seller")

@pytest.fixture
async def admin_token(client) -> str:
    """Create a fresh admin user and return their access token."""
    return await create_user_token_helper(client, "admin")
