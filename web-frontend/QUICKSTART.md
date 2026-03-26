# Balbes Web Frontend - Quick Start Guide

## Installation

```bash
cd /home/balbes/projects/dev/web-frontend

# Install dependencies
npm install
```

## Development

```bash
# Start dev server
npm run dev

# Open browser to http://localhost:5173
```

## Default Login

- Username: `admin`
- Password: `admin123`

## Pages

- **/** - Dashboard with system overview
- **/agents** - Manage AI agents
- **/tasks** - View task history
- **/skills** - Browse skills

## Features

✅ JWT Authentication
✅ Dark/Light Theme
✅ Real-time Updates
✅ Responsive Design
✅ Modern UI (shadcn/ui)

## Build

```bash
npm run build
npm run preview
```

## API Connection

Backend API: `http://localhost:8200`
Configured in `vite.config.ts` proxy
