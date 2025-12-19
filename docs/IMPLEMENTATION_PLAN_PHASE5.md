# Implementation Plan: Phase 5 - User Experience & Integrations

> Created: 2025-12-17
> Updated: 2025-12-17
> Status: **Sprint 1 Complete** - Authentication Implemented
> Priority: High

## Overview

This plan addresses the gaps identified in the current implementation and adds new features to make the Job Hunter application fully functional for end users.

---

## Sprint 1 Status: COMPLETE

### What's Implemented
- Email/password authentication (register, login, logout)
- JWT token system (access + refresh tokens)
- OAuth provider infrastructure (Google, LinkedIn, GitHub)
- NextAuth.js integration in frontend
- Login and registration pages
- User menu in navbar with avatar and dropdown
- Protected route support via SessionProvider

### OAuth Configuration Required

To enable OAuth login buttons, you need to obtain API credentials from each provider:

#### Google OAuth
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Navigate to "APIs & Services" > "Credentials"
4. Click "Create Credentials" > "OAuth client ID"
5. Select "Web application"
6. Add authorized redirect URI: `http://localhost:3000/api/auth/callback/google`
7. Copy Client ID and Client Secret

#### LinkedIn OAuth
1. Go to [LinkedIn Developer Portal](https://www.linkedin.com/developers/)
2. Create a new app
3. Under "Auth" tab, add redirect URL: `http://localhost:3000/api/auth/callback/linkedin`
4. Request "Sign In with LinkedIn" product
5. Copy Client ID and Client Secret

#### GitHub OAuth
1. Go to [GitHub Developer Settings](https://github.com/settings/developers)
2. Click "New OAuth App"
3. Set Authorization callback URL: `http://localhost:3000/api/auth/callback/github`
4. Copy Client ID and generate Client Secret

#### Configuration Files

**Frontend (.env.local):**
```env
# Required for NextAuth.js
AUTH_SECRET=generate-with-openssl-rand-base64-32

# OAuth Providers (optional - email/password works without these)
AUTH_GOOGLE_ID=your-google-client-id
AUTH_GOOGLE_SECRET=your-google-client-secret
AUTH_LINKEDIN_ID=your-linkedin-client-id
AUTH_LINKEDIN_SECRET=your-linkedin-client-secret
AUTH_GITHUB_ID=your-github-client-id
AUTH_GITHUB_SECRET=your-github-client-secret
```

**Backend (.env):**
```env
# JWT Configuration
JWT_SECRET_KEY=generate-with-openssl-rand-hex-32

# OAuth (for backend token exchange - optional)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
LINKEDIN_CLIENT_ID=your-linkedin-client-id
LINKEDIN_CLIENT_SECRET=your-linkedin-client-secret
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
```

> **Note:** Email/password authentication works without OAuth configuration. OAuth buttons will be non-functional until credentials are provided.

---

## Phase 5.1 - Authentication & User Management (P0)

### Objective
Implement secure authentication with multiple OAuth providers and email/password login.

### Features

#### 5.1.1 OAuth Authentication
| Provider | Priority | Notes |
|----------|----------|-------|
| Google | P0 | Most common, reuse existing Google API setup |
| LinkedIn | P0 | Professional context, job-related |
| GitHub | P1 | Developer audience |
| Email/Password | P0 | Fallback option |

#### 5.1.2 Backend Implementation

**New Dependencies:**
```toml
# pyproject.toml additions
python-jose = "^3.3.0"      # JWT tokens
passlib = "^1.7.4"          # Password hashing
bcrypt = "^4.1.2"           # Bcrypt backend
httpx = "^0.27.0"           # OAuth HTTP client
```

**New Files:**
```
src/
├── auth/
│   ├── __init__.py
│   ├── jwt.py              # JWT token generation/validation
│   ├── oauth.py            # OAuth provider handlers
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── google.py       # Google OAuth
│   │   ├── linkedin.py     # LinkedIn OAuth
│   │   └── github.py       # GitHub OAuth
│   └── dependencies.py     # Auth dependencies (get_current_user)
├── api/routes/
│   └── auth.py             # Auth endpoints
```

**API Endpoints:**
```
POST   /api/auth/register           # Email/password registration
POST   /api/auth/login              # Email/password login
POST   /api/auth/logout             # Logout (invalidate token)
GET    /api/auth/me                 # Get current user
POST   /api/auth/refresh            # Refresh access token

GET    /api/auth/google             # Initiate Google OAuth
GET    /api/auth/google/callback    # Google OAuth callback
GET    /api/auth/linkedin           # Initiate LinkedIn OAuth
GET    /api/auth/linkedin/callback  # LinkedIn OAuth callback
GET    /api/auth/github             # Initiate GitHub OAuth
GET    /api/auth/github/callback    # GitHub OAuth callback
```

**Database Changes:**
```sql
-- Add to users table
ALTER TABLE users ADD COLUMN password_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN auth_provider VARCHAR(50) DEFAULT 'email';
ALTER TABLE users ADD COLUMN provider_user_id VARCHAR(255);
ALTER TABLE users ADD COLUMN email_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN avatar_url VARCHAR(500);

-- New table for refresh tokens
CREATE TABLE refresh_tokens (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    revoked BOOLEAN DEFAULT FALSE
);
```

#### 5.1.3 Frontend Implementation

**New Dependencies:**
```json
{
  "next-auth": "^4.24.0"
}
```

**New Files:**
```
app/
├── login/
│   └── page.tsx            # Login page with OAuth buttons
├── register/
│   └── page.tsx            # Registration page
├── api/auth/
│   └── [...nextauth]/
│       └── route.ts        # NextAuth.js API route
lib/
├── auth.ts                 # Auth utilities
└── auth-context.tsx        # Auth context provider
components/
├── auth/
│   ├── login-form.tsx      # Email/password form
│   ├── register-form.tsx   # Registration form
│   ├── oauth-buttons.tsx   # OAuth provider buttons
│   └── user-menu.tsx       # User dropdown menu
```

**UI Components:**
- Login page with email/password form
- OAuth buttons (Google, LinkedIn, GitHub)
- Registration form with validation
- User menu in navbar (avatar, dropdown with logout)
- Protected route wrapper

### Acceptance Criteria
- [ ] User can register with email/password
- [ ] User can login with email/password
- [ ] User can login with Google OAuth
- [ ] User can login with LinkedIn OAuth
- [ ] User can login with GitHub OAuth
- [ ] JWT tokens are used for API authentication
- [ ] Refresh tokens work correctly
- [ ] Protected routes redirect to login
- [ ] User menu shows in navbar after login

---

## Phase 5.2 - Core Dashboard Features (P0-P1)

### Objective
Make the dashboard fully functional with job management capabilities.

### Features

#### 5.2.1 Manual Job Creation

**Backend:**
- Already exists: `POST /api/jobs/` endpoint
- Add: Job URL scraping to extract details automatically

**Frontend - New Files:**
```
components/
├── jobs/
│   ├── add-job-dialog.tsx      # Modal for adding jobs
│   ├── job-form.tsx            # Job creation form
│   └── url-import.tsx          # Paste URL to import job
```

**UI Flow:**
1. "Add Job" button in dashboard header
2. Dialog with two tabs:
   - **Import from URL**: Paste job posting URL, auto-extract details
   - **Manual Entry**: Form with title, company, description, URL

#### 5.2.2 Job Detail View

**Frontend - New Files:**
```
app/
├── jobs/
│   └── [id]/
│       └── page.tsx            # Job detail page
components/
├── jobs/
│   ├── job-card.tsx            # Clickable job card in Kanban
│   ├── job-detail.tsx          # Full job details component
│   ├── job-actions.tsx         # Action buttons (apply, archive, etc.)
│   └── match-score-badge.tsx   # Visual match score indicator
```

**Job Detail Page Contents:**
- Job title, company, location
- Full description (rendered markdown)
- Match score with breakdown
- Skills matched / missing
- Application history
- Action buttons: Apply, Move to stage, Archive, Delete
- Adapted CV preview (if exists)
- Cover letter preview (if exists)

#### 5.2.3 Drag-and-Drop Job Status

**Frontend Changes:**
```
# New dependency
npm install @dnd-kit/core @dnd-kit/sortable
```

**Implementation:**
- Wrap Kanban columns with DndContext
- Make job cards draggable
- Update job status via API on drop
- Optimistic UI updates
- Visual feedback during drag

#### 5.2.4 Search and Filters

**Backend - New Endpoint:**
```
GET /api/jobs/search?q=...&status=...&company=...&min_score=...
```

**Frontend - New Files:**
```
components/
├── search/
│   ├── search-bar.tsx          # Global search input
│   ├── filter-panel.tsx        # Filter sidebar/dropdown
│   └── search-results.tsx      # Search results display
```

**Filter Options:**
- Status (multi-select)
- Company (autocomplete)
- Match score range
- Date added range
- Location
- Job type (remote, hybrid, onsite)

### Acceptance Criteria
- [ ] User can add job manually via form
- [ ] User can import job by pasting URL
- [ ] User can click job card to see details
- [ ] User can drag jobs between columns
- [ ] User can search jobs by keyword
- [ ] User can filter jobs by status, company, score

---

## Phase 5.3 - Profile & Settings (P1)

### Objective
Complete the profile functionality and add user settings.

### Features

#### 5.3.1 CV Upload & Management

**Backend - New Endpoints:**
```
POST   /api/users/{id}/cv              # Upload CV (PDF, DOCX, TXT)
GET    /api/users/{id}/cv              # Get current CV
DELETE /api/users/{id}/cv              # Delete CV
GET    /api/users/{id}/cv/parsed       # Get parsed CV content
```

**Backend - New Files:**
```
src/
├── services/
│   ├── cv_parser.py            # Parse PDF/DOCX to text
│   └── file_storage.py         # File storage (local/S3)
```

**Frontend - New Files:**
```
components/
├── profile/
│   ├── cv-upload.tsx           # Drag-drop CV upload
│   ├── cv-preview.tsx          # Show uploaded CV
│   └── cv-editor.tsx           # Edit parsed CV text
```

#### 5.3.2 Email Connection Management

**Frontend - New Files:**
```
components/
├── profile/
│   ├── email-connections.tsx   # List connected emails
│   ├── connect-gmail.tsx       # Gmail OAuth connect button
│   └── email-sync-status.tsx   # Last sync time, sync button
```

**UI Flow:**
1. "Connected Accounts" section in Profile
2. "Connect Gmail" button initiates OAuth
3. Show connected email with last sync time
4. "Sync Now" button to fetch new job emails
5. "Disconnect" option

#### 5.3.3 Settings Page

**Frontend - New Files:**
```
app/
├── settings/
│   └── page.tsx                # Settings page
components/
├── settings/
│   ├── notification-settings.tsx
│   ├── automation-settings.tsx
│   └── danger-zone.tsx         # Delete account
```

**Settings Options:**
- Email notifications (new jobs, blocked applications)
- Auto-apply preferences (disabled by default)
- Default language for CV/cover letter
- Delete account

### Acceptance Criteria
- [ ] User can upload CV (PDF, DOCX)
- [ ] System parses and displays CV content
- [ ] User can edit parsed CV
- [ ] User can connect Gmail from UI
- [ ] User can see sync status and trigger sync
- [ ] User can configure notification preferences
- [ ] User can delete their account

---

## Phase 5.4 - Application Flow (P1)

### Objective
Enable users to apply to jobs and track application status from the dashboard.

### Features

#### 5.4.1 Apply Flow

**Frontend - New Files:**
```
components/
├── applications/
│   ├── apply-dialog.tsx        # Apply confirmation modal
│   ├── apply-progress.tsx      # Real-time application progress
│   ├── blocker-handler.tsx     # Handle CAPTCHA/login blockers
│   └── application-history.tsx # List of applications for a job
```

**Apply Flow:**
1. Click "Apply" on job card/detail
2. Show confirmation with:
   - Adapted CV preview
   - Cover letter preview
   - Application mode selection (assisted/auto)
3. Start application process
4. Show real-time progress (form filling, questions)
5. Handle blockers (pause, notify user)
6. Show result (success/failed/blocked)

#### 5.4.2 Application Status Dashboard

**Frontend - New Files:**
```
app/
├── applications/
│   └── page.tsx                # Applications list page
components/
├── applications/
│   ├── application-card.tsx    # Application summary card
│   ├── application-detail.tsx  # Full application details
│   └── application-filters.tsx # Filter by status
```

**Application Card Shows:**
- Job title & company
- Application status (pending, in_progress, completed, failed, blocked)
- Timestamp
- Error message (if failed)
- "Resume" button (if blocked)

### Acceptance Criteria
- [ ] User can initiate application from job detail
- [ ] User sees real-time progress during application
- [ ] User is notified of blockers (CAPTCHA, login)
- [ ] User can resume blocked applications
- [ ] User can view all applications in dedicated page
- [ ] User can filter applications by status

---

## Phase 5.5 - Notifications & Alerts (P2)

### Objective
Keep users informed about important events.

### Features

#### 5.5.1 In-App Notifications

**Backend - New Endpoints:**
```
GET    /api/notifications              # List notifications
PATCH  /api/notifications/{id}/read    # Mark as read
DELETE /api/notifications/{id}         # Delete notification
```

**Database:**
```sql
CREATE TABLE notifications (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    type VARCHAR(50) NOT NULL,        -- 'new_jobs', 'blocked', 'applied', etc.
    title VARCHAR(255) NOT NULL,
    message TEXT,
    data JSONB,                        -- Related entity IDs
    read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

**Frontend - New Files:**
```
components/
├── notifications/
│   ├── notification-bell.tsx   # Bell icon with badge in navbar
│   ├── notification-panel.tsx  # Dropdown panel with notifications
│   └── notification-item.tsx   # Individual notification row
```

#### 5.5.2 Toast Notifications

**Implementation:**
- Use `sonner` or `react-hot-toast` for toasts
- Show toasts for:
  - Job added successfully
  - Application started/completed/failed
  - Profile saved
  - Errors

### Acceptance Criteria
- [ ] Notification bell shows unread count
- [ ] User can view and dismiss notifications
- [ ] Toast notifications appear for actions
- [ ] Notifications are persisted in database

---

## Phase 5.6 - AI-Powered Search (P2)

### Objective
Help users find relevant jobs across all connected sources using AI.

### Features

#### 5.6.1 Smart Search

**Backend - New Endpoints:**
```
POST /api/search/smart
{
  "query": "remote senior python developer with ML experience",
  "sources": ["inbox", "linkedin", "infojobs"],  # Optional filter
  "limit": 20
}
```

**Backend Implementation:**
```
src/
├── agents/
│   └── search_agent.py         # AI-powered search agent
├── services/
│   └── search_service.py       # Search orchestration
```

**Search Agent Capabilities:**
- Parse natural language queries
- Extract: role, skills, location, experience level, remote preference
- Score jobs against query
- Rank results by relevance
- Suggest related searches

**Frontend - New Files:**
```
components/
├── search/
│   ├── smart-search.tsx        # AI search input with suggestions
│   ├── search-suggestions.tsx  # Autocomplete suggestions
│   └── relevance-score.tsx     # Show why job matches query
```

### Acceptance Criteria
- [ ] User can search with natural language
- [ ] Results are ranked by AI relevance
- [ ] User sees why each job matched
- [ ] Search works across all job sources

---

## Phase 5.7 - Job Connectors (P3 - Optional)

### Objective
Allow users to import jobs from multiple sources beyond Gmail.

### Features

#### 5.7.1 Connector Architecture

**Backend Structure:**
```
src/
├── connectors/
│   ├── __init__.py
│   ├── base.py                 # BaseConnector abstract class
│   ├── gmail.py                # Gmail connector (existing)
│   ├── linkedin.py             # LinkedIn connector
│   ├── infojobs.py             # InfoJobs connector
│   ├── notion.py               # Notion connector
│   ├── csv_import.py           # CSV/Excel import
│   └── json_import.py          # JSON import
```

**BaseConnector Interface:**
```python
class BaseConnector(ABC):
    @abstractmethod
    async def authenticate(self, user_id: UUID, credentials: dict) -> bool:
        """Authenticate with the service."""
        pass

    @abstractmethod
    async def fetch_jobs(self, user_id: UUID, since: datetime = None) -> list[Job]:
        """Fetch jobs from the service."""
        pass

    @abstractmethod
    async def get_status(self, user_id: UUID) -> ConnectorStatus:
        """Get connection status."""
        pass
```

#### 5.7.2 LinkedIn Connector

**Features:**
- OAuth authentication
- Fetch saved jobs
- Fetch job alerts
- Import applied jobs

**Limitations:**
- LinkedIn API access is restricted
- May require scraping (against ToS)
- Consider as "experimental"

#### 5.7.3 InfoJobs Connector

**Features:**
- OAuth or API key authentication
- Fetch job alerts
- Search jobs by criteria
- Import applications

#### 5.7.4 Notion Connector

**Features:**
- OAuth authentication
- Connect to Notion database
- Map Notion properties to job fields
- Two-way sync (optional)

**Use Case:**
- User maintains job list in Notion
- Sync to Job Hunter for automation

#### 5.7.5 File Import

**Supported Formats:**
- CSV with headers
- Excel (.xlsx)
- JSON array

**Frontend - New Files:**
```
components/
├── connectors/
│   ├── connector-list.tsx      # List available connectors
│   ├── connector-card.tsx      # Individual connector status
│   ├── linkedin-connect.tsx    # LinkedIn OAuth flow
│   ├── infojobs-connect.tsx    # InfoJobs connection
│   ├── notion-connect.tsx      # Notion OAuth flow
│   └── file-import.tsx         # File upload with mapping
```

#### 5.7.6 Connector Management Page

**Frontend - New Files:**
```
app/
├── connectors/
│   └── page.tsx                # Manage all connectors
```

**Page Contents:**
- List of available connectors
- Connection status for each
- Connect/disconnect buttons
- Last sync time
- Sync now button
- Import history

### Acceptance Criteria
- [ ] User can connect LinkedIn account
- [ ] User can connect InfoJobs account
- [ ] User can connect Notion database
- [ ] User can import jobs from CSV/Excel/JSON
- [ ] User can see all connectors in one page
- [ ] User can trigger sync for any connector

---

## Implementation Timeline

### Sprint 1 (Phase 5.1) - Authentication ✅ COMPLETE
- [x] Backend auth infrastructure
- [x] Google OAuth (infrastructure ready, needs API keys)
- [x] LinkedIn OAuth (infrastructure ready, needs API keys)
- [x] GitHub OAuth (infrastructure ready, needs API keys)
- [x] Email/password auth
- [x] Frontend login/register pages
- [x] Protected routes

### Sprint 2 (Phase 5.2) - Core Dashboard
- [ ] Manual job creation
- [ ] Job URL import
- [ ] Job detail page
- [ ] Drag-and-drop
- [ ] Search and filters

### Sprint 3 (Phase 5.3) - Profile
- [ ] CV upload
- [ ] CV parsing
- [ ] Gmail connection UI
- [ ] Settings page

### Sprint 4 (Phase 5.4) - Applications
- [ ] Apply flow UI
- [ ] Application progress tracking
- [ ] Blocker handling UI
- [ ] Applications page

### Sprint 5 (Phase 5.5-5.6) - Polish
- [ ] Notifications system
- [ ] Toast notifications
- [ ] AI-powered search

### Sprint 6+ (Phase 5.7) - Connectors (Optional)
- [ ] Connector architecture
- [ ] LinkedIn connector
- [ ] InfoJobs connector
- [ ] Notion connector
- [ ] File import

---

## Technical Considerations

### Security
- Store OAuth tokens encrypted
- Use HTTP-only cookies for refresh tokens
- Implement rate limiting on auth endpoints
- Add CSRF protection
- Validate all file uploads

### Performance
- Implement job search indexing (consider Meilisearch)
- Cache user sessions in Redis
- Lazy load job descriptions
- Virtualize long job lists

### Scalability
- Design connectors for async processing
- Use background jobs for sync operations
- Implement webhook support for real-time updates

### Testing
- Add E2E tests for auth flows
- Unit tests for each connector
- Integration tests for OAuth callbacks

---

## Environment Variables (New)

```env
# Authentication
JWT_SECRET_KEY=your-secret-key
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# OAuth - Google (existing, extend)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:3000/api/auth/google/callback

# OAuth - LinkedIn
LINKEDIN_CLIENT_ID=...
LINKEDIN_CLIENT_SECRET=...
LINKEDIN_REDIRECT_URI=http://localhost:3000/api/auth/linkedin/callback

# OAuth - GitHub
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GITHUB_REDIRECT_URI=http://localhost:3000/api/auth/github/callback

# Connectors (Phase 5.7)
INFOJOBS_API_KEY=...
NOTION_CLIENT_ID=...
NOTION_CLIENT_SECRET=...

# File Storage
FILE_STORAGE_TYPE=local  # or 's3'
S3_BUCKET_NAME=...
S3_REGION=...
```

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| User registration rate | >50% of visitors | Analytics |
| Jobs added per user | >10 in first week | Database |
| Application success rate | >60% | Application status |
| Daily active users | Growing week-over-week | Analytics |
| Feature adoption | >30% use each feature | Feature flags |

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| LinkedIn blocks OAuth | High | Focus on other connectors, use email import |
| CV parsing fails | Medium | Fallback to manual entry, improve parser |
| OAuth token expiry | Medium | Implement proper refresh flow |
| Rate limiting by providers | Medium | Implement backoff, cache results |
| File upload security | High | Validate file types, scan for malware |

---

## Next Steps

1. **Immediate**: Start Phase 5.1 (Authentication)
2. **Review**: Get feedback on this plan
3. **Prioritize**: Adjust based on user feedback
4. **Iterate**: Ship incrementally, gather feedback

