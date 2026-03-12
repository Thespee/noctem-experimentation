"""
Tests for v0.9.1 web view routes and API endpoints.
Calendar view, Tasks upcoming, Tasks projects, Butler status API.
"""
import pytest
import json
from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Create a test Flask app."""
    from noctem.web.app import create_app
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def client(app):
    """Flask test client."""
    return app.test_client()


# ---------------------------------------------------------------------------
# Helper: mock task/project objects
# ---------------------------------------------------------------------------

def _make_task(**overrides):
    """Create a mock task object."""
    t = MagicMock()
    t.id = overrides.get('id', 'task-1')
    t.name = overrides.get('name', 'Test Task')
    t.importance = overrides.get('importance', 5)
    t.urgency = overrides.get('urgency', 5)
    t.priority_score = overrides.get('priority_score', 50)
    t.due_date = overrides.get('due_date', date.today())
    t.due_time = overrides.get('due_time', None)
    t.status = overrides.get('status', 'active')
    t.tags = overrides.get('tags', [])
    t.project_id = overrides.get('project_id', None)
    t.computer_help_suggestion = overrides.get('computer_help_suggestion', None)
    return t


def _make_project(**overrides):
    """Create a mock project object."""
    p = MagicMock()
    p.id = overrides.get('id', 'proj-1')
    p.name = overrides.get('name', 'Test Project')
    p.status = overrides.get('status', 'active')
    p.next_action_suggestion = overrides.get('next_action_suggestion', None)
    p.goal_id = overrides.get('goal_id', None)
    return p


# ===========================================================================
# Calendar View Tests
# ===========================================================================

class TestCalendarView:
    """Tests for /calendar/view and /api/calendar/week."""

    def test_calendar_view_renders(self, client):
        """GET /calendar/view returns 200."""
        with patch('noctem.web.app.get_saved_urls', return_value=[]):
            resp = client.get('/calendar/view')
            assert resp.status_code == 200
            assert b'Calendar' in resp.data

    def test_calendar_view_shows_sidebar_links(self, client):
        """Template includes navigation links."""
        with patch('noctem.web.app.get_saved_urls', return_value=[]):
            resp = client.get('/calendar/view')
            html = resp.data.decode()
            assert '/tasks/upcoming' in html
            assert '/tasks/projects' in html

    def test_api_calendar_week_returns_json(self, client):
        """GET /api/calendar/week returns JSON with 7 days."""
        from noctem.db import get_db
        resp = client.get('/api/calendar/week')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'days' in data
        assert len(data['days']) == 7

    def test_api_calendar_week_with_date_param(self, client):
        """Accepts date query param."""
        resp = client.get('/api/calendar/week?date=2025-06-02')
        data = resp.get_json()
        assert data['week_start'] == '2025-06-02'
        assert data['week_end'] == '2025-06-08'

    def test_api_calendar_week_invalid_date_fallback(self, client):
        """Invalid date param falls back to today."""
        resp = client.get('/api/calendar/week?date=not-a-date')
        data = resp.get_json()
        assert 'days' in data
        assert len(data['days']) == 7

    def test_api_calendar_week_day_structure(self, client):
        """Each day has date, day_name, is_today, events."""
        resp = client.get('/api/calendar/week')
        data = resp.get_json()
        day = data['days'][0]
        assert 'date' in day
        assert 'day_name' in day
        assert 'is_today' in day
        assert 'events' in day
        assert isinstance(day['events'], list)

    def test_api_calendar_week_monday_start(self, client):
        """Week starts on Monday."""
        resp = client.get('/api/calendar/week?date=2025-06-04')  # Wednesday
        data = resp.get_json()
        assert data['days'][0]['day_name'] == 'Mon'
        assert data['days'][6]['day_name'] == 'Sun'

    def test_api_calendar_week_events_with_data(self, client):
        """Events in the database appear in the response."""
        from noctem.db import get_db
        monday = date.today() - timedelta(days=date.today().weekday())
        start = datetime.combine(monday, datetime.min.time().replace(hour=10))
        end = start + timedelta(hours=1)
        
        with get_db() as conn:
            conn.execute("""
                INSERT INTO time_blocks (title, start_time, end_time, source)
                VALUES (?, ?, ?, ?)
            """, ('Test Event 091', start.isoformat(), end.isoformat(), 'ics'))
        
        resp = client.get(f'/api/calendar/week?date={monday.isoformat()}')
        data = resp.get_json()
        monday_events = data['days'][0]['events']
        assert len(monday_events) >= 1
        assert any(e['title'] == 'Test Event 091' for e in monday_events)
        
        # Cleanup
        with get_db() as conn:
            conn.execute("DELETE FROM time_blocks WHERE title = 'Test Event 091'")


# ===========================================================================
# Tasks Upcoming View Tests
# ===========================================================================

class TestTasksUpcoming:
    """Tests for /tasks/upcoming and /api/tasks/upcoming."""

    def test_upcoming_view_renders(self, client):
        """GET /tasks/upcoming returns 200."""
        resp = client.get('/tasks/upcoming')
        assert resp.status_code == 200
        assert b'Upcoming' in resp.data

    def test_upcoming_view_has_filter_buttons(self, client):
        """Template includes filter sidebar."""
        resp = client.get('/tasks/upcoming')
        html = resp.data.decode()
        assert 'filterTasks' in html
        assert 'High Priority' in html

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_upcoming_returns_json(self, mock_proj_svc, mock_task_svc, client):
        """GET /api/tasks/upcoming returns JSON."""
        mock_task_svc.get_overdue_tasks.return_value = []
        mock_task_svc.get_tasks_due_on.return_value = []
        
        resp = client.get('/api/tasks/upcoming')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'overdue' in data
        assert 'days' in data

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_upcoming_5_days(self, mock_proj_svc, mock_task_svc, client):
        """Returns exactly 5 days."""
        mock_task_svc.get_overdue_tasks.return_value = []
        mock_task_svc.get_tasks_due_on.return_value = []
        
        resp = client.get('/api/tasks/upcoming')
        data = resp.get_json()
        assert len(data['days']) == 5

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_upcoming_today_marked(self, mock_proj_svc, mock_task_svc, client):
        """Today is marked with is_today=True."""
        mock_task_svc.get_overdue_tasks.return_value = []
        mock_task_svc.get_tasks_due_on.return_value = []
        
        resp = client.get('/api/tasks/upcoming')
        data = resp.get_json()
        today_days = [d for d in data['days'] if d['is_today']]
        assert len(today_days) == 1
        assert today_days[0]['date'] == date.today().isoformat()

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_upcoming_task_fields(self, mock_proj_svc, mock_task_svc, client):
        """Task data includes expected fields."""
        task = _make_task(name='Buy groceries', priority_score=75)
        mock_task_svc.get_overdue_tasks.return_value = []
        mock_task_svc.get_tasks_due_on.return_value = [task]
        mock_proj_svc.get_project.return_value = None
        
        resp = client.get('/api/tasks/upcoming')
        data = resp.get_json()
        t = data['days'][0]['tasks'][0]
        assert t['name'] == 'Buy groceries'
        assert t['priority_score'] == 75

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_upcoming_sorted_by_priority(self, mock_proj_svc, mock_task_svc, client):
        """Tasks are sorted by priority_score descending."""
        t1 = _make_task(id='a', name='Low', priority_score=10)
        t2 = _make_task(id='b', name='High', priority_score=90)
        t3 = _make_task(id='c', name='Med', priority_score=50)
        mock_task_svc.get_overdue_tasks.return_value = []
        mock_task_svc.get_tasks_due_on.return_value = [t1, t2, t3]
        mock_proj_svc.get_project.return_value = None
        
        resp = client.get('/api/tasks/upcoming')
        data = resp.get_json()
        scores = [t['priority_score'] for t in data['days'][0]['tasks']]
        assert scores == sorted(scores, reverse=True)

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_upcoming_overdue_tasks(self, mock_proj_svc, mock_task_svc, client):
        """Overdue tasks appear in the overdue array."""
        overdue = _make_task(name='Overdue Item', due_date=date.today() - timedelta(days=3))
        mock_task_svc.get_overdue_tasks.return_value = [overdue]
        mock_task_svc.get_tasks_due_on.return_value = []
        mock_proj_svc.get_project.return_value = None
        
        resp = client.get('/api/tasks/upcoming')
        data = resp.get_json()
        assert len(data['overdue']) == 1
        assert data['overdue'][0]['name'] == 'Overdue Item'

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_upcoming_includes_project_name(self, mock_proj_svc, mock_task_svc, client):
        """Tasks with a project include the project name."""
        task = _make_task(project_id='proj-1')
        proj = _make_project(name='Work')
        mock_task_svc.get_overdue_tasks.return_value = []
        mock_task_svc.get_tasks_due_on.return_value = [task]
        mock_proj_svc.get_project.return_value = proj
        
        resp = client.get('/api/tasks/upcoming')
        data = resp.get_json()
        assert data['days'][0]['tasks'][0]['project_name'] == 'Work'


# ===========================================================================
# Tasks Projects View Tests
# ===========================================================================

class TestTasksProjects:
    """Tests for /tasks/projects and /api/tasks/projects."""

    def test_projects_view_renders(self, client):
        """GET /tasks/projects returns 200."""
        resp = client.get('/tasks/projects')
        assert resp.status_code == 200
        assert b'Project Board' in resp.data

    def test_projects_view_has_side_panel(self, client):
        """Template includes the Notion-style side panel."""
        resp = client.get('/tasks/projects')
        html = resp.data.decode()
        assert 'side-panel' in html
        assert 'openPanel' in html
        assert 'closePanel' in html

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_projects_returns_json(self, mock_proj_svc, mock_task_svc, client):
        """GET /api/tasks/projects returns JSON."""
        mock_proj_svc.get_active_projects.return_value = []
        mock_task_svc.get_inbox_tasks.return_value = []
        
        resp = client.get('/api/tasks/projects')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'columns' in data
        assert 'inbox' in data

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_projects_inbox(self, mock_proj_svc, mock_task_svc, client):
        """Inbox tasks appear in the inbox key."""
        inbox_task = _make_task(name='Unsorted task', project_id=None)
        mock_proj_svc.get_active_projects.return_value = []
        mock_task_svc.get_inbox_tasks.return_value = [inbox_task]
        
        resp = client.get('/api/tasks/projects')
        data = resp.get_json()
        assert data['inbox']['project_name'] == 'Inbox'
        assert len(data['inbox']['tasks']) == 1
        assert data['inbox']['tasks'][0]['name'] == 'Unsorted task'

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_projects_columns(self, mock_proj_svc, mock_task_svc, client):
        """Projects become columns with tasks."""
        proj = _make_project(id='p1', name='Work')
        task = _make_task(name='Do report', project_id='p1', priority_score=80)
        mock_proj_svc.get_active_projects.return_value = [proj]
        mock_task_svc.get_project_tasks.return_value = [task]
        mock_task_svc.get_inbox_tasks.return_value = []
        
        resp = client.get('/api/tasks/projects')
        data = resp.get_json()
        assert len(data['columns']) == 1
        col = data['columns'][0]
        assert col['project_name'] == 'Work'
        assert len(col['tasks']) == 1
        assert col['tasks'][0]['name'] == 'Do report'

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_projects_excludes_done(self, mock_proj_svc, mock_task_svc, client):
        """Done/canceled tasks are excluded from columns."""
        proj = _make_project(id='p1', name='Work')
        active = _make_task(id='a', name='Active', status='active')
        done = _make_task(id='b', name='Done', status='done')
        canceled = _make_task(id='c', name='Canceled', status='canceled')
        mock_proj_svc.get_active_projects.return_value = [proj]
        mock_task_svc.get_project_tasks.return_value = [active, done, canceled]
        mock_task_svc.get_inbox_tasks.return_value = []
        
        resp = client.get('/api/tasks/projects')
        data = resp.get_json()
        tasks = data['columns'][0]['tasks']
        assert len(tasks) == 1
        assert tasks[0]['name'] == 'Active'

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_projects_sorted_by_priority(self, mock_proj_svc, mock_task_svc, client):
        """Tasks within a column are sorted by priority_score desc."""
        proj = _make_project(id='p1', name='Work')
        t1 = _make_task(id='a', priority_score=20, status='active')
        t2 = _make_task(id='b', priority_score=90, status='active')
        t3 = _make_task(id='c', priority_score=50, status='active')
        mock_proj_svc.get_active_projects.return_value = [proj]
        mock_task_svc.get_project_tasks.return_value = [t1, t2, t3]
        mock_task_svc.get_inbox_tasks.return_value = []
        
        resp = client.get('/api/tasks/projects')
        data = resp.get_json()
        scores = [t['priority_score'] for t in data['columns'][0]['tasks']]
        assert scores == sorted(scores, reverse=True)

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_projects_ai_summary(self, mock_proj_svc, mock_task_svc, client):
        """Column includes AI summary from project.next_action_suggestion."""
        proj = _make_project(id='p1', name='Work', next_action_suggestion='Focus on the report')
        mock_proj_svc.get_active_projects.return_value = [proj]
        mock_task_svc.get_project_tasks.return_value = []
        mock_task_svc.get_inbox_tasks.return_value = []
        
        resp = client.get('/api/tasks/projects')
        data = resp.get_json()
        assert data['columns'][0]['ai_summary'] == 'Focus on the report'

    @patch('noctem.web.app.task_service')
    @patch('noctem.web.app.project_service')
    def test_api_projects_done_count(self, mock_proj_svc, mock_task_svc, client):
        """Column includes done_count and total_count."""
        proj = _make_project(id='p1', name='Work')
        active = _make_task(id='a', status='active')
        done = _make_task(id='b', status='done')
        mock_proj_svc.get_active_projects.return_value = [proj]
        mock_task_svc.get_project_tasks.return_value = [active, done]
        mock_task_svc.get_inbox_tasks.return_value = []
        
        resp = client.get('/api/tasks/projects')
        data = resp.get_json()
        col = data['columns'][0]
        assert col['done_count'] == 1
        assert col['total_count'] == 2


# ===========================================================================
# Butler Status API Tests
# ===========================================================================

class TestButlerStatusAPI:
    """Tests for /api/butler/status."""

    @patch('noctem.web.app.get_butler_status')
    def test_butler_status_returns_json(self, mock_butler, client):
        """GET /api/butler/status returns JSON."""
        mock_butler.return_value = {'status': 'idle', 'last_run': None}
        resp = client.get('/api/butler/status')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'butler' in data or 'status' in data or 'feedback' in data

    @patch('noctem.web.app.get_butler_status')
    def test_butler_status_includes_feedback(self, mock_butler, client):
        """Response includes feedback session info."""
        mock_butler.return_value = {'status': 'idle'}
        
        with patch('noctem.butler.feedback.get_session_status', return_value={
            'next_session': '2025-06-20',
            'next_session_id': 'sess-1',
            'total_pending_questions': 5,
            'sessions_completed_this_week': 1,
        }):
            resp = client.get('/api/butler/status')
            data = resp.get_json()
            assert 'feedback' in data
            assert data['feedback']['total_pending_questions'] == 5


# ===========================================================================
# Cross-view Navigation Tests
# ===========================================================================

class TestCrossNavigation:
    """Verify navigation links between views."""

    def test_calendar_links_to_tasks(self, client):
        """Calendar view links to task views."""
        with patch('noctem.web.app.get_saved_urls', return_value=[]):
            html = client.get('/calendar/view').data.decode()
            assert '/tasks/upcoming' in html
            assert '/tasks/projects' in html

    def test_upcoming_links_to_calendar(self, client):
        """Upcoming view links to calendar."""
        html = client.get('/tasks/upcoming').data.decode()
        assert '/calendar/view' in html

    def test_projects_links_to_upcoming(self, client):
        """Projects view links to upcoming."""
        html = client.get('/tasks/projects').data.decode()
        assert '/tasks/upcoming' in html

    def test_all_views_link_to_dashboard(self, client):
        """All new views link back to dashboard."""
        with patch('noctem.web.app.get_saved_urls', return_value=[]):
            for path in ['/calendar/view', '/tasks/upcoming', '/tasks/projects']:
                html = client.get(path).data.decode()
                assert 'href="/"' in html, f"{path} missing dashboard link"
