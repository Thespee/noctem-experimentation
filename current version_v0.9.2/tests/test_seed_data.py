"""
Tests for seed data loading system (v0.6.0).
"""
import pytest
import json
from pathlib import Path


class TestSeedDataValidation:
    """Tests for seed data validation."""
    
    def test_validate_empty_data(self):
        """Empty dict should be valid (nothing to import)."""
        from noctem.seed.loader import validate_seed_data
        
        errors = validate_seed_data({})
        assert errors == []
    
    def test_validate_valid_goals(self):
        """Valid goals should pass validation."""
        from noctem.seed.loader import validate_seed_data
        
        data = {
            "goals": [
                {"name": "Test Goal", "type": "bigger_goal"},
                {"name": "Another Goal"}
            ]
        }
        errors = validate_seed_data(data)
        assert errors == []
    
    def test_validate_missing_goal_name(self):
        """Goals without name should fail."""
        from noctem.seed.loader import validate_seed_data
        
        data = {
            "goals": [
                {"type": "bigger_goal"}  # Missing name
            ]
        }
        errors = validate_seed_data(data)
        assert len(errors) == 1
        assert "missing 'name'" in errors[0]
    
    def test_validate_valid_projects(self):
        """Valid projects should pass validation."""
        from noctem.seed.loader import validate_seed_data
        
        data = {
            "projects": [
                {"name": "Test Project", "goal": "Some Goal"},
                {"name": "Standalone Project"}
            ]
        }
        errors = validate_seed_data(data)
        assert errors == []
    
    def test_validate_valid_tasks(self):
        """Valid tasks should pass validation."""
        from noctem.seed.loader import validate_seed_data
        
        data = {
            "tasks": [
                {"name": "Test Task", "due_date": "2025-12-31"},
                {"name": "Simple Task"}
            ]
        }
        errors = validate_seed_data(data)
        assert errors == []
    
    def test_validate_calendar_urls(self):
        """Valid calendar URLs should pass validation."""
        from noctem.seed.loader import validate_seed_data
        
        data = {
            "calendar_urls": [
                {"url": "https://example.com/cal.ics", "name": "Work"}
            ]
        }
        errors = validate_seed_data(data)
        assert errors == []
    
    def test_validate_missing_url(self):
        """Calendar URLs without url should fail."""
        from noctem.seed.loader import validate_seed_data
        
        data = {
            "calendar_urls": [
                {"name": "Work"}  # Missing url
            ]
        }
        errors = validate_seed_data(data)
        assert len(errors) == 1
        assert "missing 'url'" in errors[0]


class TestSeedDataLoading:
    """Tests for loading seed data into database."""
    
    def test_load_empty_data(self):
        """Loading empty data should work."""
        from noctem.seed.loader import load_seed_data
        
        stats = load_seed_data({})
        assert stats.goals_created == 0
        assert stats.tasks_created == 0
        assert len(stats.errors) == 0
    
    def test_load_single_goal(self):
        """Should create a goal from seed data."""
        from noctem.seed.loader import load_seed_data, ConflictAction
        from noctem.services import goal_service
        
        data = {
            "goals": [{"name": "Seed Test Goal", "type": "bigger_goal"}]
        }
        
        # Use skip resolver to avoid conflicts with existing data
        def skip_resolver(entity_type, name, existing_id):
            return ConflictAction.SKIP
        
        stats = load_seed_data(data, conflict_resolver=skip_resolver)
        
        # Either created or skipped (if already exists)
        assert stats.goals_created + stats.goals_skipped == 1
    
    def test_load_project_with_goal(self):
        """Should link project to goal."""
        from noctem.seed.loader import load_seed_data, ConflictAction
        
        data = {
            "goals": [{"name": "Seed Parent Goal"}],
            "projects": [{"name": "Seed Child Project", "goal": "Seed Parent Goal"}]
        }
        
        def skip_resolver(entity_type, name, existing_id):
            return ConflictAction.SKIP
        
        stats = load_seed_data(data, conflict_resolver=skip_resolver)
        
        # Should have processed both
        assert stats.goals_created + stats.goals_skipped == 1
        assert stats.projects_created + stats.projects_skipped == 1
    
    def test_load_task_with_project(self):
        """Should link task to project."""
        from noctem.seed.loader import load_seed_data, ConflictAction
        
        data = {
            "projects": [{"name": "Seed Task Project"}],
            "tasks": [{"name": "Seed Task", "project": "Seed Task Project"}]
        }
        
        def skip_resolver(entity_type, name, existing_id):
            return ConflictAction.SKIP
        
        stats = load_seed_data(data, conflict_resolver=skip_resolver)
        
        assert stats.projects_created + stats.projects_skipped == 1
        assert stats.tasks_created + stats.tasks_skipped == 1


