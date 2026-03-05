#!/usr/bin/env python3
"""Import goals, projects, and tasks from CSV files."""
import csv
import re
from datetime import datetime
from pathlib import Path

from noctem.db import init_db, get_db
from noctem.services import goal_service, project_service, task_service

SOURCES_DIR = Path(__file__).parent / "sources"


def parse_date(date_str: str):
    """Parse date from CSV format like 'January 20, 2026'."""
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), "%B %d, %Y").date()
    except ValueError:
        return None


def extract_goal_name(goal_field: str) -> str:
    """Extract goal name from field like 'Goal Name (https://...)'."""
    if not goal_field:
        return None
    # Remove the Notion link
    match = re.match(r'^([^(]+)', goal_field)
    if match:
        return match.group(1).strip()
    return goal_field.strip()


def import_goals():
    """Import goals from CSV."""
    goals_file = list(SOURCES_DIR.glob("Goals*.csv"))[0]
    goals_map = {}  # name -> goal object
    
    with open(goals_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('Name', '').strip()
            goal_type = row.get('When', '').strip().lower()
            
            if not name:
                continue
            
            # Map to our types
            if 'bigger' in goal_type:
                gtype = 'bigger_goal'
            elif 'daily' in goal_type:
                gtype = 'daily_goal'
            else:
                gtype = 'bigger_goal'
            
            goal = goal_service.create_goal(name, goal_type=gtype)
            goals_map[name] = goal
            print(f"  ✓ Goal: {name} ({gtype})")
    
    return goals_map


def import_projects(goals_map):
    """Import projects from CSV."""
    projects_file = list(SOURCES_DIR.glob("Projects*.csv"))[0]
    projects_map = {}  # name -> project object
    
    with open(projects_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('Project name', '').strip()
            if not name:
                continue
            
            status_raw = row.get('Status', '').strip().lower()
            summary = row.get('Current Summary', '').strip()
            goal_field = row.get('🏔️ Goal', '') or row.get('Goal', '')
            
            # Map status
            if 'back burner' in status_raw:
                status = 'backburner'
            elif 'in progress' in status_raw:
                status = 'in_progress'
            elif 'done' in status_raw or 'complete' in status_raw:
                status = 'done'
            else:
                status = 'in_progress'
            
            # Find goal
            goal_id = None
            goal_name = extract_goal_name(goal_field)
            if goal_name and goal_name in goals_map:
                goal_id = goals_map[goal_name].id
            
            project = project_service.create_project(
                name=name,
                goal_id=goal_id,
                status=status,
                summary=summary or None,
            )
            projects_map[name] = project
            print(f"  ✓ Project: {name} ({status})")
    
    return projects_map


def build_task_project_map():
    """Build a map of task names to project names from the _all.csv file."""
    all_files = list(SOURCES_DIR.glob("Tasks*_all.csv"))
    if not all_files:
        return {}
    
    task_project_map = {}
    with open(all_files[0], 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            task_name = row.get('Task name', '').strip()
            project_field = row.get('Project', '')
            if task_name and project_field:
                project_name = extract_goal_name(project_field)  # Reuse the extraction logic
                if project_name:
                    task_project_map[task_name] = project_name
    
    return task_project_map


def import_tasks(projects_map):
    """Import tasks from CSV."""
    # Get the short list CSV (not the _all.csv)
    tasks_files = [f for f in SOURCES_DIR.glob("Tasks*.csv") if '_all' not in f.name]
    if not tasks_files:
        print("  No tasks file found")
        return
    tasks_file = tasks_files[0]
    
    # Build map of task -> project from the _all.csv
    task_project_map = build_task_project_map()
    
    with open(tasks_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('Task name', '').strip()
            if not name or name == 'Task':  # Skip empty/placeholder rows
                continue
            
            status_raw = row.get('Status', '').strip().lower()
            due_str = row.get('Due', '').strip()
            
            # Map status
            if 'done' in status_raw or 'complete' in status_raw:
                status = 'done'
            elif 'in progress' in status_raw:
                status = 'in_progress'
            else:
                status = 'not_started'
            
            # Parse due date
            due_date = parse_date(due_str)
            
            # Find project from the _all.csv mapping
            project_id = None
            project_name = task_project_map.get(name)
            if project_name and project_name in projects_map:
                project_id = projects_map[project_name].id
            
            # Default importance (medium)
            importance = 0.5
            
            task = task_service.create_task(
                name=name,
                project_id=project_id,
                due_date=due_date,
                importance=importance,
            )
            
            # Update status if needed
            if status != 'not_started':
                task_service.update_task(task.id, status=status)
            
            due_info = f" (due {due_date})" if due_date else ""
            proj_info = f" → {project_name}" if project_name else ""
            print(f"  ✓ Task: {name}{due_info}{proj_info}")


def main():
    print("🌙 Importing data into Noctem...\n")
    
    # Initialize database
    init_db()
    
    print("📎 Importing Goals...")
    goals_map = import_goals()
    print(f"   Imported {len(goals_map)} goals\n")
    
    print("📁 Importing Projects...")
    projects_map = import_projects(goals_map)
    print(f"   Imported {len(projects_map)} projects\n")
    
    print("📋 Importing Tasks...")
    import_tasks(projects_map)
    print()
    
    print("✅ Import complete!")


if __name__ == "__main__":
    main()
