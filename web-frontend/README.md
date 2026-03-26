# Balbes Web Frontend

Modern React + Vite dashboard for the Balbes Multi-Agent System.

## Features

- 🎨 Beautiful UI with Tailwind CSS and shadcn/ui
- 🔐 JWT Authentication
- 📊 Real-time Dashboard
- 🤖 Agent Management
- ✅ Task Tracking
- ⚡ Skills Management
- 🌓 Dark/Light theme support
- 🔄 WebSocket for live updates

## Tech Stack

- **React 18** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool
- **TailwindCSS** - Styling
- **shadcn/ui** - UI components
- **React Router** - Navigation
- **Zustand** - State management
- **TanStack Query** - Data fetching
- **Axios** - HTTP client
- **date-fns** - Date formatting

## Quick Start

### Install Dependencies

```bash
cd web-frontend
npm install
```

### Run Development Server

```bash
npm run dev
```

Visit `http://localhost:5173`

### Build for Production

```bash
npm run build
npm run preview
```

## Project Structure

```
web-frontend/
├── src/
│   ├── components/
│   │   ├── ui/            # shadcn/ui components
│   │   ├── Layout.tsx     # Main layout
│   │   └── ThemeProvider.tsx
│   ├── pages/
│   │   ├── LoginPage.tsx
│   │   ├── DashboardPage.tsx
│   │   ├── AgentsPage.tsx
│   │   ├── TasksPage.tsx
│   │   └── SkillsPage.tsx
│   ├── stores/
│   │   └── authStore.ts   # Zustand auth store
│   ├── lib/
│   │   ├── api.ts         # API client
│   │   └── utils.ts       # Utilities
│   ├── App.tsx
│   ├── main.tsx
│   └── index.css
├── package.json
├── tsconfig.json
├── vite.config.ts
└── tailwind.config.js
```

## Default Credentials

- **Username**: admin
- **Password**: admin123

## API Integration

The frontend connects to Web Backend API at `http://localhost:8200`

All API requests automatically include JWT token in headers.

## Theme Toggle

Click the moon/sun icon in the sidebar to switch between dark and light themes.

## Available Pages

- **Dashboard** (`/`) - System overview and statistics
- **Agents** (`/agents`) - List and manage AI agents
- **Tasks** (`/tasks`) - View task execution history
- **Skills** (`/skills`) - Browse available skills

## Development

```bash
# Run dev server
npm run dev

# Type checking
npm run build

# Lint code
npm run lint
```

## Environment Variables

Create `.env` file:

```env
VITE_API_URL=http://localhost:8200
```

## Production Deployment

```bash
# Build
npm run build

# Output in dist/
# Serve with any static server
```
