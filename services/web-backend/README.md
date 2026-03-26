# Web Backend Service for Balbes Dashboard

**Web Backend** is the REST API server for the Balbes Web Dashboard. It provides:
- User authentication (JWT)
- Agent and task management
- Skill management
- System monitoring and statistics
- Real-time updates via WebSocket

## Features

### 🔐 Authentication
- JWT-based authentication
- User registration and login
- Secure password hashing
- Token expiration management

### 🎯 API Endpoints

#### Authentication
```
POST   /api/v1/auth/login              Login with credentials
POST   /api/v1/auth/register           Register new user
GET    /api/v1/auth/me                 Get current user info
```

#### Agents
```
GET    /api/v1/agents                  List all agents
GET    /api/v1/agents/{agent_id}       Get agent details & stats
```

#### Tasks
```
GET    /api/v1/tasks                   List tasks
POST   /api/v1/tasks                   Create new task
GET    /api/v1/tasks/{task_id}         Get task details
```

#### Skills
```
GET    /api/v1/skills                  List all skills
POST   /api/v1/skills                  Create new skill
```

#### Dashboard
```
GET    /api/v1/dashboard/status        Get system status
GET    /api/v1/dashboard/overview      Get complete overview
```

### 🔄 WebSocket
```
WS     /ws/{client_id}                 Real-time updates
```

## Configuration

Port: 8200 (default)
JWT Secret: From .env
Cors Origins: From .env

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run service
python main.py
```

## Usage Examples

### Login
```bash
curl -X POST http://localhost:8200/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'

# Response:
# {"access_token": "...", "token_type": "bearer", "expires_in": 86400}
```

### Get Agents (with auth)
```bash
curl http://localhost:8200/api/v1/agents \
  -H "Authorization: Bearer {token}"
```

### WebSocket Connection
```javascript
const ws = new WebSocket('ws://localhost:8200/ws/client-123');

ws.onmessage = (event) => {
  console.log('Update:', JSON.parse(event.data));
};

ws.send(JSON.stringify({type: 'subscribe', channel: 'tasks'}));
```

## Architecture

```
Web Backend (Port 8200)
├── Authentication (JWT)
├── API Routes
│   ├── Agents
│   ├── Tasks
│   ├── Skills
│   └── Dashboard
└── WebSocket
    └── Real-time Updates
```

## Files

- `main.py` - FastAPI app
- `auth.py` - Authentication & models
- `api/` - API route handlers
- `requirements.txt` - Dependencies
- `README.md` - This file