class TestConflictResolution:
    """Tests for conflict resolution during import."""
    
    def test_conflict_skip(self):
        """Skip action should not modify existing data."""
        from noctem.seed.loader import load_seed_data, ConflictAction
        from noctem.services import goal_service
        
        # Create a goal first
        goal = goal_service.create_goal(name="Conflict Test Goal")
        original_desc = goal.description
        
        # Try to import same name with different description
        data = {
            "goals": [{"name": "Conflict Test Goal", "description": "New description"}]
        }
        
        def skip_resolver(entity_type, name, existing_id):
            return ConflictAction.SKIP
        
        stats = load_seed_data(data, conflict_resolver=skip_resolver)
        
        assert stats.goals_skipped == 1
        assert stats.goals_created == 0
        
        # Check original wasn't modified
        reloaded = goal_service.get_goal(goal.id)
        assert reloaded.description == original_desc
    
    def test_conflict_overwrite(self):
        """Overwrite action should update existing data."""
        from noctem.seed.loader import load_seed_data, ConflictAction
        from noctem.services import goal_service
        
        # Create a goal first
        goal = goal_service.create_goal(name="Overwrite Test Goal", description="Old")
        
        # Import same name with different description
        data = {
            "goals": [{"name": "Overwrite Test Goal", "description": "Updated description"}]
        }
        
        def overwrite_resolver(entity_type, name, existing_id):
            return ConflictAction.OVERWRITE
        
        stats = load_seed_data(data, conflict_resolver=overwrite_resolver)
        
        assert stats.goals_overwritten == 1
        
        # Check it was updated
        reloaded = goal_service.get_goal(goal.id)
        assert reloaded.description == "Updated description"
    
    def test_conflict_rename(self):
        """Rename action should create new entity with modified name."""
        from noctem.seed.loader import load_seed_data, ConflictAction
        from noctem.services import goal_service
        
        # Create a goal first
        original = goal_service.create_goal(name="Rename Test Goal")
        
        # Import same name
        data = {
            "goals": [{"name": "Rename Test Goal", "description": "Imported version"}]
        }
        
        def rename_resolver(entity_type, name, existing_id):
            return ConflictAction.RENAME
        
        stats = load_seed_data(data, conflict_resolver=rename_resolver)
        
        assert stats.goals_created == 1
        
        # Should have created a new one with modified name
        imported = goal_service.get_goal_by_name("Rename Test Goal (imported)")
        assert imported is not None
        assert imported.id != original.id


class TestSeedDataExport:
    """Tests for exporting seed data."""
    
    def test_export_structure(self):
        """Export should return correct structure."""
        from noctem.seed.loader import export_seed_data
        
        data = export_seed_data()
        
        assert "_noctem_seed_version" in data
        assert "_exported_at" in data
        assert "goals" in data
        assert "projects" in data
        assert "tasks" in data
        assert "calendar_urls" in data
    
    def test_export_includes_goals(self):
        """Export should include goals."""
        from noctem.seed.loader import export_seed_data
        from noctem.services import goal_service
        
        # Create a goal
        goal_service.create_goal(name="Export Test Goal")
        
        data = export_seed_data()
        
        assert isinstance(data["goals"], list)
        goal_names = [g["name"] for g in data["goals"]]
        assert "Export Test Goal" in goal_names
    
    def test_export_without_tasks(self):
        """Export without tasks should have empty tasks list."""
        from noctem.seed.loader import export_seed_data
        
        data = export_seed_data(include_tasks=False)
        
        assert data["tasks"] == []


class TestSeedDataImports:
    """Test module imports."""
    
    def test_import_loader(self):
        """Test importing loader module."""
        from noctem.seed import loader
        
        assert hasattr(loader, 'load_seed_data')
        assert hasattr(loader, 'export_seed_data')
        assert hasattr(loader, 'validate_seed_data')
        assert hasattr(loader, 'ConflictAction')
        assert hasattr(loader, 'ImportStats')
    
    def test_import_package(self):
        """Test importing seed package."""
        from noctem import seed
        
        assert hasattr(seed, 'load_seed_data')
        assert hasattr(seed, 'export_seed_data')


class TestExampleFile:
    """Test the example seed file."""
    
    def test_example_file_valid(self):
        """Example seed file should be valid JSON and pass validation."""
        from noctem.seed.loader import validate_seed_data
        
        example_path = Path(__file__).parent.parent / "examples" / "seed_data.json"
        
        if example_path.exists():
            with open(example_path) as f:
                data = json.load(f)
            
            errors = validate_seed_data(data)
            assert errors == [], f"Example file has validation errors: {errors}"


class TestWebEndpoints:
    """Tests for seed data web endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from noctem.web.app import create_app
        app = create_app()
        app.config['TESTING'] = True
        return app.test_client()
    
    def test_export_endpoint(self, client):
        """Test /api/seed/export endpoint."""
        response = client.get('/api/seed/export')
        assert response.status_code == 200
        
        data = response.get_json()
        assert "goals" in data
        assert "projects" in data
        assert "tasks" in data
    
    def test_upload_endpoint_no_data(self, client):
        """Test upload endpoint without data."""
        response = client.post('/api/seed/upload')
        assert response.status_code == 400
    
    def test_upload_endpoint_invalid_json(self, client):
        """Test upload endpoint with invalid JSON."""
        response = client.post(
            '/api/seed/upload',
            data="not json",
            content_type='application/json'
        )
        # Should fail gracefully
        assert response.status_code in (400, 500)
    
    def test_upload_endpoint_valid_data(self, client):
        """Test upload endpoint with valid data."""
        data = {
            "goals": [{"name": "Web Upload Test Goal"}]
        }
        response = client.post(
            '/api/seed/upload',
            json=data
        )
        assert response.status_code == 200
        
        result = response.get_json()
        assert "success" in result
        assert "stats" in result
