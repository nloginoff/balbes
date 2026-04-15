"""
Web Backend FastAPI Application for Balbes Dashboard.

Provides REST API and WebSocket for:
- User authentication
- Agent and task management
- Skill management
- System monitoring
- Real-time updates
"""

import json
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from api import agents as agents_api
from api import dashboard as dashboard_api
from api import skills as skills_api
from api import tasks as tasks_api
from auth import (
    APIService,
    AuthManager,
    AuthToken,
    LoginRequest,
    RegisterRequest,
    User,
)
from fastapi import (
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.config import get_settings

# Initialize settings
settings = get_settings()

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("web_backend")

# Global instances
auth_manager: AuthManager | None = None
api_service: APIService | None = None
active_connections: dict[str, WebSocket] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """
    FastAPI lifespan context manager.

    Handles startup and shutdown.
    """
    global auth_manager, api_service

    logger.info("Starting Web Backend Service...")

    try:
        # Initialize auth manager
        auth_manager = AuthManager()
        logger.info("Auth Manager initialized")

        # Initialize API service
        api_service = APIService()
        await api_service.connect()
        logger.info("API Service initialized")

    except Exception as e:
        logger.error(f"Failed to initialize Web Backend: {e}")
        raise

    # App is running
    yield

    # Shutdown
    logger.info("Shutting down Web Backend Service...")

    if api_service:
        await api_service.close()

    logger.info("Web Backend Service stopped")


# Create FastAPI application
app = FastAPI(
    title="Balbes Web Backend",
    description="API for Balbes Multi-Agent System Dashboard",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Helper Functions
# ============================================================================


def get_current_user(authorization: str | None = Header(None)) -> str:
    """Get current authenticated user"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authentication scheme")

        if not auth_manager:
            raise HTTPException(status_code=503, detail="Auth service unavailable")

        user_id = auth_manager.verify_token(token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        return user_id

    except (ValueError, HTTPException):
        raise HTTPException(status_code=401, detail="Invalid authentication")


# ============================================================================
# Exception Handlers
# ============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions"""
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "error_code": "INTERNAL_ERROR",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


# ============================================================================
# Include API Routers
# ============================================================================

app.include_router(agents_api.router, dependencies=[Depends(get_current_user)])
app.include_router(tasks_api.router, dependencies=[Depends(get_current_user)])
app.include_router(skills_api.router, dependencies=[Depends(get_current_user)])
app.include_router(dashboard_api.router, dependencies=[Depends(get_current_user)])


# ============================================================================
# Authentication Endpoints
# ============================================================================


@app.post("/api/v1/auth/login", response_model=AuthToken)
async def login(request: LoginRequest) -> AuthToken:
    """
    Login endpoint.

    Args:
        request: Login credentials

    Returns:
        Authentication token
    """
    if not auth_manager:
        raise HTTPException(status_code=503, detail="Auth service unavailable")

    user = auth_manager.authenticate_user(request.username, request.password)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = auth_manager.create_access_token(user.user_id)

    logger.info(f"User logged in: {request.username}")

    return token


@app.post("/api/v1/auth/register", response_model=User)
async def register(request: RegisterRequest) -> User:
    """
    Register new user.

    Args:
        request: Registration details

    Returns:
        Created user
    """
    if not auth_manager:
        raise HTTPException(status_code=503, detail="Auth service unavailable")

    user = auth_manager.register_user(
        username=request.username,
        email=request.email,
        password=request.password,
        full_name=request.full_name,
    )

    if not user:
        raise HTTPException(status_code=400, detail="Username already exists")

    logger.info(f"User registered: {request.username}")

    return user


@app.get("/api/v1/auth/me", response_model=User)
async def get_current_user_info(user_id: str = Depends(get_current_user)) -> User:
    """
    Get current user info.

    Returns:
        Current user details
    """
    if not auth_manager:
        raise HTTPException(status_code=503, detail="Auth service unavailable")

    user = auth_manager.get_user(user_id)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


# ============================================================================
# Health & Status Endpoints
# ============================================================================


@app.get("/health")
async def health_check() -> dict:
    """
    Health check endpoint.

    Returns:
        dict: Health status
    """
    if not api_service:
        return {
            "service": "web_backend",
            "status": "unhealthy",
            "reason": "API service not initialized",
        }

    services_status = await api_service.check_services_health()

    return {
        "service": "web_backend",
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "services": services_status,
    }


@app.get("/")
async def root() -> dict:
    """Root endpoint with service information"""
    return {
        "service": "Balbes Web Backend",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
        "description": "API for Balbes Multi-Agent System Dashboard",
    }


# ============================================================================
# WebSocket for Real-time Updates
# ============================================================================


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    """
    WebSocket endpoint for real-time updates.

    Args:
        websocket: WebSocket connection
        client_id: Client identifier
    """
    await websocket.accept()
    active_connections[client_id] = websocket

    logger.info(f"WebSocket client connected: {client_id}")

    try:
        while True:
            data = await websocket.receive_text()

            # Handle incoming messages
            message = json.loads(data)
            logger.debug(f"WebSocket message from {client_id}: {message}")

            # Echo back or broadcast
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "ack",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "message": "Message received",
                    }
                )
            )

    except WebSocketDisconnect:
        del active_connections[client_id]
        logger.info(f"WebSocket client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if client_id in active_connections:
            del active_connections[client_id]


async def broadcast_message(message: dict[str, any]) -> None:
    """
    Broadcast message to all connected WebSocket clients.

    Args:
        message: Message to broadcast
    """
    disconnected = []

    for client_id, connection in active_connections.items():
        try:
            await connection.send_text(json.dumps(message))
        except Exception as e:
            logger.warning(f"Failed to send to {client_id}: {e}")
            disconnected.append(client_id)

    # Clean up disconnected clients
    for client_id in disconnected:
        del active_connections[client_id]


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Web Backend on port {settings.web_backend_port}")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.web_backend_port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
