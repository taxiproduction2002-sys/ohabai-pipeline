# Ohabai Pipeline Frontend

Next.js 15 inbox UI for Ohabai Pipeline. React 19, plain CSS, polls
backend every 3 seconds. No auth (fake login), no AI integration, no
media support.

## Local development

    cd frontend
    npm install

`.env.local` is pre-filled with production backend URL and company
ID. Edit if pointing at a different backend.

    npm run dev

Open http://localhost:3000.

## Layout

    [Sidebar 320px] [Chat thread flex-1] [Context panel 320px]

Sidebar shows conversations with last message preview, unread count
placeholder, and relative timestamp. Chat thread renders inbound/
outbound bubbles with timestamps and quoted-message placeholders.
Composer sends via existing /api/conversations/:id/send endpoint.
Context panel has placeholders for notes, AI suggestion, and company
brain.

## Production build

    npm run build
    npm run start

## Deployment

Vercel: `npx vercel` from the frontend directory.

Railway: add as a new service in the same project, root directory
`frontend/`, environment vars `NEXT_PUBLIC_API_BASE_URL` and
`NEXT_PUBLIC_COMPANY_ID`.

## Environment variables

| Variable                   | Notes                       |
|----------------------------|-----------------------------|
| NEXT_PUBLIC_API_BASE_URL   | Backend base URL            |
| NEXT_PUBLIC_COMPANY_ID     | Hardcoded tenant UUID       |

## Not built yet

- Real auth (currently fake login -> localStorage flag)
- Multi-user / multi-company
- Media (images, files)
- AI suggestions
- Notes / contact memory persistence
- WebSocket real-time updates (currently 3s polling)
- Quoted message rendering (placeholder only)
- Read receipts
