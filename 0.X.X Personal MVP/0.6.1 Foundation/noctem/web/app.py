"""
Flask web dashboard for Noctem.
Read-only view of goals, projects, and tasks.
"""
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from datetime import date, datetime, timedelta
import io
import sys

from ..config import Config
from ..services import task_service, project_service, goal_service
from ..services.briefing import get_time_blocks_for_date
from ..slow.loop import get_slow_mode_status
from ..butler.protocol import get_butler_status
from ..slow.ollama import OllamaClient
from ..services.ics_import import (
    import_ics_bytes, import_ics_url, clear_ics_events,
    get_saved_urls, save_url, remove_url, refresh_all_urls, refresh_url
)
from ..voice.journals import (
    save_voice_journal, get_all_journals, get_transcription_stats,
    get_journal, update_transcription
)
from ..seed.loader import (
    load_seed_data, export_seed_data, validate_seed_data, ConflictAction
)
from ..seed.text_parser import parse_natural_seed_text, is_natural_seed_format

# Common timezones for settings dropdown
COMMON_TIMEZONES = [
    "America/Vancouver", "America/Los_Angeles", "America/Denver", 
    "America/Chicago", "America/New_York", "America/Toronto",
    "America/Sao_Paulo", "Europe/London", "Europe/Paris", 
    "Europe/Berlin", "Europe/Moscow", "Asia/Dubai",
    "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo",
    "Asia/Shanghai", "Australia/Sydney", "Pacific/Auckland",
    "UTC"
]


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
        
        # v0.6.0: System status
        butler_status = get_butler_status()
        slow_status = get_slow_mode_status()
        
        # v0.6.0: LLM health
        try:
            client = OllamaClient()
            ollama_healthy, ollama_msg = client.health_check()
        except Exception:
            ollama_healthy, ollama_msg = False, "Not configured"
        
        # v0.6.0: AI suggestions
        tasks_with_suggestions = task_service.get_tasks_with_suggestions(limit=5)
        projects_with_suggestions = project_service.get_projects_with_suggestions(limit=3)
        
        # v0.6.0 Final: Forecast data
        from ..services.forecast_service import get_14_day_forecast, get_7_day_table_data
        forecast_14 = get_14_day_forecast()
        week_table = get_7_day_table_data()
        
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
            week_data=week_data,
            graph_tasks=graph_tasks,
            # v0.6.0 data
            butler_status=butler_status,
            slow_status=slow_status,
            ollama_healthy=ollama_healthy,
            ollama_msg=ollama_msg,
            tasks_with_suggestions=tasks_with_suggestions,
            projects_with_suggestions=projects_with_suggestions,
            # v0.6.0 Final data
            forecast_14=forecast_14,
            week_table=week_table,
        )
    
    @app.route("/health")
    def health():
        """Health check endpoint."""
        return {"status": "ok", "time": datetime.now().isoformat()}
    
    @app.route("/prompts")
    def prompts():
        """Prompt editor page - view and edit LLM prompts."""
        return render_template("prompts.html")
    
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
    
    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        """Settings page for configuring Noctem."""
        if request.method == "POST":
            # Save all config values
            fields = [
                'telegram_bot_token', 'telegram_chat_id', 'timezone',
                'morning_message_time', 'web_host', 'web_port'
            ]
            for field in fields:
                value = request.form.get(field, '').strip()
                if field == 'web_port':
                    try:
                        value = int(value) if value else 5000
                    except ValueError:
                        value = 5000
                if value or field in ['telegram_bot_token', 'telegram_chat_id']:
                    Config.set(field, value)
            
            Config.clear_cache()
            flash('Settings saved successfully!', 'success')
            return redirect(url_for('settings'))
        
        # GET - show settings form
        config = Config.get_all()
        return render_template(
            "settings.html",
            config=config,
            timezones=COMMON_TIMEZONES,
        )
    
    @app.route("/settings/test", methods=["POST"])
    def settings_test():
        """Send a test message to Telegram."""
        import requests as http_requests
        
        token = Config.telegram_token()
        chat_id = Config.telegram_chat_id()
        
        if not token:
            flash('Telegram bot token not set!', 'error')
            return redirect(url_for('settings'))
        
        if not chat_id:
            flash('Telegram chat ID not set! Send /start to your bot first.', 'error')
            return redirect(url_for('settings'))
        
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            response = http_requests.post(url, json={
                'chat_id': chat_id,
                'text': '✅ Noctem test message - connection working!',
            }, timeout=10)
            
            if response.ok:
                flash('Test message sent successfully! Check Telegram.', 'success')
            else:
                error = response.json().get('description', 'Unknown error')
                flash(f'Telegram API error: {error}', 'error')
        except Exception as e:
            flash(f'Connection error: {str(e)}', 'error')
        
        return redirect(url_for('settings'))
    
    # =========================================================================
    # v0.6.0: Chat API for web interface
    # =========================================================================
    
    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        """
        Chat endpoint - same fast mode as Telegram/CLI.
        
        Accepts JSON: {"message": "buy groceries tomorrow"}
        Returns JSON: {"response": "✓ Created task...", "success": true}
        """
        from ..cli import handle_input
        from ..services.message_logger import MessageLog
        
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({"error": "No message provided", "success": False}), 400
        
        message = data['message'].strip()
        if not message:
            return jsonify({"error": "Empty message", "success": False}), 400
        
        # Capture stdout to get the response
        old_stdout = sys.stdout
        sys.stdout = captured = io.StringIO()
        
        try:
            with MessageLog(message, source="web") as log:
                result = handle_input(message, log)
            
            response = captured.getvalue().strip()
            
            # If no output captured, provide a default
            if not response:
                response = "✓ Done"
            
            return jsonify({
                "response": response,
                "success": True,
                "timestamp": datetime.now().isoformat(),
            })
            
        except Exception as e:
            return jsonify({
                "error": str(e),
                "success": False,
            }), 500
        finally:
            sys.stdout = old_stdout
    
    @app.route("/api/chat/history")
    def api_chat_history():
        """Get recent chat history from message_log."""
        from ..services.message_logger import get_recent_logs
        
        limit = request.args.get('limit', 10, type=int)
        logs = get_recent_logs(limit)
        
        # Format for chat display
        history = []
        for log in reversed(logs):  # Oldest first
            history.append({
                "message": log.get("raw_message", ""),
                "response": log.get("result", "done"),
                "action": log.get("action_taken", ""),
                "timestamp": log.get("created_at", ""),
                "source": log.get("source", "unknown"),
            })
        
        return jsonify({"history": history})
    
    # =========================================================================
    # v0.6.0: Voice Journals API
    # =========================================================================
    
    @app.route("/voice")
    def voice_journals():
        """Voice journals page - view and upload voice memos."""
        journals = get_all_journals(limit=50)
        stats = get_transcription_stats()
        return render_template("voice.html", journals=journals, stats=stats)
    
    @app.route("/api/voice/upload", methods=["POST"])
    def api_voice_upload():
        """
        Upload an audio file for transcription.
        
        Accepts: multipart/form-data with 'audio' file
        Returns JSON: {"journal_id": 1, "success": true}
        """
        if 'audio' not in request.files:
            return jsonify({"error": "No audio file provided", "success": False}), 400
        
        file = request.files['audio']
        if not file or file.filename == '':
            return jsonify({"error": "No file selected", "success": False}), 400
        
        # Check file extension
        allowed = {'.mp3', '.wav', '.ogg', '.m4a', '.webm', '.flac'}
        ext = '.' + file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if ext not in allowed:
            return jsonify({
                "error": f"Unsupported format. Allowed: {', '.join(allowed)}",
                "success": False
            }), 400
        
        try:
            audio_data = file.read()
            journal_id = save_voice_journal(
                audio_data=audio_data,
                source="web",
                original_filename=file.filename,
            )
            
            return jsonify({
                "journal_id": journal_id,
                "success": True,
                "message": "Voice memo uploaded. Will be transcribed in the background.",
            })
            
        except Exception as e:
            return jsonify({"error": str(e), "success": False}), 500
    
    @app.route("/api/voice/list")
    def api_voice_list():
        """Get list of voice journals."""
        limit = request.args.get('limit', 20, type=int)
        journals = get_all_journals(limit=limit)
        stats = get_transcription_stats()
        
        return jsonify({
            "journals": journals,
            "stats": stats,
        })
    
    @app.route("/api/voice/<int:journal_id>/download")
    def api_voice_download(journal_id):
        """
        Download the audio file for a voice journal.
        
        Returns: Audio file with appropriate content-type
        """
        from flask import send_file
        from pathlib import Path
        
        journal = get_journal(journal_id)
        if not journal:
            return jsonify({"error": "Journal not found"}), 404
        
        audio_path = Path(journal['audio_path'])
        if not audio_path.exists():
            return jsonify({"error": "Audio file not found"}), 404
        
        # Determine mime type from extension
        ext = audio_path.suffix.lower()
        mime_types = {
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.ogg': 'audio/ogg',
            '.m4a': 'audio/mp4',
            '.webm': 'audio/webm',
            '.flac': 'audio/flac',
        }
        mime_type = mime_types.get(ext, 'audio/mpeg')
        
        # Use original filename if available
        download_name = journal.get('original_filename') or audio_path.name
        
        return send_file(
            audio_path,
            mimetype=mime_type,
            as_attachment=True,
            download_name=download_name,
        )
    
    @app.route("/api/voice/<int:journal_id>/transcription", methods=["PUT"])
    def api_voice_edit_transcription(journal_id):
        """
        Edit the transcription for a voice journal.
        
        Accepts JSON: {"transcription": "edited text"}
        Returns JSON: {"success": true}
        """
        journal = get_journal(journal_id)
        if not journal:
            return jsonify({"error": "Journal not found", "success": False}), 404
        
        data = request.get_json()
        if not data or 'transcription' not in data:
            return jsonify({"error": "No transcription provided", "success": False}), 400
        
        new_text = data['transcription'].strip()
        
        try:
            update_transcription(journal_id, new_text)
            return jsonify({
                "success": True,
                "message": "Transcription updated",
            })
        except Exception as e:
            return jsonify({"error": str(e), "success": False}), 500
    
    # =========================================================================
    # v0.6.0: Seed Data API
    # =========================================================================
    
    @app.route("/api/seed/upload", methods=["POST"])
    def api_seed_upload():
        """
        Upload seed data JSON file.
        Uses 'overwrite_all' mode for web (no interactive prompts).
        
        Accepts: multipart/form-data with 'file' or JSON body
        Returns JSON: {"stats": {...}, "success": true}
        """
        import json
        
        # Get the data
        if request.is_json:
            data = request.get_json()
        elif 'file' in request.files:
            file = request.files['file']
            if not file or file.filename == '':
                return jsonify({"error": "No file selected", "success": False}), 400
            try:
                content = file.read().decode('utf-8')
                data = json.loads(content)
            except Exception as e:
                return jsonify({"error": f"Invalid JSON: {e}", "success": False}), 400
        else:
            return jsonify({"error": "No data provided", "success": False}), 400
        
        # Validate
        errors = validate_seed_data(data)
        if errors:
            return jsonify({"error": "Validation failed", "errors": errors, "success": False}), 400
        
        # Get conflict mode from request
        mode = request.args.get('mode', 'skip')  # skip, overwrite
        
        def web_resolver(entity_type: str, name: str, existing_id: int) -> ConflictAction:
            return ConflictAction.OVERWRITE if mode == 'overwrite' else ConflictAction.SKIP
        
        # Load the data
        stats = load_seed_data(data, conflict_resolver=web_resolver)
        
        return jsonify({
            "success": len(stats.errors) == 0,
            "stats": {
                "goals_created": stats.goals_created,
                "goals_skipped": stats.goals_skipped,
                "projects_created": stats.projects_created,
                "projects_skipped": stats.projects_skipped,
                "tasks_created": stats.tasks_created,
                "tasks_skipped": stats.tasks_skipped,
                "calendars_added": stats.calendars_added,
            },
            "errors": stats.errors[:10] if stats.errors else [],
            "summary": stats.summary(),
        })
    
    @app.route("/api/seed/export")
    def api_seed_export():
        """Export current data as seed JSON."""
        include_tasks = request.args.get('tasks', 'true').lower() == 'true'
        include_done = request.args.get('done', 'false').lower() == 'true'
        
        data = export_seed_data(include_tasks=include_tasks, include_done_tasks=include_done)
        
        # Return as downloadable file or JSON
        if request.args.get('download', 'false').lower() == 'true':
            from flask import Response
            import json
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            return Response(
                json_str,
                mimetype='application/json',
                headers={'Content-Disposition': 'attachment; filename=noctem-export.json'}
            )
        
        return jsonify(data)
    
    @app.route("/api/seed/text", methods=["POST"])
    def api_seed_text():
        """
        Parse and load natural language seed data.
        
        Accepts: JSON {"text": "Goals:\n-Goal 1\n..."} or plain text body
        Returns JSON: {"stats": {...}, "parsed": {...}, "success": true}
        """
        # Get the text
        if request.is_json:
            data = request.get_json()
            text = data.get('text', '')
        else:
            text = request.get_data(as_text=True)
        
        if not text or not text.strip():
            return jsonify({"error": "No text provided", "success": False}), 400
        
        # Parse natural language format
        parsed = parse_natural_seed_text(text)
        
        # Check if anything was parsed
        total_items = len(parsed['goals']) + len(parsed['projects']) + len(parsed['tasks']) + len(parsed['calendar_urls'])
        if total_items == 0:
            return jsonify({
                "error": "Could not parse any items. Make sure format starts with 'Goals:' section.",
                "success": False,
                "parsed": parsed,
            }), 400
        
        # Get conflict mode from request
        mode = request.args.get('mode', 'skip')  # skip, overwrite
        
        def web_resolver(entity_type: str, name: str, existing_id: int) -> ConflictAction:
            return ConflictAction.OVERWRITE if mode == 'overwrite' else ConflictAction.SKIP
        
        # Load the data
        stats = load_seed_data(parsed, conflict_resolver=web_resolver)
        
        return jsonify({
            "success": len(stats.errors) == 0,
            "parsed": {
                "goals": len(parsed['goals']),
                "projects": len(parsed['projects']),
                "tasks": len(parsed['tasks']),
                "calendars": len(parsed['calendar_urls']),
            },
            "stats": {
                "goals_created": stats.goals_created,
                "goals_skipped": stats.goals_skipped,
                "projects_created": stats.projects_created,
                "projects_skipped": stats.projects_skipped,
                "tasks_created": stats.tasks_created,
                "tasks_skipped": stats.tasks_skipped,
                "calendars_added": stats.calendars_added,
            },
            "errors": stats.errors[:10] if stats.errors else [],
            "summary": stats.summary(),
        })
    
    # =========================================================================
    # v0.6.0 Final: Thinking Feed API
    # =========================================================================
    
    @app.route("/api/thinking/recent")
    def api_thinking_recent():
        """
        Get recent thinking feed entries.
        
        Query params:
        - limit: Max entries (default 50)
        - level: Filter by level ('all', 'activity', 'decisions')
        - since_id: Get entries after this ID
        """
        from ..services.conversation_service import (
            get_thinking_feed, get_thinking_feed_since, export_thinking_log
        )
        
        limit = request.args.get('limit', 50, type=int)
        level = request.args.get('level', 'all')
        since_id = request.args.get('since_id', type=int)
        
        if since_id:
            entries = get_thinking_feed_since(since_id)
        else:
            entries = get_thinking_feed(limit=limit, level_filter=level)
        
        return jsonify({
            "entries": [
                {
                    "id": e.id,
                    "timestamp": e.created_at.isoformat() if e.created_at else None,
                    "source": e.source,
                    "level": e.thinking_level,
                    "summary": e.thinking_summary or e.content,
                }
                for e in entries
            ],
            "count": len(entries),
        })
    
    @app.route("/api/thinking/export")
    def api_thinking_export():
        """Export thinking log as JSON file."""
        from ..services.conversation_service import export_thinking_log
        from flask import Response
        import json
        
        level = request.args.get('level', 'all')
        data = export_thinking_log(level_filter=level)
        
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        return Response(
            json_str,
            mimetype='application/json',
            headers={'Content-Disposition': 'attachment; filename=noctem-thinking-log.json'}
        )
    
    # =========================================================================
    # v0.6.0 Final: Forecast API
    # =========================================================================
    
    @app.route("/api/forecast")
    def api_forecast():
        """Get 14-day forecast data."""
        from ..services.forecast_service import get_14_day_forecast
        
        forecasts = get_14_day_forecast()
        
        return jsonify({
            "days": [
                {
                    "date": f.date.isoformat(),
                    "day_name": f.day_name,
                    "is_today": f.is_today,
                    "is_weekend": f.is_weekend,
                    "density": f.density,
                    "density_label": f.density_label,
                    "task_count": f.task_count,
                    "event_count": f.event_count,
                    "brief": f.brief,
                }
                for f in forecasts
            ],
        })
    
    @app.route("/api/week")
    def api_week():
        """Get 7-day table data for the current week (Mon-Sun)."""
        from ..services.forecast_service import get_7_day_table_data
        
        return jsonify({
            "days": get_7_day_table_data(),
        })
    
    # =========================================================================
    # v0.6.0 Final: Prompt Management API
    # =========================================================================
    
    @app.route("/api/prompts")
    def api_prompts_list():
        """List all prompt templates."""
        from ..services.prompt_service import list_prompts, seed_default_prompts
        
        # Ensure defaults exist
        seed_default_prompts()
        
        templates = list_prompts()
        return jsonify({
            "templates": [
                {
                    "name": t.name,
                    "description": t.description,
                    "current_version": t.current_version,
                }
                for t in templates
            ],
        })
    
    @app.route("/api/prompts/<name>")
    def api_prompt_get(name):
        """Get a prompt template with current version."""
        from ..services.prompt_service import get_prompt_with_context
        
        ctx = get_prompt_with_context(name)
        if not ctx:
            return jsonify({"error": "Prompt not found"}), 404
        
        return jsonify({
            "name": ctx["template"].name,
            "description": ctx["template"].description,
            "current_version": ctx["template"].current_version,
            "prompt_text": ctx["current_version"].prompt_text if ctx["current_version"] else "",
            "variables": ctx["variables"],
            "history_count": ctx["history_count"],
        })
    
    @app.route("/api/prompts/<name>", methods=["PUT"])
    def api_prompt_update(name):
        """Update a prompt template (creates new version)."""
        from ..services.prompt_service import update_prompt
        
        data = request.get_json()
        if not data or 'prompt_text' not in data:
            return jsonify({"error": "No prompt_text provided", "success": False}), 400
        
        new_version = update_prompt(
            name,
            data['prompt_text'],
            created_by='user',
            description=data.get('description'),
        )
        
        if not new_version:
            return jsonify({"error": "Prompt not found", "success": False}), 404
        
        return jsonify({
            "success": True,
            "new_version": new_version.version,
        })
    
    @app.route("/api/prompts/<name>/history")
    def api_prompt_history(name):
        """Get version history for a prompt."""
        from ..services.prompt_service import get_prompt_history
        
        history = get_prompt_history(name)
        return jsonify({
            "versions": [
                {
                    "version": v.version,
                    "prompt_text": v.prompt_text,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                    "created_by": v.created_by,
                }
                for v in history
            ],
        })
    
    @app.route("/api/prompts/<name>/rollback", methods=["POST"])
    def api_prompt_rollback(name):
        """Rollback a prompt to a previous version."""
        from ..services.prompt_service import rollback_prompt
        
        data = request.get_json()
        if not data or 'to_version' not in data:
            return jsonify({"error": "No to_version provided", "success": False}), 400
        
        new_version = rollback_prompt(name, data['to_version'])
        
        if not new_version:
            return jsonify({"error": "Version not found", "success": False}), 404
        
        return jsonify({
            "success": True,
            "new_version": new_version.version,
        })
    
    return app


def run_web():
    """Run the web dashboard."""
    app = create_app()
    host = Config.web_host()
    port = Config.web_port()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_web()
