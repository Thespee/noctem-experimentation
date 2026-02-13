"""
Flask web dashboard for Noctem.
Read-only view of goals, projects, tasks, and habits.
"""
from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import date, datetime, timedelta

from ..config import Config
from ..services import task_service, project_service, goal_service, habit_service
from ..services.briefing import get_time_blocks_for_date
from ..services.ics_import import (
    import_ics_bytes, import_ics_url, clear_ics_events,
    get_saved_urls, save_url, remove_url, refresh_all_urls, refresh_url
)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, 
                template_folder="templates",
                static_folder="static")
    app.secret_key = 'noctem-dev-key'  # For flash messages
    
    @app.route("/")
    def dashboard():
        """Main dashboard view."""
        today = date.today()
        
        # Today's data
        today_tasks = task_service.get_tasks_due_today()
        overdue_tasks = task_service.get_overdue_tasks()
        priority_tasks = task_service.get_priority_tasks(5)
        time_blocks = get_time_blocks_for_date(today)
        
        # Goals and projects hierarchy
        goals = goal_service.get_all_goals()
        goals_data = []
        for goal in goals:
            projects = project_service.get_all_projects(goal_id=goal.id)
            projects_data = []
            for project in projects:
                tasks = task_service.get_project_tasks(project.id)
                projects_data.append({
                    "project": project,
                    "tasks": tasks,
                    "done_count": len([t for t in tasks if t.status == "done"]),
                    "total_count": len(tasks),
                })
            goals_data.append({
                "goal": goal,
                "projects": projects_data,
            })
        
        # Standalone projects (no goal)
        standalone_projects = project_service.get_all_projects(goal_id=None)
        standalone_data = []
        for project in standalone_projects:
            if project.goal_id is None:
                tasks = task_service.get_project_tasks(project.id)
                standalone_data.append({
                    "project": project,
                    "tasks": tasks,
                    "done_count": len([t for t in tasks if t.status == "done"]),
                    "total_count": len(tasks),
                })
        
        # Inbox (tasks without project)
        inbox_tasks = task_service.get_inbox_tasks()
        
        # Habits with stats
        habits_stats = habit_service.get_all_habits_stats()
        
        # Week view (with calendar events)
        week_data = []
        for i in range(7):
            day = today + timedelta(days=i)
            day_tasks = task_service.get_tasks_due_on(day)
            day_events = get_time_blocks_for_date(day)
            week_data.append({
                "date": day,
                "day_name": day.strftime("%a"),
                "is_today": day == today,
                "tasks": day_tasks,
                "events": day_events,
            })
        
        # 2D graph data (urgency x importance)
        all_active_tasks = task_service.get_all_tasks(include_done=False)
        graph_tasks = []
        for task in all_active_tasks:
            graph_tasks.append({
                "id": task.id,
                "name": task.name[:30] + "..." if len(task.name) > 30 else task.name,
                "urgency": task.urgency,
                "importance": task.importance,
                "priority_score": task.priority_score,
            })
        
        return render_template(
            "dashboard.html",
            today=today,
            today_tasks=today_tasks,
            overdue_tasks=overdue_tasks,
            priority_tasks=priority_tasks,
            time_blocks=time_blocks,
            goals_data=goals_data,
            standalone_projects=standalone_data,
            inbox_tasks=inbox_tasks,
            habits_stats=habits_stats,
            week_data=week_data,
            graph_tasks=graph_tasks,
        )
    
    @app.route("/health")
    def health():
        """Health check endpoint."""
        return {"status": "ok", "time": datetime.now().isoformat()}
    
    @app.route("/calendar", methods=["GET", "POST"])
    def calendar_upload():
        """Calendar ICS upload page."""
        if request.method == "POST":
            # Check for URL to save
            ics_url = request.form.get('ics_url', '').strip()
            url_name = request.form.get('url_name', '').strip()
            
            if ics_url:
                try:
                    stats = save_url(ics_url, url_name if url_name else None)
                    if 'error' in stats.get('status', ''):
                        flash(f"Error fetching URL: {stats.get('message')}", 'error')
                    else:
                        flash(f"Saved & imported: {stats['created']} new, {stats['updated']} updated, {stats['skipped']} skipped", 'success')
                except Exception as e:
                    flash(f"Error importing: {str(e)}", 'error')
                return redirect(url_for('calendar_upload'))
            
            # Check for file upload
            if 'ics_file' not in request.files or request.files['ics_file'].filename == '':
                flash('Please provide a URL or upload a file', 'error')
                return redirect(url_for('calendar_upload'))
            
            file = request.files['ics_file']
            if file and file.filename.endswith('.ics'):
                try:
                    content = file.read()
                    stats = import_ics_bytes(content)
                    flash(f"Imported: {stats['created']} new, {stats['updated']} updated, {stats['skipped']} skipped", 'success')
                except Exception as e:
                    flash(f"Error importing: {str(e)}", 'error')
            else:
                flash('Please upload a .ics file', 'error')
            
            return redirect(url_for('calendar_upload'))
        
        # GET - show upload form
        from ..db import get_db
        with get_db() as conn:
            events = conn.execute("""
                SELECT * FROM time_blocks 
                WHERE start_time >= date('now', '-1 day')
                ORDER BY start_time ASC
                LIMIT 50
            """).fetchall()
        
        saved_urls = get_saved_urls()
        return render_template("calendar.html", events=events, saved_urls=saved_urls)
    
    @app.route("/calendar/refresh", methods=["POST"])
    def calendar_refresh():
        """Refresh a single URL or all saved URLs."""
        url = request.form.get('url', '').strip()
        
        if url:
            # Refresh single URL
            try:
                stats = refresh_url(url)
                if 'error' in stats.get('status', ''):
                    flash(f"Error: {stats.get('message')}", 'error')
                else:
                    flash(f"Refreshed: {stats['created']} new, {stats['updated']} updated", 'success')
            except Exception as e:
                flash(f"Error: {str(e)}", 'error')
        else:
            # Refresh all
            stats = refresh_all_urls()
            if stats['errors']:
                flash(f"Refreshed with errors: {', '.join(stats['errors'])}", 'error')
            else:
                flash(f"Refreshed all: {stats['created']} new, {stats['updated']} updated", 'success')
        
        return redirect(url_for('calendar_upload'))
    
    @app.route("/calendar/remove", methods=["POST"])
    def calendar_remove_url():
        """Remove a saved URL."""
        url = request.form.get('url', '').strip()
        if url:
            remove_url(url)
            flash("URL removed", 'success')
        return redirect(url_for('calendar_upload'))
    
    @app.route("/calendar/clear", methods=["POST"])
    def calendar_clear():
        """Clear all imported calendar events."""
        count = clear_ics_events()
        flash(f"Cleared {count} calendar events", 'success')
        return redirect(url_for('calendar_upload'))
    
    return app


def run_web():
    """Run the web dashboard."""
    app = create_app()
    host = Config.web_host()
    port = Config.web_port()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_web()
