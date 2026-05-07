"""
Flask web dashboard for Noctem.
Read-only view of goals, projects, and tasks.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import ipaddress
import json
import re

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session

from ..config import Config
from ..services import task_service, project_service, goal_service
from ..services.time_blocks import get_time_blocks_for_date
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
from ..mcp import get_mcp_server
from ..db import get_db

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


@dataclass
class User:
    user_id: int
    username: str
    role: str = "public"
    member_id: int | None = None
    artist_id: int | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_member(self) -> bool:
        return self.role in {"admin", "member"}


@dataclass
class Admin(User):
    role: str = "admin"

def create_app(*, portal_mode: bool = False, cor_unum_private_only: bool = True) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder="templates_portal" if portal_mode else "templates",
        static_folder="static",
    )
    app.secret_key = 'noctem-dev-key'  # For flash messages

    def _calendar_redirect_response(default_endpoint: str = "calendar_upload"):
        target = (request.form.get("next", "") or request.args.get("next", "")).strip().lower()
        if target == "settings":
            return redirect(url_for("settings", _anchor="calendar-import"))
        return redirect(url_for(default_endpoint))

    def _request_remote_ip() -> str:
        return (
            (request.headers.get("X-Forwarded-For", "").split(",")[0].strip())
            or str(request.remote_addr or "")
        )

    def _is_private_request() -> bool:
        remote = _request_remote_ip()
        if remote in {"localhost", ""}:
            return True
        try:
            addr = ipaddress.ip_address(remote)
        except ValueError:
            return False
        if addr.is_loopback or addr.is_private:
            return True
        if isinstance(addr, ipaddress.IPv4Address):
            if addr in ipaddress.ip_network("100.64.0.0/10"):
                return True
        return False

    def _seed_default_cu_session() -> None:
        session_mode = str(session.get("cu_app_mode") or "").strip().lower()
        if portal_mode:
            if session.get("cu_role") and session_mode == "portal":
                return
            session["cu_role"] = "public"
            session["cu_user_id"] = 0
            session["cu_username"] = "public"
            session["cu_member_id"] = None
            session["cu_app_mode"] = "portal"
        elif _is_private_request():
            if session.get("cu_role") and session_mode == "internal":
                return
            session["cu_role"] = "admin"
            session["cu_user_id"] = 1
            session["cu_username"] = "cor_unum_admin"
            session["cu_member_id"] = None
            session["cu_app_mode"] = "internal"
        else:
            if session.get("cu_role"):
                return
            session["cu_role"] = "public"
            session["cu_user_id"] = 0
            session["cu_username"] = "public"
            session["cu_member_id"] = None
            session["cu_app_mode"] = "internal"

    def _set_cu_session_role(
        *,
        role: str,
        username: str,
        user_id: int,
        member_id: int | None = None,
    ) -> None:
        session["cu_role"] = role
        session["cu_username"] = username
        session["cu_user_id"] = int(user_id)
        session["cu_member_id"] = int(member_id) if member_id is not None else None
        session["cu_app_mode"] = "portal" if portal_mode else "internal"

    def _get_current_cu_user() -> User:
        _seed_default_cu_session()
        role = str(session.get("cu_role") or "public").strip().lower()
        if role == "admin":
            return Admin(
                user_id=int(session.get("cu_user_id") or 1),
                username=str(session.get("cu_username") or "cor_unum_admin"),
            )
        if role == "member":
            member_id = session.get("cu_member_id")
            if member_id is None:
                _set_cu_session_role(role="public", username="public", user_id=0, member_id=None)
                return User(user_id=0, username="public", role="public")
            with get_db() as conn:
                member = conn.execute(
                    """SELECT m.id, m.username, m.artist_id
                       FROM cu_members m
                       WHERE m.id = ? AND m.is_active = 1""",
                    (int(member_id),),
                ).fetchone()
            if not member:
                _set_cu_session_role(role="public", username="public", user_id=0, member_id=None)
                return User(user_id=0, username="public", role="public")
            return User(
                user_id=10_000 + int(member["id"]),
                username=str(member["username"]),
                role="member",
                member_id=int(member["id"]),
                artist_id=int(member["artist_id"]) if member["artist_id"] is not None else None,
            )
        return User(
            user_id=int(session.get("cu_user_id") or 0),
            username=str(session.get("cu_username") or "public"),
            role="public",
        )

    def _cu_actor_label(user: User | None = None) -> str:
        user = user or _get_current_cu_user()
        if user.role == "admin":
            return f"cu_admin:{user.username}"
        if user.role == "member":
            suffix = f":{user.member_id}" if user.member_id is not None else ""
            return f"cu_member:{user.username}{suffix}"
        return "cu_public"

    def _require_cu_admin():
        user = _get_current_cu_user()
        if not user.is_admin:
            return jsonify({"success": False, "error": "Admin access required"}), 403
        return None

    def _require_cu_member_or_admin():
        user = _get_current_cu_user()
        if not user.is_member:
            return jsonify({"success": False, "error": "Member or admin access required"}), 403
        return None

    def _cu_assume_capabilities(user: User | None = None) -> dict:
        current = user or _get_current_cu_user()
        is_local = _is_private_request()
        return {
            "is_local_request": is_local,
            "can_assume_admin": bool(current.is_admin or (is_local and not portal_mode)),
            "can_assume_member": True,
        }

    def _is_portal_page_allowed(path: str) -> bool:
        if path in {
            "/",
            "/health",
            "/favicon.ico",
            "/cor-unum",
            "/cor-unum/upcoming",
            "/cor-unum/add-event",
            "/cor-unum/db/events",
            "/cor-unum/db/artists",
            "/cor-unum/db/venues",
        }:
            return True
        if re.fullmatch(r"/cor-unum/(event|artist|venue)/\d+", path):
            return True
        if path.startswith("/static/"):
            return True
        return False

    def _is_portal_api_allowed(path: str) -> bool:
        if path in {
            "/api/cor-unum/session",
            "/api/cor-unum/session/assume",
            "/api/cor-unum/upcoming",
            "/api/cor-unum/events",
            "/api/cor-unum/events/create",
            "/api/cor-unum/artists",
            "/api/cor-unum/artists/search",
            "/api/cor-unum/venues",
            "/api/cor-unum/venues/search",
            "/api/cor-unum/suggestions",
        }:
            return True
        if re.fullmatch(r"/api/cor-unum/events/\d+", path):
            return True
        if re.fullmatch(r"/api/cor-unum/events/\d+/update", path):
            return True
        if re.fullmatch(r"/api/cor-unum/artists/\d+", path):
            return True
        if re.fullmatch(r"/api/cor-unum/artists/\d+/update", path):
            return True
        if re.fullmatch(r"/api/cor-unum/venues/\d+", path):
            return True
        if re.fullmatch(r"/api/cor-unum/venues/\d+/update", path):
            return True
        if re.fullmatch(r"/api/cor-unum/history/(event|artist|venue|event_source)/\d+", path):
            return True
        return False

    def _enforce_portal_scope():
        path = str(request.path or "")
        if path in {"/", "/cor-unum"}:
            return redirect(url_for("cor_unum_upcoming"))
        if path.startswith("/api/"):
            if not _is_portal_api_allowed(path):
                return jsonify({"success": False, "error": "Endpoint not available in portal mode"}), 403
            return None
        if _is_portal_page_allowed(path):
            return None
        return redirect(url_for("cor_unum_upcoming"))

    def _enforce_cu_scope():
        if portal_mode:
            return _enforce_portal_scope()
        path = str(request.path or "")
        if path.startswith("/static/") or path in {"/favicon.ico", "/health"}:
            return None
        if not cor_unum_private_only:
            return None
        if _is_private_request():
            return None
        if path.startswith("/cor-unum"):
            return redirect(url_for("dashboard"))
        if path.startswith("/api/cor-unum"):
            return jsonify({"success": False, "error": "Cor Unum dashboard APIs are private-only"}), 403
        return None

    @app.context_processor
    def _inject_cu_template_context():
        current = _get_current_cu_user()
        return {
            "cu_session_user": current,
            "cu_is_local_request": _is_private_request(),
            "cu_show_session_controls": portal_mode,
        }

    @app.before_request
    def _bootstrap_cu_session():
        _get_current_cu_user()
        private_scope_response = _enforce_cu_scope()
        if private_scope_response is not None:
            return private_scope_response
    
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
        
        # v0.9.3: Lean runtime status (legacy AI surfaces removed)
        active_task_count = len(all_active_tasks)
        week_event_count = sum(len(day["events"]) for day in week_data)
        system_status = {
            "mode": "agentic-transition",
            "voice_enabled": True,
        }
        
        # v0.6.0 Final: Forecast data
        from ..services.forecast_service import get_14_day_forecast, get_14_day_table_data
        forecast_14 = get_14_day_forecast()
        two_week_data = get_14_day_table_data()
        
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
            active_task_count=active_task_count,
            week_event_count=week_event_count,
            system_status=system_status,
            # v0.9.2 data
            forecast_14=forecast_14,
            current_week=two_week_data['current_week'],
            next_week=two_week_data['next_week'],
        )

    @app.route("/feedback")
    def feedback_page():
        """Feedback capture page — view and submit feedback."""
        return render_template("feedback.html")

    @app.route("/control")
    def control():
        """Unified control surface: Reviews, Tasks, Background."""
        return render_template("control.html")

    @app.route("/reviews")
    def reviews():
        """Legacy review route redirects to Control."""
        return redirect(url_for("control"))

    @app.route("/tools")
    def tools():
        """Legacy tools route redirects to Control."""
        return redirect(url_for("control"))

    @app.route("/graph")
    def graph_view():
        """Noctem-native object graph + internal versioning page."""
        return render_template("graph.html")
    
    @app.route("/health")
    def health():
        """Health check endpoint."""
        return {"status": "ok", "time": datetime.now().isoformat()}
    
    @app.route("/prompts")
    def prompts():
        """Legacy prompts page removed in v0.9.3."""
        flash("Prompt management has been removed from active runtime in v0.9.3.", "error")
        return redirect(url_for("settings"))
    
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
                return _calendar_redirect_response()
            
            # Check for file upload
            if 'ics_file' not in request.files or request.files['ics_file'].filename == '':
                flash('Please provide a URL or upload a file', 'error')
                return _calendar_redirect_response()
            
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
            
            return _calendar_redirect_response()
        
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
        
        return _calendar_redirect_response()
    
    @app.route("/calendar/remove", methods=["POST"])
    def calendar_remove_url():
        """Remove a saved URL."""
        url = request.form.get('url', '').strip()
        if url:
            remove_url(url)
            flash("URL removed", 'success')
        return _calendar_redirect_response()
    
    @app.route("/calendar/clear", methods=["POST"])
    def calendar_clear():
        """Clear all imported calendar events."""
        count = clear_ics_events()
        flash(f"Cleared {count} calendar events", 'success')
        return _calendar_redirect_response()
    
    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        """Settings page for configuring Noctem."""
        if request.method == "POST":
            existing_config = Config.get_all()
            text_fields = [
                'telegram_bot_token',
                'telegram_chat_id',
                'timezone',
                'web_host',
                'chat_assistant_name',
                'chat_default_thread_id',
                'chat_ollama_model',
                'chat_ollama_base_url',
            ]
            allow_empty_text = {'chat_default_thread_id'}
            preserve_if_blank = {'telegram_bot_token', 'telegram_chat_id'}

            for field in text_fields:
                value = request.form.get(field, '').strip()
                if value or field in allow_empty_text:
                    Config.set(field, value)
                elif field in preserve_if_blank:
                    Config.set(field, str(existing_config.get(field, '') or '').strip())

            web_port_raw = request.form.get('web_port', '').strip()
            try:
                web_port = int(web_port_raw) if web_port_raw else 5000
            except ValueError:
                web_port = 5000
            Config.set('web_port', web_port)

            bool_fields = [
                'chat_model_first_enabled',
                'chat_unified_continuity',
                'chat_brief_mode',
            ]
            for field in bool_fields:
                Config.set(field, bool(request.form.get(field)))
            
            Config.clear_cache()
            flash('Settings saved successfully!', 'success')
            return redirect(url_for('settings'))
        
        # GET - show settings form
        config = Config.get_all()
        saved_urls = get_saved_urls()
        return render_template(
            "settings.html",
            config=config,
            timezones=COMMON_TIMEZONES,
            saved_urls=saved_urls,
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
        Chat endpoint routed through model-first chat orchestrator.
        
        Accepts JSON: {"message": "buy groceries tomorrow"}
        Returns JSON: {"response": "✓ Created task...", "success": true}
        """
        from ..agent.execution_queue_runtime import process_chat_message_via_queue
        from ..parser.command import parse_command, CommandType
        from ..services.feedback_service import prepend_feedback as _prepend_feedback
        
        data = request.get_json() or {}
        if not data or 'message' not in data:
            return jsonify({"error": "No message provided", "success": False}), 400
        
        message = data['message'].strip()
        if not message:
            return jsonify({"error": "Empty message", "success": False}), 400

        # Fast-path: .f feedback capture (bypass queue runtime)
        _parsed_cmd = parse_command(message)
        if _parsed_cmd.type == CommandType.FEEDBACK:
            _fb_text = message
            _lower = _fb_text.lower()
            if _lower.startswith(".f") or _lower.startswith("/f"):
                _fb_text = _fb_text[2:].strip()
            if not _fb_text:
                return jsonify({"error": "Empty feedback", "success": False}), 400
            fb_result = _prepend_feedback(_fb_text, source="web.fast_path")
            if not fb_result.get("ok"):
                return jsonify({"error": "Unable to save feedback", "success": False}), 500
            return jsonify({
                "response": "✓ Feedback captured.",
                "success": True,
                "mode": "fast_path",
                "timestamp": datetime.now().isoformat(),
            })

        requested_thread_id = (
            (data.get("thread_id") or "")
            or (request.headers.get("X-Noctem-Thread") or "")
            or (session.get("chat_thread_id") or "")
        ).strip() or None
        try:
            result = process_chat_message_via_queue(
                message,
                source="web",
                thread_id=requested_thread_id,
            )
            session["chat_thread_id"] = result.get("thread_id")
            return jsonify({
                "response": result.get("response", "✓ Done"),
                "success": True,
                "thread_id": result.get("thread_id"),
                "mode": result.get("mode"),
                "model": result.get("model"),
                "requires_action": result.get("requires_action"),
                "memory_pack": result.get("memory_pack"),
                "fallback_reason": result.get("fallback_reason"),
                "workflow_id": result.get("workflow_id"),
                "queue_item_id": result.get("queue_item_id"),
                "status": result.get("status"),
                "interrupt": result.get("interrupt"),
                "review": result.get("review"),
                "task": result.get("task"),
                "updated_count": result.get("updated_count"),
                "updated_task_ids": result.get("updated_task_ids"),
                "deleted_task_id": result.get("deleted_task_id"),
                "intent": result.get("intent"),
                "intent_classifier": result.get("intent_classifier"),
                "intent_confidence": result.get("intent_confidence"),
                "timestamp": datetime.now().isoformat(),
            })
            
        except ValueError as e:
            return jsonify({
                "error": str(e),
                "success": False,
            }), 400
        except Exception as e:
            return jsonify({
                "error": str(e),
                "success": False,
            }), 500
    
    @app.route("/api/chat/history")
    def api_chat_history():
        """Get recent chat history from durable conversation records."""
        from ..services.conversation_service import get_thread_context, resolve_thread_id

        limit = max(1, min(request.args.get('limit', 50, type=int), 200))
        requested_thread_id = (
            (request.args.get("thread_id") or "")
            or (request.headers.get("X-Noctem-Thread") or "")
            or (session.get("chat_thread_id") or "")
        ).strip() or None

        thread_id = resolve_thread_id(source="web", thread_id=requested_thread_id)
        session["chat_thread_id"] = thread_id
        turns = get_thread_context(thread_id, limit=limit * 2, include_system=False)

        messages = []
        for turn in turns:
            messages.append({
                "id": turn.id,
                "role": turn.role,
                "content": turn.content,
                "timestamp": turn.created_at.isoformat() if turn.created_at else None,
                "source": turn.source,
                "thread_id": turn.session_id,
            })

        history = []
        pending_user = None
        for turn in turns:
            if turn.role == "user":
                pending_user = turn
                continue
            if turn.role == "assistant" and pending_user is not None:
                history.append({
                    "message": pending_user.content,
                    "response": turn.content,
                    "timestamp": turn.created_at.isoformat() if turn.created_at else None,
                    "source": turn.source,
                    "thread_id": thread_id,
                })
                pending_user = None

        return jsonify({
            "thread_id": thread_id,
            "messages": messages[-(limit * 2):],
            "history": history[-limit:],
        })
    
    # =========================================================================
    # Feedback export API
    # =========================================================================

    @app.route("/api/feedback", methods=["GET"])
    def api_feedback_export():
        """Export the singleton feedback document."""
        from ..services.feedback_service import export_feedback
        return jsonify({"success": True, **export_feedback()})

    @app.route("/api/feedback", methods=["POST"])
    def api_feedback_save():
        """Overwrite the singleton feedback document body."""
        from ..services.feedback_service import save_feedback_body
        data = request.get_json() or {}
        body = data.get("body", "")
        result = save_feedback_body(body, source="web")
        return jsonify({"success": result.get("ok", False), "version_id": result.get("version_id")})

    # =========================================================================
    # v0.9.3: Agent workflow API
    # =========================================================================
    
    @app.route("/api/agent/submit", methods=["POST"])
    def api_agent_submit():
        """Submit input text to the agent workflow."""
        from ..agent.workflow import submit_input
        
        data = request.get_json() or {}
        text = (data.get("input") or data.get("text") or "").strip()
        if not text:
            return jsonify({"success": False, "error": "No input provided"}), 400
        
        try:
            result = submit_input(text, source="web")
            return jsonify({"success": True, **result})
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
    
    @app.route("/api/agent/status/<int:workflow_id>")
    def api_agent_status(workflow_id: int):
        """Get current status + actions for a workflow."""
        from ..agent.workflow import get_workflow_status
        
        status_data = get_workflow_status(workflow_id)
        if not status_data:
            return jsonify({"success": False, "error": "Workflow not found"}), 404
        return jsonify({"success": True, **status_data})
    
    @app.route("/api/agent/resume/<int:workflow_id>", methods=["POST"])
    def api_agent_resume(workflow_id: int):
        """Resume an interrupted workflow with user response."""
        from ..agent.workflow import resume_workflow
        
        data = request.get_json() or {}
        resolution = (data.get("response") or data.get("input") or "").strip()
        decision = (data.get("decision") or "").strip()
        instructions = (data.get("instructions") or "").strip()
        if not resolution and decision:
            resolution = f"{decision} {instructions}".strip() if instructions else decision
        if not resolution:
            return jsonify({"success": False, "error": "No response provided"}), 400
        
        try:
            result = resume_workflow(workflow_id, resolution)
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        
        if result is None:
            return jsonify({"success": False, "error": "No pending interrupt for workflow"}), 404
        return jsonify({"success": True, **result})
    
    @app.route("/api/agent/interrupts")
    def api_agent_interrupts():
        """List all pending interrupts across workflows."""
        from ..agent.workflow import list_pending_interrupts
        
        interrupts = list_pending_interrupts()
        return jsonify({
            "success": True,
            "count": len(interrupts),
            "interrupts": interrupts,
        })

    @app.route("/api/agent/reviews")
    def api_agent_reviews():
        """List review queue items with optional filtering."""
        from ..agent.review_queue import list_review_items

        status = (request.args.get("status") or "pending").strip().lower()
        reason_code = (request.args.get("reason_code") or "").strip().lower() or None
        workflow_id = request.args.get("workflow_id", type=int)
        limit = max(1, min(request.args.get("limit", 50, type=int), 500))

        reviews = list_review_items(
            status=status if status != "all" else None,
            reason_code=reason_code,
            workflow_id=workflow_id,
            limit=limit,
        )
        return jsonify({
            "success": True,
            "count": len(reviews),
            "reviews": reviews,
        })

    @app.route("/api/agent/reviews/blocked")
    def api_agent_reviews_blocked():
        """List blocked workflows with associated pending review items."""
        from ..agent.review_queue import list_blocked_workflows

        limit = max(1, min(request.args.get("limit", 100, type=int), 500))
        blocked = list_blocked_workflows(limit=limit)
        return jsonify({
            "success": True,
            "count": len(blocked),
            "blocked_workflows": blocked,
        })

    def _drain_queue_to_item(queue_item_id: int | None):
        if queue_item_id is None:
            return None
        from ..agent.execution_queue_runtime import process_execution_queue

        try:
            results = process_execution_queue(
                worker_id="review-api",
                max_items=200,
                stop_on_item_id=int(queue_item_id),
            )
        except Exception:
            return None
        for result in reversed(results):
            try:
                if int(result.get("queue_item_id") or -1) == int(queue_item_id):
                    return result
            except Exception:
                continue
        return None

    @app.route("/api/reviews/<review_id>/resolve", methods=["POST"])
    def api_review_resolve(review_id: str):
        """Unified resolve endpoint — replaces separate approve/reject/resume.

        JSON body:
            action: "approve" | "reject" | "resume"  (required)
            response: str  (required for resume, optional for approve/reject)
            notes: str     (optional)
        """
        from ..agent.review_queue import get_review_item, resolve_review_item
        from ..services.execution_queue import (
            cancel_item, enqueue_review_resume, requeue_item,
        )

        review = get_review_item(review_id)
        if not review:
            return jsonify({"success": False, "error": "Review item not found"}), 404

        data = request.get_json() or {}
        action = (data.get("action") or "").strip().lower()
        if action not in ("approve", "reject", "resume"):
            return jsonify({"success": False, "error": "action must be approve, reject, or resume"}), 400

        notes = (data.get("notes") or "").strip() or None
        payload = review.get("payload") if isinstance(review.get("payload"), dict) else {}
        workflow_id = payload.get("workflow_id")
        queue_item_id = payload.get("queue_item_id")

        # --- action-specific defaults ---
        if action == "approve":
            resolution = (data.get("response") or "yes").strip()
            resolve_status = "approved"
        elif action == "reject":
            resolution = (data.get("response") or "no").strip()
            resolve_status = "rejected"
        else:  # resume
            resolution = (data.get("response") or data.get("input") or "").strip()
            if not resolution:
                return jsonify({"success": False, "error": "No response provided for resume"}), 400
            resolve_status = "resolved"

        queue_resume_item = None
        resume_result = None
        requeued_item = None
        cancelled_item = None

        # enqueue resume work for approve / resume
        if action in ("approve", "resume") and workflow_id is not None:
            queue_resume_item = enqueue_review_resume(
                workflow_id=int(workflow_id),
                review_id=review_id,
                resolution=resolution,
                thread_id=str(payload.get("thread_id") or "").strip() or None,
                review_created_at=review.get("created_at"),
            )
            resume_result = _drain_queue_to_item(queue_resume_item.get("id")) or queue_resume_item

        # requeue linked item for approve / resume
        if action in ("approve", "resume") and queue_item_id is not None:
            requeued_item = requeue_item(
                int(queue_item_id),
                front=True,
                reason=f"review_{action}d" if action == "approve" else f"review_resumed:{resolution}",
            )
            _drain_queue_to_item(int(queue_item_id))

        # cancel linked item for reject
        if action == "reject" and queue_item_id is not None:
            cancelled_item = cancel_item(int(queue_item_id), reason="review_rejected")

        updated_review = resolve_review_item(
            review_id,
            status=resolve_status,
            resolution_notes=notes or f"{action.title()}d via Control: {resolution}",
        ) or get_review_item(review_id) or review

        return jsonify({
            "success": True,
            "review": updated_review,
            "resume_result": resume_result,
            "queue_resume_item": queue_resume_item,
            "requeued_item": requeued_item,
            "cancelled_item": cancelled_item,
        })

    @app.route("/api/reviews")
    def api_reviews_grouped():
        """Reviews grouped by category for the Control tab."""
        from ..agent.review_queue import list_review_items

        status = (request.args.get("status") or "pending").strip().lower()
        limit = max(1, min(request.args.get("limit", 100, type=int), 500))
        items = list_review_items(
            status=status if status != "all" else None,
            limit=limit,
        )
        grouped: dict[str, list] = {}
        for item in items:
            cat = item.get("category", "manual_review")
            grouped.setdefault(cat, []).append(item)
        return jsonify({"success": True, "grouped": grouped, "total": len(items)})

    @app.route("/api/tasks/active")
    def api_tasks_active():
        """Active execution-queue items for the Control tab Tasks section."""
        from ..services.execution_queue import list_queue_items, queue_metrics

        limit = max(1, min(request.args.get("limit", 50, type=int), 500))
        active_statuses = ["queued", "processing", "review_blocked"]
        items: list[dict] = []
        for st in active_statuses:
            items.extend(list_queue_items(status=st, limit=limit))
        return jsonify({
            "success": True,
            "items": items,
            "metrics": queue_metrics(),
        })

    @app.route("/api/tools")
    def api_tools():
        """Combined tools payload for queue and scheduler."""
        from ..agent.review_queue import list_blocked_workflows, list_review_items
        from ..scheduler.jobs import get_scheduler_status
        from ..services.async_delivery import delivery_metrics, list_delivery_publications
        from ..services.execution_queue import list_queue_items, queue_metrics

        limit = max(1, min(request.args.get("limit", 50, type=int), 500))
        status = (request.args.get("status") or "all").strip().lower()
        review_status = (request.args.get("review_status") or "pending").strip().lower()
        diagnostics: list[str] = []
        queue_items = []
        queue_snapshot = {}
        scheduler_status = {}
        delivery_snapshot = {"metrics": {}, "recent": []}
        review_snapshot = {"items": [], "blocked_workflows": []}
        try:
            queue_items = list_queue_items(status=status, limit=limit)
        except Exception as exc:
            diagnostics.append(f"queue:list_failed:{exc}")
        try:
            queue_snapshot = queue_metrics()
        except Exception as exc:
            diagnostics.append(f"queue:metrics_failed:{exc}")
        try:
            scheduler_status = get_scheduler_status()
        except Exception as exc:
            diagnostics.append(f"scheduler:status_failed:{exc}")
            scheduler_status = {
                "job_config": Config.get("scheduler_job_config", {}) or {},
                "job_stats": {},
                "recent_runs": [],
            }
        try:
            delivery_snapshot = {
                "metrics": delivery_metrics(),
                "recent": list_delivery_publications(limit=60),
            }
        except Exception as exc:
            diagnostics.append(f"delivery:summary_failed:{exc}")
        try:
            review_snapshot = {
                "items": list_review_items(
                    status=review_status if review_status != "all" else None,
                    limit=limit,
                ),
                "blocked_workflows": list_blocked_workflows(limit=min(limit, 200)),
            }
        except Exception as exc:
            diagnostics.append(f"reviews:summary_failed:{exc}")
        return jsonify({
            "success": True,
            "queue": {
                "items": queue_items,
                "metrics": queue_snapshot,
            },
            "scheduler": scheduler_status,
            "delivery": delivery_snapshot,
            "reviews": review_snapshot,
            "diagnostics": diagnostics,
        })

    @app.route("/api/tools/queue")
    def api_tools_queue_list():
        """List queue items and queue metrics."""
        from ..services.execution_queue import list_queue_items, queue_metrics

        limit = max(1, min(request.args.get("limit", 100, type=int), 500))
        status = (request.args.get("status") or "all").strip().lower()
        items = list_queue_items(status=status, limit=limit)
        return jsonify({
            "success": True,
            "count": len(items),
            "items": items,
            "metrics": queue_metrics(),
        })

    @app.route("/api/tools/queue/<int:item_id>")
    def api_tools_queue_detail(item_id: int):
        """Get one queue item by id."""
        from ..services.execution_queue import get_queue_item

        item = get_queue_item(item_id)
        if item is None:
            return jsonify({"success": False, "error": "Queue item not found"}), 404
        return jsonify({"success": True, "item": item})

    @app.route("/api/tools/queue/<int:item_id>/cancel", methods=["POST"])
    def api_tools_queue_cancel(item_id: int):
        """Cancel a queue item."""
        from ..services.execution_queue import cancel_item

        data = request.get_json(silent=True) or {}
        reason = (data.get("reason") or "").strip() or None
        updated = cancel_item(item_id, reason=reason)
        if updated is None:
            return jsonify({"success": False, "error": "Queue item not found"}), 404
        return jsonify({"success": True, "item": updated})

    @app.route("/api/tools/queue/<int:item_id>/requeue", methods=["POST"])
    def api_tools_queue_requeue(item_id: int):
        """Requeue a queue item, optionally to the front."""
        from ..services.execution_queue import requeue_item

        data = request.get_json(silent=True) or {}
        front = bool(data.get("front"))
        reason = (data.get("reason") or "").strip() or None
        updated = requeue_item(item_id, front=front, reason=reason)
        if updated is None:
            return jsonify({"success": False, "error": "Queue item not found"}), 404
        return jsonify({"success": True, "item": updated})

    @app.route("/api/tools/scheduler/status")
    def api_tools_scheduler_status():
        """Get scheduler status snapshot."""
        from ..scheduler.jobs import get_scheduler_status

        return jsonify({"success": True, "scheduler": get_scheduler_status()})

    @app.route("/api/tools/scheduler/history")
    def api_tools_scheduler_history():
        """Get scheduler run history."""
        from ..scheduler.jobs import get_job_run_history

        limit = max(1, min(request.args.get("limit", 50, type=int), 500))
        job_name = (request.args.get("job_name") or "").strip() or None
        history = get_job_run_history(job_name=job_name, limit=limit)
        return jsonify({
            "success": True,
            "count": len(history),
            "runs": history,
        })

    @app.route("/api/tools/scheduler/jobs/<job_name>", methods=["POST"])
    def api_tools_scheduler_update_job(job_name: str):
        """Update one scheduler job configuration."""
        from ..scheduler.jobs import update_job_config

        data = request.get_json(silent=True) or {}
        interval_minutes = data.get("interval_minutes")
        enabled = data.get("enabled")
        try:
            updated = update_job_config(
                job_name=job_name,
                interval_minutes=int(interval_minutes) if interval_minutes is not None else None,
                enabled=bool(enabled) if enabled is not None else None,
            )
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
        return jsonify({"success": True, "job": updated})

    @app.route("/api/tools/scheduler/jobs/<job_name>/run", methods=["POST"])
    def api_tools_scheduler_run_job(job_name: str):
        """Run one scheduler job immediately."""
        from ..scheduler.jobs import run_job_now

        try:
            result = run_job_now(job_name)
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500
        return jsonify({"success": True, "result": result})

    @app.route("/api/tools/deliveries")
    def api_tools_deliveries():
        """List async delivery publication records."""
        from ..services.async_delivery import delivery_metrics, list_delivery_publications

        limit = max(1, min(request.args.get("limit", 80, type=int), 500))
        queue_item_id = request.args.get("queue_item_id", type=int)
        channel = (request.args.get("channel") or "").strip().lower() or None
        items = list_delivery_publications(
            queue_item_id=queue_item_id,
            channel=channel,
            limit=limit,
        )
        return jsonify({
            "success": True,
            "count": len(items),
            "items": items,
            "metrics": delivery_metrics(),
        })

    # =========================================================================
    # v0.9.4: Object graph + internal versioning surfaces
    # =========================================================================

    @app.route("/api/graph")
    def api_graph():
        """Return object graph nodes/edges from internal object references."""
        from ..services.object_graph import build_object_graph

        limit = max(1, min(request.args.get("limit", 300, type=int), 5000))
        object_type = (request.args.get("object_type") or "").strip().lower() or None
        include_versions = str(request.args.get("include_versions", "")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        graph_payload = build_object_graph(
            limit=limit,
            object_type=object_type,
            include_versions=include_versions,
        )
        return jsonify({
            "success": True,
            "graph": graph_payload,
        })

    @app.route("/api/graph/object/<path:object_id>")
    def api_graph_object(object_id: str):
        """Return one object's versions, provenance events, and relation surface."""
        from ..services.object_graph import get_object_version_surface

        version_limit = max(1, min(request.args.get("version_limit", 40, type=int), 500))
        surface = get_object_version_surface(object_id, version_limit=version_limit)
        if surface is None:
            return jsonify({"success": False, "error": "Object not found"}), 404
        return jsonify({
            "success": True,
            "surface": surface,
        })

    @app.route("/api/graph/versions")
    def api_graph_versions():
        """Return internal commit graph (versions + event provenance links)."""
        from ..services.object_graph import list_version_graph

        limit = max(1, min(request.args.get("limit", 400, type=int), 5000))
        object_id = (request.args.get("object_id") or "").strip() or None
        versions = list_version_graph(limit=limit, object_id=object_id)
        return jsonify({
            "success": True,
            "versions": versions,
        })

    @app.route("/api/graph/export/markdown", methods=["POST"])
    def api_graph_export_markdown():
        """Export graph/object/version surfaces to local markdown snapshot files."""
        from ..services.object_graph import export_graph_markdown_snapshot

        data = request.get_json(silent=True) or {}
        output_dir = (data.get("output_dir") or "").strip() or None
        limit_raw = data.get("limit")
        limit = 500
        if limit_raw is not None:
            try:
                limit = max(1, min(int(limit_raw), 10000))
            except (TypeError, ValueError):
                return jsonify({"success": False, "error": "Invalid limit value"}), 400
        include_context_docs = bool(data.get("include_context_docs", True))

        try:
            manifest = export_graph_markdown_snapshot(
                output_dir=output_dir,
                limit=limit,
                include_context_docs=include_context_docs,
            )
        except ValueError as e:
            return jsonify({"success": False, "error": str(e)}), 400
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 500

        return jsonify({
            "success": True,
            "manifest": manifest,
        })
    
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
            from ..voice.processing import process_pending_voice_journals
            processed_now = process_pending_voice_journals(max_items=1)
            
            return jsonify({
                "journal_id": journal_id,
                "success": True,
                "processed_now": processed_now,
                "message": (
                    "Voice memo uploaded and processed."
                    if processed_now > 0
                    else "Voice memo uploaded. Transcription queued."
                ),
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
    
    @app.route("/api/voice/retry-all", methods=["POST"])
    def api_voice_retry_all():
        """Reset all failed voice journals back to pending for retry."""
        from ..voice.journals import retry_failed_journals
        from ..voice.processing import process_pending_voice_journals
        count = retry_failed_journals()
        processed_now = process_pending_voice_journals(max_items=max(1, count)) if count > 0 else 0
        return jsonify({
            "success": True,
            "count": count,
            "processed_now": processed_now,
            "message": f"Reset {count} failed journal(s) to pending",
        })
    
    @app.route("/api/voice/<int:journal_id>/retry", methods=["POST"])
    def api_voice_retry(journal_id):
        """Reset a single failed voice journal back to pending."""
        from ..voice.journals import retry_journal
        from ..voice.processing import process_pending_voice_journals
        if retry_journal(journal_id):
            processed_now = process_pending_voice_journals(max_items=1)
            return jsonify({
                "success": True,
                "processed_now": processed_now,
                "message": "Journal queued for retry",
            })
        return jsonify({"success": False, "error": "Journal not found or not in failed state"}), 400
    
    @app.route("/api/voice/process", methods=["POST"])
    def api_voice_process():
        """Manually process pending voice journals."""
        from ..voice.processing import process_pending_voice_journals
        max_items = request.args.get("max_items", 3, type=int)
        processed = process_pending_voice_journals(max_items=max_items)
        return jsonify({
            "success": True,
            "processed": processed,
            "message": f"Processed {processed} voice journal(s)",
        })
    
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
    # v0.9.3: Legacy prompt APIs removed
    # =========================================================================
    
    @app.route("/api/prompts", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    @app.route("/api/prompts/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def api_prompts_removed(path):
        """Prompt APIs removed from active runtime in v0.9.3."""
        return jsonify({
            "success": False,
            "error": "Prompt management removed from active runtime in v0.9.3",
        }), 410
    
    # =========================================================================
    # v0.9.2: Task CRUD API (powers inline creation & check-off)
    # =========================================================================
    
    @app.route("/api/tasks", methods=["POST"])
    def api_task_create():
        """Create a new task. Accepts JSON: {name, due_date?, project_id?}"""
        from ..parser.task_parser import parse_task
        
        data = request.get_json()
        if not data or not data.get('name', '').strip():
            return jsonify({"error": "Task name required", "success": False}), 400
        
        raw_name = data['name'].strip()
        parsed = parse_task(raw_name)
        
        # NLP defaults
        name_val = parsed.name or raw_name
        due_date_val = parsed.due_date
        due_time_val = parsed.due_time
        importance_val = parsed.importance
        tags_val = parsed.tags if parsed.tags else None
        recurrence_rule_val = parsed.recurrence_rule
        
        project_id_val = data.get('project_id')
        if project_id_val is None and parsed.project_name:
            p = project_service.get_project_by_name(parsed.project_name)
            if p:
                project_id_val = p.id
        
        # Explicit payload values override parsed values
        if 'due_date' in data and data.get('due_date'):
            try:
                from datetime import date as date_cls
                due_date_val = date_cls.fromisoformat(data['due_date'])
            except (ValueError, TypeError):
                pass
        elif 'due_date' in data and not data.get('due_date'):
            due_date_val = None
        
        if 'due_time' in data and data.get('due_time'):
            try:
                from datetime import time as time_cls
                due_time_val = time_cls.fromisoformat(data['due_time'])
            except (ValueError, TypeError):
                pass
        elif 'due_time' in data and not data.get('due_time'):
            due_time_val = None
        
        if 'importance' in data:
            importance_val = data.get('importance')
        if 'tags' in data:
            tags_val = data.get('tags')
        if 'recurrence_rule' in data:
            recurrence_rule_val = data.get('recurrence_rule')
        if 'project_id' in data:
            project_id_val = data.get('project_id')

        normalized_project_id = None
        if project_id_val is not None and str(project_id_val).strip() != "":
            try:
                normalized_project_id = int(project_id_val)
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid project_id", "success": False}), 400

        mcp_server = get_mcp_server()
        create_result = mcp_server.call_tool(
            "tasks.create",
            {
                "name": name_val,
                "project_id": normalized_project_id,
                "due_date": due_date_val.isoformat() if due_date_val else None,
                "due_time": due_time_val.isoformat() if due_time_val else None,
                "importance": importance_val,
                "tags": tags_val,
                "recurrence_rule": recurrence_rule_val,
            },
            context={"source": "web.api"},
        )
        if not create_result.get("ok"):
            return jsonify({"error": "Unable to create task", "success": False}), 500
        task_payload = create_result["result"].get("task")
        if not isinstance(task_payload, dict):
            return jsonify({"error": "Invalid task payload from MCP create", "success": False}), 500
        
        return jsonify({
            "success": True,
            "task": {
                "id": task_payload.get("id"),
                "name": task_payload.get("name"),
                "due_date": task_payload.get("due_date"),
                "project_id": task_payload.get("project_id"),
                "status": task_payload.get("status"),
            },
        })
    
    @app.route("/api/tasks/<int:task_id>/complete", methods=["POST"])
    def api_task_complete(task_id):
        """Mark a task as done."""
        task = task_service.get_task(task_id)
        if not task:
            return jsonify({"error": "Task not found", "success": False}), 404
        mcp_server = get_mcp_server()
        complete_result = mcp_server.call_tool(
            "tasks.complete",
            {"task_id": task_id},
            context={"source": "web.api"},
        )
        if not complete_result.get("ok"):
            return jsonify({"error": "Unable to complete task", "success": False}), 500
        if complete_result["result"].get("verified") is False:
            return jsonify({"error": "Task completion verification failed", "success": False}), 500
        return jsonify({"success": True, "task_id": task_id, "status": "done"})

    @app.route("/api/tasks/<int:task_id>/delete", methods=["POST"])
    def api_task_delete(task_id):
        """Permanently delete a task (does not complete it or create recurrence)."""
        task = task_service.get_task(task_id)
        if not task:
            return jsonify({"error": "Task not found", "success": False}), 404

        mcp_server = get_mcp_server()
        preview_result = mcp_server.call_tool(
            "tasks.preview_delete",
            {"task_id": task_id},
            context={"source": "web.api"},
        )
        if not preview_result.get("ok"):
            return jsonify({"error": "Unable to preview task delete", "success": False}), 500

        preview_payload = preview_result.get("result") or {}
        preview_id = preview_payload.get("preview_id")
        if not preview_id:
            return jsonify({"error": "Missing delete preview id", "success": False}), 500

        commit_result = mcp_server.call_tool(
            "tasks.commit_delete",
            {"preview_id": preview_id, "approved": True},
            context={"source": "web.api"},
        )
        if not commit_result.get("ok"):
            return jsonify({"error": "Unable to delete task", "success": False}), 500

        if task_service.get_task(task_id) is not None:
            return jsonify({"error": "Task delete verification failed", "success": False}), 500
        return jsonify({"success": True, "task_id": task_id, "deleted": True})
    
    @app.route("/api/tasks/<int:task_id>/update", methods=["POST"])
    def api_task_update(task_id):
        """Update task fields. Accepts JSON with any of: name, due_date, status, project_id, importance."""
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided", "success": False}), 400

        if not task_service.get_task(task_id):
            return jsonify({"error": "Task not found", "success": False}), 404

        tool_args = {"task_id": task_id}
        if 'name' in data:
            tool_args['name'] = data['name']
        if 'status' in data:
            tool_args['status'] = data['status']
        if 'project_id' in data:
            tool_args['project_id'] = data['project_id']
        if 'importance' in data:
            tool_args['importance'] = data['importance']
        if 'due_date' in data:
            try:
                from datetime import date as date_cls
                tool_args['due_date'] = date_cls.fromisoformat(data['due_date']).isoformat() if data['due_date'] else None
            except (ValueError, TypeError):
                pass

        if 'due_time' in data:
            try:
                from datetime import time as time_cls
                tool_args['due_time'] = time_cls.fromisoformat(data['due_time']).isoformat() if data['due_time'] else None
            except (ValueError, TypeError):
                pass
        if 'tags' in data:
            tool_args['tags'] = data.get('tags')
        if 'recurrence_rule' in data:
            tool_args['recurrence_rule'] = data.get('recurrence_rule')

        if len(tool_args) == 1:
            return jsonify({"error": "No valid update fields provided", "success": False}), 400

        mcp_server = get_mcp_server()
        update_result = mcp_server.call_tool(
            "tasks.update_fields",
            tool_args,
            context={"source": "web.api"},
        )
        if not update_result.get("ok"):
            return jsonify({"error": "Unable to update task", "success": False}), 500
        task_payload = update_result["result"].get("task")
        if not isinstance(task_payload, dict):
            return jsonify({"error": "Invalid task payload from MCP update", "success": False}), 500
        
        return jsonify({
            "success": True,
            "task": {
                "id": task_payload.get("id"),
                "name": task_payload.get("name"),
                "status": task_payload.get("status"),
                "due_date": task_payload.get("due_date"),
            },
        })
    
    @app.route("/api/tasks/<int:task_id>/reprocess", methods=["POST"])
    def api_task_reprocess(task_id):
        """Reprocess task text with NLP parser - only updates fields explicitly mentioned."""
        from ..parser.task_parser import parse_task
        
        data = request.get_json()
        if not data or not data.get('text', '').strip():
            return jsonify({"error": "Task text required", "success": False}), 400
        
        # Get existing task
        existing_task = task_service.get_task(task_id)
        if not existing_task:
            return jsonify({"error": "Task not found", "success": False}), 404
        
        # Parse new text
        parsed = parse_task(data['text'].strip())
        
        # Differential update: only update fields that are explicitly mentioned
        kwargs = {}
        
        # Always update name (task text)
        kwargs['name'] = parsed.name
        
        # Only update due_date if explicitly mentioned
        if parsed.due_date is not None:
            kwargs['due_date'] = parsed.due_date
        
        # Only update due_time if explicitly mentioned
        if parsed.due_time is not None:
            kwargs['due_time'] = parsed.due_time
        
        # Only update importance if explicitly mentioned
        if parsed.importance is not None:
            kwargs['importance'] = parsed.importance
        
        # Only update tags if explicitly mentioned (has tags in new text)
        if parsed.tags:
            kwargs['tags'] = parsed.tags
        
        # Only update project if explicitly mentioned
        if parsed.project_name is not None:
            # Look up project by name
            from ..services import project_service
            project = project_service.get_project_by_name(parsed.project_name)
            if project:
                kwargs['project_id'] = project.id
        
        # Update the task
        mcp_args = {"task_id": task_id}
        for key, value in kwargs.items():
            if key == "due_date":
                mcp_args[key] = value.isoformat() if value else None
            elif key == "due_time":
                mcp_args[key] = value.isoformat() if value else None
            else:
                mcp_args[key] = value
        mcp_server = get_mcp_server()
        update_result = mcp_server.call_tool(
            "tasks.update_fields",
            mcp_args,
            context={"source": "web.api"},
        )
        if not update_result.get("ok"):
            return jsonify({"error": "Unable to reprocess task text", "success": False}), 500
        updated_task = update_result["result"].get("task")
        if not isinstance(updated_task, dict):
            return jsonify({"error": "Invalid task payload from MCP reprocess update", "success": False}), 500
        
        return jsonify({
            "success": True,
            "task": {
                "id": updated_task.get("id"),
                "name": updated_task.get("name"),
                "due_date": updated_task.get("due_date"),
                "due_time": updated_task.get("due_time"),
                "importance": updated_task.get("importance"),
                "project_id": updated_task.get("project_id"),
                "status": updated_task.get("status"),
                "tags": updated_task.get("tags"),
            },
        })
    
    # =========================================================================
    # v0.9.1: Calendar View (Google Calendar-style weekly grid)
    # =========================================================================
    
    @app.route("/calendar/view")
    def calendar_view():
        """Calendar weekly view page — Google Calendar inspired."""
        saved_urls = get_saved_urls()
        return render_template("calendar_view.html", saved_urls=saved_urls)
    
    @app.route("/api/calendar/week")
    def api_calendar_week():
        """
        Get events for a specific week.
        Query param: date=YYYY-MM-DD (any day in the desired week).
        Returns events grouped by day, Mon-Sun.
        """
        from ..db import get_db
        
        date_str = request.args.get('date')
        if date_str:
            try:
                ref_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                ref_date = date.today()
        else:
            ref_date = date.today()
        
        # Find Monday of this week
        monday = ref_date - timedelta(days=ref_date.weekday())
        sunday = monday + timedelta(days=6)
        
        with get_db() as conn:
            events = conn.execute("""
                SELECT * FROM time_blocks
                WHERE date(start_time) >= ? AND date(start_time) <= ?
                ORDER BY start_time ASC
            """, (monday.isoformat(), sunday.isoformat())).fetchall()
        
        # Group by day
        days = []
        for i in range(7):
            day = monday + timedelta(days=i)
            day_events = []
            for e in events:
                start = e['start_time']
                if isinstance(start, str):
                    try:
                        start_dt = datetime.fromisoformat(start)
                    except ValueError:
                        continue
                else:
                    start_dt = start
                
                if start_dt.date() == day:
                    end = e['end_time']
                    if isinstance(end, str):
                        try:
                            end_dt = datetime.fromisoformat(end)
                        except ValueError:
                            end_dt = start_dt + timedelta(hours=1)
                    else:
                        end_dt = end or start_dt + timedelta(hours=1)
                    
                    # Detect all_day from column or heuristic
                    all_day = bool(e['all_day']) if 'all_day' in e.keys() else False
                    
                    day_events.append({
                        'id': e['id'],
                        'title': e['title'],
                        'start': start_dt.isoformat(),
                        'end': end_dt.isoformat(),
                        'start_hour': start_dt.hour + start_dt.minute / 60,
                        'end_hour': end_dt.hour + end_dt.minute / 60,
                        'source': e['source'],
                        'all_day': all_day,
                    })
            
            days.append({
                'date': day.isoformat(),
                'day_name': day.strftime('%a'),
                'is_today': day == date.today(),
                'events': day_events,
            })
        
        return jsonify({
            'week_start': monday.isoformat(),
            'week_end': sunday.isoformat(),
            'days': days,
        })
    
    # =========================================================================
    # v0.9.1: Task Upcoming View (Todoist-style rolling days)
    # =========================================================================
    
    @app.route("/tasks")
    def tasks_root_redirect():
        """Legacy route redirect to upcoming tasks."""
        return redirect(url_for("tasks_upcoming"))
    
    @app.route("/upcoming")
    def upcoming_redirect():
        """Legacy route redirect to upcoming tasks."""
        return redirect(url_for("tasks_upcoming"))
    
    @app.route("/projects")
    def projects_redirect():
        """Legacy route redirect to projects board."""
        return redirect(url_for("tasks_projects"))
    
    @app.route("/tasks/settings")
    @app.route("/task/settings")
    def tasks_settings_redirect():
        """Legacy route redirect for old task settings links."""
        return redirect(url_for("settings"))
    
    @app.route("/tasks/upcoming")
    def tasks_upcoming():
        """Task upcoming view — rolling few days + overdue."""
        return render_template("tasks_upcoming.html")
    
    @app.route("/api/tasks/upcoming")
    def api_tasks_upcoming():
        """Get tasks grouped by day for the next 5 days + overdue."""
        today = date.today()
        overdue = task_service.get_overdue_tasks()
        
        days = []
        for i in range(5):
            day = today + timedelta(days=i)
            day_tasks = task_service.get_tasks_due_on(day)
            
            # Sort by priority_score
            day_tasks.sort(key=lambda t: t.priority_score, reverse=True)
            
            tasks_data = []
            for t in day_tasks:
                project_name = None
                if t.project_id:
                    p = project_service.get_project(t.project_id)
                    project_name = p.name if p else None
                
                tasks_data.append({
                    'id': t.id,
                    'name': t.name,
                    'importance': t.importance,
                    'urgency': t.urgency,
                    'priority_score': t.priority_score,
                    'due_time': t.due_time.isoformat() if t.due_time else None,
                    'project_name': project_name,
                    'project_id': t.project_id,
                    'status': t.status,
                    'tags': t.tags,
                })
            
            days.append({
                'date': day.isoformat(),
                'day_name': day.strftime('%A'),
                'is_today': day == today,
                'tasks': tasks_data,
            })
        
        # Overdue tasks
        overdue_data = []
        for t in overdue:
            project_name = None
            if t.project_id:
                p = project_service.get_project(t.project_id)
                project_name = p.name if p else None
            overdue_data.append({
                'id': t.id,
                'name': t.name,
                'importance': t.importance,
                'due_date': t.due_date.isoformat() if t.due_date else None,
                'project_name': project_name,
                'priority_score': t.priority_score,
            })
        
        return jsonify({
            'overdue': overdue_data,
            'days': days,
        })
    
    @app.route("/api/tasks/no-due-date")
    def api_tasks_no_due_date():
        """Get tasks without a due date (unassigned)."""
        tasks = task_service.get_tasks_without_due_date()
        
        tasks_data = []
        for t in tasks:
            project_name = None
            if t.project_id:
                p = project_service.get_project(t.project_id)
                project_name = p.name if p else None
            
            created_at_value = None
            if t.created_at:
                created_at_value = t.created_at.isoformat() if hasattr(t.created_at, "isoformat") else str(t.created_at)
            
            tasks_data.append({
                'id': t.id,
                'name': t.name,
                'importance': t.importance,
                'priority_score': t.priority_score,
                'project_name': project_name,
                'project_id': t.project_id,
                'status': t.status,
                'tags': t.tags,
                'created_at': created_at_value,
            })
        
        return jsonify({'tasks': tasks_data})
    
    # =========================================================================
    # v0.9.1: Task Projects View (Kanban-style board)
    # =========================================================================
    
    @app.route("/tasks/projects")
    def tasks_projects():
        """Task projects board — columns per project, Notion-style side panel."""
        return render_template("tasks_projects.html")
    
    @app.route("/api/tasks/projects")
    def api_tasks_projects():
        """Get tasks grouped by project for the board view."""
        projects = project_service.get_all_projects()
        
        columns = []
        for proj in projects:
            tasks = task_service.get_project_tasks(proj.id)
            # Filter active tasks and sort by priority
            active_tasks = [t for t in tasks if t.status not in ('done', 'canceled')]
            active_tasks.sort(key=lambda t: t.priority_score, reverse=True)
            
            columns.append({
                'project_id': proj.id,
                'project_name': proj.name,
                'ai_summary': proj.next_action_suggestion,
                'tasks': [{
                    'id': t.id,
                    'name': t.name,
                    'importance': t.importance,
                    'urgency': t.urgency,
                    'priority_score': t.priority_score,
                    'due_date': t.due_date.isoformat() if t.due_date else None,
                    'due_time': t.due_time.isoformat() if t.due_time else None,
                    'status': t.status,
                    'tags': t.tags,
                    'computer_help_suggestion': t.computer_help_suggestion,
                } for t in active_tasks],
                'done_count': len([t for t in tasks if t.status == 'done']),
                'total_count': len(tasks),
            })
        
        # Inbox: tasks without a project
        inbox_tasks = task_service.get_inbox_tasks()
        inbox_active = [t for t in inbox_tasks if t.status not in ('done', 'canceled')]
        inbox_active.sort(key=lambda t: t.priority_score, reverse=True)
        
        inbox = {
            'project_name': 'Inbox',
            'project_id': None,
            'ai_summary': None,
            'tasks': [{
                'id': t.id,
                'name': t.name,
                'importance': t.importance,
                'urgency': t.urgency,
                'priority_score': t.priority_score,
                'due_date': t.due_date.isoformat() if t.due_date else None,
                'due_time': t.due_time.isoformat() if t.due_time else None,
                'status': t.status,
                'tags': t.tags,
                'computer_help_suggestion': t.computer_help_suggestion,
            } for t in inbox_active],
        }
        
        return jsonify({
            'columns': columns,
            'inbox': inbox,
        })
    
    # =========================================================================
    # v0.9.3: Legacy butler APIs removed
    # =========================================================================
    
    @app.route("/api/butler/status")
    def api_butler_status_removed():
        """Butler status API removed from active runtime in v0.9.3."""
        return jsonify({
            "success": False,
            "error": "Butler protocol removed from active runtime in v0.9.3",
        }), 410
    
    # =========================================================================
    # v0.9.3: Legacy skills UI/APIs removed
    # =========================================================================
    
    @app.route("/skills")
    def skills_page_removed():
        """Legacy skills page removed in v0.9.3."""
        flash("Skills UI has been removed from active runtime in v0.9.3.", "error")
        return redirect(url_for("settings"))
    
    @app.route("/api/skills", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    @app.route("/api/skills/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def api_skills_removed(path):
        """Skills APIs removed from active runtime in v0.9.3."""
        return jsonify({
            "success": False,
            "error": "Skills runtime removed from active backend in v0.9.3",
        }), 410
    
    # =========================================================================
    # Cor Unum: Live Music Ingestion Surface
    # =========================================================================

    @app.route("/cor-unum")
    def cor_unum():
        """Cor Unum — live music ingestion dashboard."""
        return render_template("cor_unum.html")

    @app.route("/cor-unum/duplicates")
    def cor_unum_duplicates():
        """Cor Unum duplicate review page."""
        return render_template("cor_unum_duplicates.html")

    @app.route("/cor-unum/db/events")
    def cor_unum_db_events():
        return render_template("cor_unum_db.html", table="events", title="Events")

    @app.route("/cor-unum/db/artists")
    def cor_unum_db_artists():
        return render_template("cor_unum_db.html", table="artists", title="Artists")

    @app.route("/cor-unum/db/venues")
    def cor_unum_db_venues():
        return render_template("cor_unum_db.html", table="venues", title="Venues")

    @app.route("/cor-unum/db/event-sources")
    def cor_unum_db_event_sources():
        return render_template("cor_unum_db.html", table="event-sources", title="Event Sources")

    @app.route("/cor-unum/db/source-registry")
    def cor_unum_db_source_registry():
        return render_template("cor_unum_db.html", table="source-registry", title="Source Registry")
    def _cu_session_payload(user: User | None = None) -> dict:
        current = user or _get_current_cu_user()
        capabilities = _cu_assume_capabilities(current)
        return {
            "user_id": current.user_id,
            "username": current.username,
            "role": current.role,
            "member_id": current.member_id,
            "artist_id": current.artist_id,
            "is_admin": current.is_admin,
            "is_member": current.is_member,
            "can_mutate": current.is_member,
            "is_local_request": capabilities["is_local_request"],
            "can_assume_admin": capabilities["can_assume_admin"],
            "can_assume_member": capabilities["can_assume_member"],
        }

    def _parse_suggestion_payload(raw_payload: str | None) -> dict:
        if not raw_payload:
            return {}
        try:
            value = json.loads(raw_payload)
            if isinstance(value, dict):
                return value
            return {"value": value}
        except Exception:
            return {"message": str(raw_payload)}

    def _serialize_cu_suggestion(row) -> dict:
        payload = _parse_suggestion_payload(row["payload_json"])
        return {
            "id": row["id"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "status": row["status"],
            "submitted_at": row["submitted_at"],
            "submitted_by": row["submitted_by"],
            "submitted_role": row["submitted_role"],
            "resolved_at": row["resolved_at"],
            "resolved_by": row["resolved_by"],
            "decision_notes": row["decision_notes"],
            "applied_event_id": row["applied_event_id"],
            "payload": payload,
        }

    def _list_cu_suggestions(
        *,
        status: str | None = "pending",
        entity_type: str | None = None,
        entity_id: int | None = None,
        limit: int = 200,
    ) -> list[dict]:
        clauses: list[str] = []
        params: list = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if entity_type:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if entity_id is not None:
            clauses.append("entity_id = ?")
            params.append(int(entity_id))
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        bounded_limit = max(1, min(int(limit), 500))
        with get_db() as conn:
            rows = conn.execute(
                f"""SELECT *
                    FROM cu_suggestions
                    {where_sql}
                    ORDER BY submitted_at DESC, id DESC
                    LIMIT ?""",
                tuple(params + [bounded_limit]),
            ).fetchall()
        return [_serialize_cu_suggestion(row) for row in rows]

    def _coerce_bool(value) -> int:
        if isinstance(value, bool):
            return 1 if value else 0
        text = str(value or "").strip().lower()
        return 1 if text in {"1", "true", "yes", "on"} else 0

    @app.route("/api/cor-unum/session")
    def api_cu_session():
        return jsonify({"success": True, "session": _cu_session_payload()})

    @app.route("/api/cor-unum/session/assume", methods=["POST"])
    def api_cu_assume_session():
        data = request.get_json(silent=True) or {}
        role = str(data.get("role") or "").strip().lower()
        current = _get_current_cu_user()
        capabilities = _cu_assume_capabilities(current)
        if role not in {"admin", "member", "public"}:
            return jsonify({"success": False, "error": "role must be admin, member, or public"}), 400
        if role == "admin":
            if not capabilities["can_assume_admin"]:
                return jsonify({"success": False, "error": "Admin role assumption not allowed"}), 403
            _set_cu_session_role(role="admin", username="cor_unum_admin", user_id=1, member_id=None)
            return jsonify({"success": True, "session": _cu_session_payload()})
        if role == "public":
            _set_cu_session_role(role="public", username="public", user_id=0, member_id=None)
            return jsonify({"success": True, "session": _cu_session_payload()})
        if not capabilities["can_assume_member"]:
            return jsonify({"success": False, "error": "Member role assumption not allowed"}), 403
        member_id = data.get("member_id")
        username = str(data.get("username") or data.get("member_username") or "").strip()
        if member_id is None and not username:
            return jsonify({"success": False, "error": "member_id or username required for member role"}), 400
        claim_requested = member_id is None and bool(username)
        with get_db() as conn:
            member = None
            if member_id is not None:
                try:
                    lookup_member_id = int(member_id)
                except (TypeError, ValueError):
                    return jsonify({"success": False, "error": "member_id must be an integer"}), 400
                member = conn.execute(
                    """SELECT id, username, artist_id, claimed_at
                       FROM cu_members
                       WHERE id = ? AND is_active = 1""",
                    (lookup_member_id,),
                ).fetchone()
            elif username:
                member = conn.execute(
                    """SELECT id, username, artist_id, claimed_at
                       FROM cu_members
                       WHERE LOWER(username) = LOWER(?) AND is_active = 1""",
                    (username,),
                ).fetchone()
            if member and claim_requested and not member["claimed_at"]:
                now = datetime.utcnow().isoformat()
                conn.execute(
                    "UPDATE cu_members SET claimed_at = ? WHERE id = ? AND claimed_at IS NULL",
                    (now, int(member["id"])),
                )
                member = conn.execute(
                    """SELECT id, username, artist_id, claimed_at
                       FROM cu_members
                       WHERE id = ? AND is_active = 1""",
                    (int(member["id"]),),
                ).fetchone()
        if not member:
            return jsonify({"success": False, "error": "Active member not found"}), 404
        _set_cu_session_role(
            role="member",
            username=str(member["username"]),
            user_id=10_000 + int(member["id"]),
            member_id=int(member["id"]),
        )
        return jsonify({"success": True, "session": _cu_session_payload()})

    @app.route("/api/cor-unum/members", methods=["GET"])
    def api_cu_members():
        admin_error = _require_cu_admin()
        if admin_error:
            return admin_error
        with get_db() as conn:
            rows = conn.execute(
                """SELECT m.id, m.username, m.display_name, m.artist_id, m.role, m.is_active, m.created_by, m.created_at, m.claimed_at,
                          a.name AS artist_name
                   FROM cu_members m
                   LEFT JOIN cu_artists a ON a.id = m.artist_id
                   ORDER BY m.id DESC"""
            ).fetchall()
        return jsonify({"success": True, "members": [dict(r) for r in rows]})

    @app.route("/api/cor-unum/members", methods=["POST"])
    def api_cu_create_member():
        admin_error = _require_cu_admin()
        if admin_error:
            return admin_error
        from ..ingestion.history import record_entity_change
        data = request.get_json(silent=True) or {}
        username = str(data.get("username") or "").strip()
        if not username:
            return jsonify({"success": False, "error": "username required"}), 400
        display_name = str(data.get("display_name") or "").strip() or username
        artist_id = data.get("artist_id")
        artist_name = str(data.get("artist_name") or "").strip()
        actor = _cu_actor_label()
        with get_db() as conn:
            existing_username = conn.execute(
                "SELECT id FROM cu_members WHERE LOWER(username) = LOWER(?) LIMIT 1",
                (username,),
            ).fetchone()
            if existing_username:
                return jsonify({"success": False, "error": "username already exists"}), 409
            canonical_artist_id = None
            if artist_id is not None:
                try:
                    lookup_artist_id = int(artist_id)
                except (TypeError, ValueError):
                    return jsonify({"success": False, "error": "artist_id must be an integer"}), 400
                row = conn.execute(
                    "SELECT id, alias_of FROM cu_artists WHERE id = ?",
                    (lookup_artist_id,),
                ).fetchone()
                if not row:
                    return jsonify({"success": False, "error": "artist not found"}), 404
                canonical_artist_id = int(row["alias_of"] or row["id"])
            elif artist_name:
                row = conn.execute(
                    "SELECT id, alias_of FROM cu_artists WHERE LOWER(name) = LOWER(?) ORDER BY id ASC LIMIT 1",
                    (artist_name,),
                ).fetchone()
                if row:
                    canonical_artist_id = int(row["alias_of"] or row["id"])
                else:
                    created = conn.execute(
                        "INSERT INTO cu_artists (name, last_seen) VALUES (?, ?)",
                        (artist_name, datetime.utcnow().isoformat()),
                    )
                    canonical_artist_id = int(created.lastrowid)
                    record_entity_change(
                        conn,
                        entity_type="artist",
                        entity_id=canonical_artist_id,
                        operation="cor_unum.artist.create",
                        summary=f"Artist created for member {username}",
                        actor=actor,
                        details={"username": username},
                    )
            if canonical_artist_id is not None:
                active_member = conn.execute(
                    """SELECT id, username
                       FROM cu_members
                       WHERE artist_id = ? AND is_active = 1
                       ORDER BY id DESC
                       LIMIT 1""",
                    (canonical_artist_id,),
                ).fetchone()
                if active_member:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "artist already has an active member",
                                "member": {"id": int(active_member["id"]), "username": str(active_member["username"])},
                            }
                        ),
                        409,
                    )
            created_member = conn.execute(
                """INSERT INTO cu_members (username, display_name, artist_id, role, is_active, created_by)
                   VALUES (?, ?, ?, 'member', 1, ?)""",
                (username, display_name, canonical_artist_id, actor),
            )
            member_id = int(created_member.lastrowid)
            if canonical_artist_id is not None:
                record_entity_change(
                    conn,
                    entity_type="artist",
                    entity_id=canonical_artist_id,
                    operation="cor_unum.member.link",
                    summary=f"Linked member {username} to artist",
                    actor=actor,
                    details={"member_id": member_id, "username": username},
                )
            member = conn.execute(
                """SELECT m.id, m.username, m.display_name, m.artist_id, m.role, m.is_active, m.created_by, m.created_at, m.claimed_at,
                          a.name AS artist_name
                   FROM cu_members m
                   LEFT JOIN cu_artists a ON a.id = m.artist_id
                   WHERE m.id = ?""",
                (member_id,),
            ).fetchone()
        return jsonify({"success": True, "member": dict(member)})

    @app.route("/api/cor-unum/suggestions", methods=["GET"])
    def api_cu_list_suggestions():
        status = (request.args.get("status") or "pending").strip().lower() or None
        entity_type = (request.args.get("entity_type") or "").strip().lower() or None
        entity_id = request.args.get("entity_id", type=int)
        limit = max(1, min(request.args.get("limit", 200, type=int), 500))
        current = _get_current_cu_user()
        if not current.is_member and (status not in {None, "pending"}):
            return jsonify({"success": False, "error": "Public view only supports pending suggestions"}), 403
        return jsonify(
            {
                "success": True,
                "suggestions": _list_cu_suggestions(
                    status=status,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    limit=limit,
                ),
            }
        )

    @app.route("/api/cor-unum/suggestions", methods=["POST"])
    def api_cu_submit_suggestion():
        data = request.get_json(silent=True) or {}
        entity_type = str(data.get("entity_type") or "").strip().lower()
        if entity_type not in {"event", "artist"}:
            return jsonify({"success": False, "error": "entity_type must be event or artist"}), 400
        entity_id = data.get("entity_id")
        payload = data.get("payload")
        if entity_id is None or not isinstance(payload, dict) or not payload:
            return jsonify({"success": False, "error": "entity_id and payload object required"}), 400
        current = _get_current_cu_user()
        now = datetime.utcnow().isoformat()
        payload_json = json.dumps(payload, ensure_ascii=False)
        with get_db() as conn:
            exists = conn.execute(
                f"SELECT id FROM cu_{entity_type}s WHERE id = ?",
                (int(entity_id),),
            ).fetchone()
            if not exists:
                return jsonify({"success": False, "error": f"{entity_type} not found"}), 404
            created = conn.execute(
                """INSERT INTO cu_suggestions
                   (entity_type, entity_id, payload_json, status, submitted_by, submitted_role, submitted_at)
                   VALUES (?, ?, ?, 'pending', ?, ?, ?)""",
                (
                    entity_type,
                    int(entity_id),
                    payload_json,
                    current.username,
                    current.role,
                    now,
                ),
            )
            suggestion_id = int(created.lastrowid)
            row = conn.execute("SELECT * FROM cu_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        return jsonify({"success": True, "suggestion": _serialize_cu_suggestion(row)})

    @app.route("/api/cor-unum/suggestions/<int:suggestion_id>/resolve", methods=["POST"])
    def api_cu_resolve_suggestion(suggestion_id: int):
        admin_error = _require_cu_admin()
        if admin_error:
            return admin_error
        from ..ingestion.history import record_entity_change
        data = request.get_json(silent=True) or {}
        decision = str(data.get("decision") or "").strip().lower()
        if decision not in {"accept", "reject"}:
            return jsonify({"success": False, "error": "decision must be accept or reject"}), 400
        notes = str(data.get("notes") or "").strip()
        actor = _cu_actor_label()
        with get_db() as conn:
            row = conn.execute(
                """SELECT id, entity_type, entity_id, payload_json, status
                   FROM cu_suggestions
                   WHERE id = ?""",
                (suggestion_id,),
            ).fetchone()
            if not row:
                return jsonify({"success": False, "error": "Suggestion not found"}), 404
            if row["status"] != "pending":
                return jsonify({"success": False, "error": "Suggestion already resolved"}), 409
            payload = _parse_suggestion_payload(row["payload_json"])
            now = datetime.utcnow().isoformat()
            applied_event_id = None
            if decision == "accept":
                assignments: list[str] = []
                values: list = []
                allowed_fields = {
                    "event": {"title", "date", "description"},
                    "artist": {"name", "soundcloud_url", "instagram_url", "spotify_url", "is_canadian"},
                }
                for field, value in payload.items():
                    if field not in allowed_fields[row["entity_type"]]:
                        continue
                    if field == "is_canadian":
                        assignments.append(f"{field} = ?")
                        values.append(_coerce_bool(value))
                    else:
                        assignments.append(f"{field} = ?")
                        values.append(str(value).strip())
                if assignments:
                    values.append(int(row["entity_id"]))
                    conn.execute(
                        f"UPDATE cu_{row['entity_type']}s SET {', '.join(assignments)} WHERE id = ?",
                        tuple(values),
                    )
                event = record_entity_change(
                    conn,
                    entity_type=row["entity_type"],
                    entity_id=int(row["entity_id"]),
                    operation="cor_unum.suggestion.accepted",
                    summary=f"Suggestion #{suggestion_id} accepted",
                    actor=actor,
                    details={"payload": payload, "notes": notes},
                )
                applied_event_id = (event or {}).get("event_id")
            else:
                record_entity_change(
                    conn,
                    entity_type=row["entity_type"],
                    entity_id=int(row["entity_id"]),
                    operation="cor_unum.suggestion.rejected",
                    summary=f"Suggestion #{suggestion_id} rejected",
                    actor=actor,
                    details={"payload": payload, "notes": notes},
                )
            conn.execute(
                """UPDATE cu_suggestions
                   SET status = ?, resolved_at = ?, resolved_by = ?, decision_notes = ?, applied_event_id = ?
                   WHERE id = ?""",
                (
                    "accepted" if decision == "accept" else "rejected",
                    now,
                    actor,
                    notes,
                    applied_event_id,
                    suggestion_id,
                ),
            )
            resolved = conn.execute("SELECT * FROM cu_suggestions WHERE id = ?", (suggestion_id,)).fetchone()
        return jsonify({"success": True, "suggestion": _serialize_cu_suggestion(resolved)})

    @app.route("/api/cor-unum/history/<entity_type>/<int:entity_id>")
    def api_cu_history(entity_type: str, entity_id: int):
        if entity_type not in {"event", "artist", "venue", "event_source"}:
            return jsonify({"success": False, "error": "Unsupported entity type"}), 400
        limit = max(1, min(request.args.get("limit", 50, type=int), 200))
        from ..ingestion.history import list_entity_history
        with get_db() as conn:
            rows = list_entity_history(
                conn,
                entity_type=entity_type,
                entity_id=entity_id,
                limit=limit,
            )
        history = [
            {
                "id": row.get("event_id") or row.get("version_id"),
                "operation": row.get("operation"),
                "summary": row.get("summary"),
                "actor": row.get("created_by"),
                "details": row.get("details") or {},
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]
        return jsonify({"success": True, "history": history})

    @app.route("/api/cor-unum/artists/<int:artist_id>/expand-member", methods=["POST"])
    def api_cu_expand_member_from_artist(artist_id: int):
        admin_error = _require_cu_admin()
        if admin_error:
            return admin_error
        data = request.get_json(silent=True) or {}
        username = str(data.get("username") or "").strip()
        if not username:
            return jsonify({"success": False, "error": "username required"}), 400
        payload = {
            "username": username,
            "display_name": str(data.get("display_name") or "").strip() or username,
            "artist_id": artist_id,
        }
        from ..ingestion.history import record_entity_change
        actor = _cu_actor_label()
        with get_db() as conn:
            existing_username = conn.execute(
                "SELECT id FROM cu_members WHERE LOWER(username) = LOWER(?) LIMIT 1",
                (username,),
            ).fetchone()
            if existing_username:
                return jsonify({"success": False, "error": "username already exists"}), 409
            row = conn.execute(
                "SELECT id, alias_of, name FROM cu_artists WHERE id = ?",
                (artist_id,),
            ).fetchone()
            if not row:
                return jsonify({"success": False, "error": "artist not found"}), 404
            canonical_artist_id = int(row["alias_of"] or row["id"])
            active_member = conn.execute(
                """SELECT id, username
                   FROM cu_members
                   WHERE artist_id = ? AND is_active = 1
                   ORDER BY id DESC
                   LIMIT 1""",
                (canonical_artist_id,),
            ).fetchone()
            if active_member:
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "artist already has an active member",
                            "member": {"id": int(active_member["id"]), "username": str(active_member["username"])},
                        }
                    ),
                    409,
                )
            created = conn.execute(
                """INSERT INTO cu_members (username, display_name, artist_id, role, is_active, created_by)
                   VALUES (?, ?, ?, 'member', 1, ?)""",
                (username, payload["display_name"], canonical_artist_id, actor),
            )
            member_id = int(created.lastrowid)
            record_entity_change(
                conn,
                entity_type="artist",
                entity_id=canonical_artist_id,
                operation="cor_unum.member.link",
                summary=f"Linked member {username} to artist {row['name']}",
                actor=actor,
                details={"member_id": member_id, "username": username},
            )
            member = conn.execute(
                """SELECT m.id, m.username, m.display_name, m.artist_id, m.role, m.is_active, m.created_by, m.created_at, m.claimed_at,
                          a.name AS artist_name
                   FROM cu_members m
                   LEFT JOIN cu_artists a ON a.id = m.artist_id
                   WHERE m.id = ?""",
                (member_id,),
            ).fetchone()
        return jsonify({"success": True, "member": dict(member)})

    # --- Cor Unum API endpoints ---

    @app.route("/api/cor-unum/sources")
    def api_cu_sources():
        from ..ingestion.service import get_source_registry
        return jsonify({"success": True, "sources": get_source_registry()})

    @app.route("/api/cor-unum/sources/<source_key>/refresh", methods=["POST"])
    def api_cu_refresh_source(source_key):
        from ..ingestion.service import refresh_source
        result = refresh_source(source_key)
        return jsonify({"success": result.get("status") != "error", "result": result})

    @app.route("/api/cor-unum/sources/refresh-all", methods=["POST"])
    def api_cu_refresh_all():
        from ..ingestion.service import refresh_all_sources
        result = refresh_all_sources()
        return jsonify({"success": True, "result": result})

    @app.route("/api/cor-unum/sources/run-all/<scanner_class>", methods=["POST"])
    def api_cu_refresh_by_class(scanner_class):
        from ..ingestion.service import refresh_sources_by_class
        if scanner_class not in {"event", "fingerprint", "internal"}:
            return jsonify({"success": False, "error": "Invalid scanner class"}), 400
        result = refresh_sources_by_class(scanner_class)
        return jsonify({"success": True, "result": result})

    @app.route("/api/cor-unum/sources/<source_key>/enabled", methods=["PATCH"])
    def api_cu_set_enabled(source_key):
        from ..ingestion.service import set_source_enabled
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("enabled", True))
        updated = set_source_enabled(source_key, enabled)
        if not updated:
            return jsonify({"success": False, "error": "Source not found"}), 404
        return jsonify({"success": True, "source": updated})

    @app.route("/api/cor-unum/sources/<source_key>/clear-error", methods=["PATCH"])
    def api_cu_clear_error(source_key):
        from ..ingestion.service import clear_source_error
        updated = clear_source_error(source_key)
        if not updated:
            return jsonify({"success": False, "error": "Source not found"}), 404
        return jsonify({"success": True, "source": updated})

    @app.route("/api/cor-unum/runs")
    def api_cu_runs():
        from ..ingestion.service import get_run_summary
        source_key = (request.args.get("source_key") or "").strip() or None
        limit = max(1, min(request.args.get("limit", 20, type=int), 200))
        runs = get_run_summary(source_key=source_key, limit=limit)
        return jsonify({"success": True, "runs": runs})

    @app.route("/api/cor-unum/events")
    def api_cu_events():
        from ..ingestion.service import get_events
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)
        search = (request.args.get("search") or "").strip()
        return jsonify({"success": True, **get_events(page, per_page, search)})

    @app.route("/api/cor-unum/artists")
    def api_cu_artists():
        from ..ingestion.service import get_artists
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)
        search = (request.args.get("search") or "").strip()
        local = (request.args.get("local") or "").strip()
        return jsonify({"success": True, **get_artists(page, per_page, search, local)})

    @app.route("/api/cor-unum/venues")
    def api_cu_venues():
        from ..ingestion.service import get_venues
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)
        search = (request.args.get("search") or "").strip()
        return jsonify({"success": True, **get_venues(page, per_page, search)})

    @app.route("/api/cor-unum/event-sources")
    def api_cu_event_sources():
        from ..ingestion.service import get_event_sources
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)
        return jsonify({"success": True, **get_event_sources(page, per_page)})

    @app.route("/api/cor-unum/source-registry")
    def api_cu_source_registry():
        from ..ingestion.service import get_source_registry_page
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 50, type=int)
        return jsonify({"success": True, **get_source_registry_page(page, per_page)})

    @app.route("/api/cor-unum/duplicates")
    def api_cu_duplicates():
        from ..ingestion.service import get_duplicate_candidates
        payload = get_duplicate_candidates()
        payload["pending_suggestions"] = _list_cu_suggestions(status="pending", limit=100)
        return jsonify({"success": True, **payload})

    @app.route("/api/cor-unum/duplicates/rescan", methods=["POST"])
    def api_cu_duplicates_rescan():
        admin_error = _require_cu_admin()
        if admin_error:
            return admin_error
        from ..ingestion.service import rescan_duplicate_candidates
        data = request.get_json(silent=True) or {}
        kind = (data.get("kind") or request.args.get("kind") or "all").strip().lower()
        return jsonify({"success": True, "result": rescan_duplicate_candidates(kind)})

    @app.route("/api/cor-unum/duplicates/ignore", methods=["POST"])
    def api_cu_duplicates_ignore():
        admin_error = _require_cu_admin()
        if admin_error:
            return admin_error
        from ..ingestion.service import ignore_duplicate_candidate
        data = request.get_json(silent=True) or {}
        entity_type = (data.get("entity_type") or "").strip().lower()
        source_key = (data.get("source_key") or "").strip()
        left_id = data.get("left_id")
        right_id = data.get("right_id")
        if not entity_type or not source_key or left_id is None or right_id is None:
            return jsonify({"success": False, "error": "entity_type, source_key, left_id, right_id required"}), 400
        result = ignore_duplicate_candidate(entity_type, source_key, int(left_id), int(right_id))
        if result.get("error"):
            return jsonify({"success": False, "error": result["error"]}), 400
        return jsonify({"success": True, **result})

    @app.route("/api/cor-unum/duplicates/merge", methods=["POST"])
    def api_cu_duplicates_merge():
        admin_error = _require_cu_admin()
        if admin_error:
            return admin_error
        from ..ingestion.service import merge_artists, merge_events
        data = request.get_json(silent=True) or {}
        entity_type = (data.get("entity_type") or "").strip().lower()
        duplicate_id = data.get("duplicate_id")
        canonical_id = data.get("canonical_id")
        if entity_type not in {"artist", "event"}:
            return jsonify({"success": False, "error": "entity_type must be artist or event"}), 400
        if duplicate_id is None or canonical_id is None:
            return jsonify({"success": False, "error": "duplicate_id and canonical_id required"}), 400
        if entity_type == "artist":
            result = merge_artists(int(duplicate_id), int(canonical_id))
        else:
            result = merge_events(int(duplicate_id), int(canonical_id))
        if result.get("error"):
            return jsonify({"success": False, "error": result["error"]}), 400
        return jsonify({"success": True, **result})

    # --- Cor Unum: browse pages ---
    @app.route("/cor-unum/add-artist")
    def cor_unum_add_artist():
        """Manual artist creation page (admin only)."""
        current = _get_current_cu_user()
        if not current.is_admin:
            return redirect(url_for("cor_unum"))
        return render_template("cor_unum_add_artist.html")

    @app.route("/cor-unum/add-event")
    def cor_unum_add_event():
        """Manual event creation page."""
        return render_template("cor_unum_add_event.html")
    @app.route("/api/cor-unum/artists/create", methods=["POST"])
    def api_cu_create_artist():
        admin_error = _require_cu_admin()
        if admin_error:
            return admin_error
        from ..ingestion.city_tags import LOCAL_CITY_TAG, set_local_yvr
        from ..ingestion.history import record_entity_change
        data = request.get_json(silent=True) or {}
        name = str(data.get("name") or "").strip()
        if not name:
            return jsonify({"success": False, "error": "name required"}), 400
        soundcloud_url = str(data.get("soundcloud_url") or "").strip() or None
        instagram_url = str(data.get("instagram_url") or "").strip() or None
        spotify_url = str(data.get("spotify_url") or "").strip() or None
        is_canadian = _coerce_bool(data.get("is_canadian"))
        is_local = bool(data.get("is_local"))
        actor = _cu_actor_label()
        now = datetime.utcnow().isoformat()
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id, alias_of FROM cu_artists WHERE LOWER(name) = LOWER(?) ORDER BY id ASC LIMIT 1",
                (name,),
            ).fetchone()
            if existing:
                existing_id = int(existing["alias_of"] or existing["id"])
                return (
                    jsonify(
                        {
                            "success": False,
                            "error": "artist already exists",
                            "artist_id": existing_id,
                        }
                    ),
                    409,
                )
            created = conn.execute(
                """INSERT INTO cu_artists (name, soundcloud_url, instagram_url, spotify_url, is_canadian, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (name, soundcloud_url, instagram_url, spotify_url, int(is_canadian), now),
            )
            artist_id = int(created.lastrowid)
            if is_local:
                set_local_yvr(conn, artist_id, True)
            record_entity_change(
                conn,
                entity_type="artist",
                entity_id=artist_id,
                operation="cor_unum.artist.create",
                summary=f"Created artist '{name}'",
                actor=actor,
                details={
                    "is_local": is_local,
                    "is_canadian": bool(is_canadian),
                    "source": "manual_dashboard",
                },
            )
            artist = conn.execute(
                """SELECT a.id, a.name, a.soundcloud_url, a.instagram_url, a.spotify_url, a.is_canadian,
                          EXISTS (
                              SELECT 1
                              FROM cu_artist_tags t
                              WHERE t.artist_id = a.id AND t.tag = ?
                          ) AS is_local
                   FROM cu_artists a
                   WHERE a.id = ?""",
                (LOCAL_CITY_TAG, artist_id),
            ).fetchone()
        return jsonify({"success": True, "artist": dict(artist)})

    @app.route("/api/cor-unum/events/create", methods=["POST"])
    def api_cu_create_event():
        member_error = _require_cu_member_or_admin()
        if member_error:
            return member_error
        from ..ingestion.city_tags import LOCAL_CITY_TAG
        from ..ingestion.history import record_entity_change
        from ..ingestion.models import FALLBACK_VENUE_NAME
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        date_str = (data.get("date") or "").strip()
        if not title or not date_str:
            return jsonify({"success": False, "error": "Title and date required"}), 400

        venue_id = data.get("venue_id")
        venue_name = (data.get("venue_name") or "").strip()
        description = (data.get("description") or "").strip()
        artist_list = data.get("artists") or []
        current_user = _get_current_cu_user()
        actor = _cu_actor_label()

        with get_db() as conn:
            member_artist_id = None
            if current_user.role == "member":
                if current_user.artist_id is None:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Member account must be linked to an artist before creating events",
                            }
                        ),
                        409,
                    )
                member_artist_row = conn.execute(
                    "SELECT id, alias_of FROM cu_artists WHERE id = ?",
                    (int(current_user.artist_id),),
                ).fetchone()
                if not member_artist_row:
                    return (
                        jsonify(
                            {
                                "success": False,
                                "error": "Linked artist not found for member account",
                            }
                        ),
                        409,
                    )
                member_artist_id = int(member_artist_row["alias_of"] or member_artist_row["id"])
            # Resolve or create venue
            if venue_id:
                pass  # use existing
            elif venue_name:
                row = conn.execute("SELECT id, alias_of FROM cu_venues WHERE name = ?", (venue_name,)).fetchone()
                if row:
                    venue_id = row["alias_of"] or row["id"]
                else:
                    cur = conn.execute("INSERT INTO cu_venues (name) VALUES (?)", (venue_name,))
                    venue_id = cur.lastrowid
            else:
                row = conn.execute("SELECT id FROM cu_venues WHERE name = ?", (FALLBACK_VENUE_NAME,)).fetchone()
                venue_id = row["id"] if row else None

            # Create event
            cur = conn.execute(
                "INSERT INTO cu_events (title, date, venue_id, description) VALUES (?, ?, ?, ?)",
                (title, date_str, venue_id, description[:2000] if description else ""),
            )
            event_id = cur.lastrowid

            # Create source record (manual)
            conn.execute(
                """INSERT INTO cu_event_sources
                   (event_id, source_type, source_url, source_fingerprint, captured_at)
                   VALUES (?, 'manual', '', 'manual_' || ?, ?)""",
                (event_id, str(event_id), datetime.utcnow().isoformat()),
            )

            # Process artists
            canonical_artist_ids: set[int] = set()
            for art in artist_list:
                art_name = (art.get("name") or "").strip()
                if not art_name:
                    continue
                art_id = art.get("id")
                if art_id and not art.get("is_new"):
                    # Existing artist — resolve alias
                    row = conn.execute("SELECT id, alias_of FROM cu_artists WHERE id = ?", (art_id,)).fetchone()
                    if row:
                        art_id = row["alias_of"] or row["id"]
                else:
                    # New or unresolved — get-or-create
                    row = conn.execute("SELECT id, alias_of FROM cu_artists WHERE name = ?", (art_name,)).fetchone()
                    if row:
                        art_id = row["alias_of"] or row["id"]
                    else:
                        cur2 = conn.execute(
                            "INSERT INTO cu_artists (name, last_seen) VALUES (?, ?)",
                            (art_name, datetime.utcnow().isoformat()),
                        )
                        art_id = cur2.lastrowid
                        record_entity_change(
                            conn,
                            entity_type="artist",
                            entity_id=int(art_id),
                            operation="cor_unum.artist.create",
                            summary=f"Artist created while adding event {title}",
                            actor=actor,
                            details={"event_id": int(event_id)},
                        )
                        if art.get("is_local"):
                            conn.execute(
                                "INSERT OR IGNORE INTO cu_artist_tags (artist_id, tag) VALUES (?, ?)",
                                (art_id, LOCAL_CITY_TAG),
                            )
                canonical_artist_ids.add(int(art_id))
                conn.execute(
                    "INSERT OR IGNORE INTO cu_event_performers (event_id, artist_id) VALUES (?, ?)",
                    (event_id, art_id),
                )
            auto_added_member_artist = False
            if member_artist_id is not None and member_artist_id not in canonical_artist_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO cu_event_performers (event_id, artist_id) VALUES (?, ?)",
                    (event_id, member_artist_id),
                )
                canonical_artist_ids.add(member_artist_id)
                auto_added_member_artist = True
            record_entity_change(
                conn,
                entity_type="event",
                entity_id=int(event_id),
                operation="cor_unum.event.create",
                summary=f"Created event '{title}'",
                actor=actor,
                details={
                    "date": date_str,
                    "venue_id": int(venue_id) if venue_id else None,
                    "artist_count": len(canonical_artist_ids),
                    "member_artist_enforced": auto_added_member_artist,
                },
            )

        return jsonify({"success": True, "event_id": event_id})

    @app.route("/cor-unum/upcoming")
    def cor_unum_upcoming():
        """Upcoming events view — RA-style date-grouped listing."""
        return render_template("cor_unum_upcoming.html")

    @app.route("/cor-unum/event/<int:event_id>")
    def cor_unum_event(event_id):
        """Single event detail page."""
        return render_template("cor_unum_event.html", event_id=event_id)

    @app.route("/cor-unum/artist/<int:artist_id>")
    def cor_unum_artist(artist_id):
        """Artist page — lists their events."""
        return render_template("cor_unum_artist.html", artist_id=artist_id)

    @app.route("/cor-unum/venue/<int:venue_id>")
    def cor_unum_venue(venue_id):
        """Venue page — lists events at this venue."""
        return render_template("cor_unum_venue.html", venue_id=venue_id)

    @app.route("/api/cor-unum/upcoming")
    def api_cu_upcoming():
        from ..ingestion.service import get_upcoming_events
        limit = max(1, min(request.args.get("limit", 200, type=int), 500))
        locality = (request.args.get("locality") or "all").strip().lower()
        return jsonify({"success": True, "events": get_upcoming_events(limit=limit, locality=locality)})

    @app.route("/api/cor-unum/events/<int:event_id>")
    def api_cu_event_detail(event_id):
        from ..ingestion.service import get_event_detail
        from ..ingestion.history import list_entity_history
        ev = get_event_detail(event_id)
        if not ev:
            return jsonify({"success": False, "error": "Event not found"}), 404
        with get_db() as conn:
            rows = list_entity_history(conn, entity_type="event", entity_id=event_id, limit=50)
        history = [
            {
                "id": row.get("event_id") or row.get("version_id"),
                "operation": row.get("operation"),
                "summary": row.get("summary"),
                "actor": row.get("created_by"),
                "details": row.get("details") or {},
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]
        suggestions = _list_cu_suggestions(status=None, entity_type="event", entity_id=event_id, limit=100)
        return jsonify({"success": True, "event": ev, "history": history, "suggestions": suggestions})

    @app.route("/api/cor-unum/artists/<int:artist_id>")
    def api_cu_artist_detail(artist_id):
        from ..ingestion.service import get_artist_detail
        from ..ingestion.history import list_entity_history
        artist = get_artist_detail(artist_id)
        if not artist:
            return jsonify({"success": False, "error": "Artist not found"}), 404
        with get_db() as conn:
            rows = list_entity_history(conn, entity_type="artist", entity_id=artist_id, limit=50)
        history = [
            {
                "id": row.get("event_id") or row.get("version_id"),
                "operation": row.get("operation"),
                "summary": row.get("summary"),
                "actor": row.get("created_by"),
                "details": row.get("details") or {},
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]
        suggestions = _list_cu_suggestions(status=None, entity_type="artist", entity_id=artist_id, limit=100)
        return jsonify({"success": True, "artist": artist, "history": history, "suggestions": suggestions})

    @app.route("/api/cor-unum/venues/<int:venue_id>")
    def api_cu_venue_detail(venue_id):
        from ..ingestion.service import get_venue_detail
        from ..ingestion.history import list_entity_history
        venue = get_venue_detail(venue_id)
        if not venue:
            return jsonify({"success": False, "error": "Venue not found"}), 404
        with get_db() as conn:
            rows = list_entity_history(conn, entity_type="venue", entity_id=venue_id, limit=50)
        history = [
            {
                "id": row.get("event_id") or row.get("version_id"),
                "operation": row.get("operation"),
                "summary": row.get("summary"),
                "actor": row.get("created_by"),
                "details": row.get("details") or {},
                "created_at": row.get("created_at"),
            }
            for row in rows
        ]
        suggestions = _list_cu_suggestions(status=None, entity_type="venue", entity_id=venue_id, limit=100)
        return jsonify({"success": True, "venue": venue, "history": history, "suggestions": suggestions})

    # --- Cor Unum: merge / alias endpoints ---

    @app.route("/api/cor-unum/artists/<int:artist_id>/merge-into", methods=["POST"])
    def api_cu_merge_artist(artist_id):
        admin_error = _require_cu_admin()
        if admin_error:
            return admin_error
        from ..ingestion.service import merge_artists
        data = request.get_json(silent=True) or {}
        canonical_id = data.get("canonical_id")
        if not canonical_id:
            return jsonify({"success": False, "error": "canonical_id required"}), 400
        result = merge_artists(artist_id, int(canonical_id))
        if result.get("error"):
            return jsonify({"success": False, "error": result["error"]}), 400
        return jsonify({"success": True, **result})

    @app.route("/api/cor-unum/venues/<int:venue_id>/merge-into", methods=["POST"])
    def api_cu_merge_venue(venue_id):
        admin_error = _require_cu_admin()
        if admin_error:
            return admin_error
        from ..ingestion.service import merge_venues
        data = request.get_json(silent=True) or {}
        canonical_id = data.get("canonical_id")
        if not canonical_id:
            return jsonify({"success": False, "error": "canonical_id required"}), 400
        result = merge_venues(venue_id, int(canonical_id))
        if result.get("error"):
            return jsonify({"success": False, "error": result["error"]}), 400
        return jsonify({"success": True, **result})

    @app.route("/api/cor-unum/artists/search")
    def api_cu_search_artists():
        from ..ingestion.service import search_artists_for_merge
        q = (request.args.get("q") or "").strip()
        exclude = request.args.get("exclude", type=int)
        return jsonify({"success": True, "results": search_artists_for_merge(q, exclude)})

    @app.route("/api/cor-unum/venues/search")
    def api_cu_search_venues():
        from ..ingestion.service import search_venues_for_merge
        q = (request.args.get("q") or "").strip()
        exclude = request.args.get("exclude", type=int)
        if not q:
            return jsonify({"success": True, "results": []})
        return jsonify({"success": True, "results": search_venues_for_merge(q, exclude)})

    # --- Cor Unum: settings + artist fingerprint checks ---

    @app.route("/cor-unum/settings")
    def cor_unum_settings():
        return render_template("cor_unum_settings.html")

    @app.route("/api/cor-unum/settings", methods=["GET"])
    def api_cu_settings_get():
        from ..ingestion.soundcloud import get_sc_config
        return jsonify({"success": True, "settings": get_sc_config()})

    @app.route("/api/cor-unum/settings", methods=["POST"])
    def api_cu_settings_save():
        from ..ingestion.soundcloud import save_sc_config
        data = request.get_json(silent=True) or {}
        save_sc_config(
            min_followers=int(data.get("min_followers", 0)),
            search_limit=int(data.get("search_limit", 5)),
        )
        return jsonify({"success": True})

    @app.route("/api/cor-unum/events/<int:event_id>/update", methods=["POST"])
    def api_cu_update_event(event_id):
        member_error = _require_cu_member_or_admin()
        if member_error:
            return member_error
        from ..ingestion.history import record_entity_change
        data = request.get_json(silent=True) or {}
        assignments: list[str] = []
        params: list = []
        title = data.get("title")
        date_value = data.get("date")
        description = data.get("description")
        venue_id = data.get("venue_id")
        venue_name = str(data.get("venue_name") or "").strip()
        if title is not None:
            assignments.append("title = ?")
            params.append(str(title).strip())
        if date_value is not None:
            assignments.append("date = ?")
            params.append(str(date_value).strip())
        if description is not None:
            assignments.append("description = ?")
            params.append(str(description).strip())
        actor = _cu_actor_label()
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id, title FROM cu_events WHERE id = ?",
                (event_id,),
            ).fetchone()
            if not existing:
                return jsonify({"success": False, "error": "Event not found"}), 404
            if venue_id is not None:
                resolved_venue_id = int(venue_id) if str(venue_id).strip() else None
                if resolved_venue_id is not None:
                    venue_row = conn.execute(
                        "SELECT id, alias_of FROM cu_venues WHERE id = ?",
                        (resolved_venue_id,),
                    ).fetchone()
                    if not venue_row:
                        return jsonify({"success": False, "error": "Venue not found"}), 404
                    resolved_venue_id = int(venue_row["alias_of"] or venue_row["id"])
                assignments.append("venue_id = ?")
                params.append(resolved_venue_id)
            elif venue_name:
                venue_row = conn.execute(
                    "SELECT id, alias_of FROM cu_venues WHERE name = ?",
                    (venue_name,),
                ).fetchone()
                if venue_row:
                    resolved_venue_id = int(venue_row["alias_of"] or venue_row["id"])
                else:
                    created = conn.execute(
                        "INSERT INTO cu_venues (name) VALUES (?)",
                        (venue_name,),
                    )
                    resolved_venue_id = int(created.lastrowid)
                    record_entity_change(
                        conn,
                        entity_type="venue",
                        entity_id=resolved_venue_id,
                        operation="cor_unum.venue.create",
                        summary=f"Created venue '{venue_name}'",
                        actor=actor,
                        details={"event_id": int(event_id)},
                    )
                assignments.append("venue_id = ?")
                params.append(resolved_venue_id)
            if not assignments:
                return jsonify({"success": False, "error": "No fields to update"}), 400
            params.append(event_id)
            conn.execute(
                f"UPDATE cu_events SET {', '.join(assignments)} WHERE id = ?",
                tuple(params),
            )
            record_entity_change(
                conn,
                entity_type="event",
                entity_id=int(event_id),
                operation="cor_unum.event.update",
                summary=f"Updated event '{existing['title']}'",
                actor=actor,
                details={"fields": list(data.keys())},
            )
        return jsonify({"success": True})

    @app.route("/api/cor-unum/venues/<int:venue_id>/update", methods=["POST"])
    def api_cu_update_venue(venue_id):
        member_error = _require_cu_member_or_admin()
        if member_error:
            return member_error
        from ..ingestion.history import record_entity_change
        data = request.get_json(silent=True) or {}
        assignments: list[str] = []
        params: list = []
        for field in ("name", "address", "url"):
            if field in data:
                assignments.append(f"{field} = ?")
                params.append((data.get(field) or "").strip() or None)
        if not assignments:
            return jsonify({"success": False, "error": "No fields to update"}), 400
        params.append(venue_id)
        actor = _cu_actor_label()
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id, name FROM cu_venues WHERE id = ?",
                (venue_id,),
            ).fetchone()
            if not existing:
                return jsonify({"success": False, "error": "Venue not found"}), 404
            conn.execute(
                f"UPDATE cu_venues SET {', '.join(assignments)} WHERE id = ?",
                tuple(params),
            )
            record_entity_change(
                conn,
                entity_type="venue",
                entity_id=int(venue_id),
                operation="cor_unum.venue.update",
                summary=f"Updated venue '{existing['name']}'",
                actor=actor,
                details={"fields": list(data.keys())},
            )
        return jsonify({"success": True})

    @app.route("/api/cor-unum/artists/<int:artist_id>/update", methods=["POST"])
    def api_cu_update_artist(artist_id):
        member_error = _require_cu_member_or_admin()
        if member_error:
            return member_error
        from ..ingestion.city_tags import set_local_yvr
        from ..ingestion.history import record_entity_change
        data = request.get_json(silent=True) or {}
        updates = []
        params = []
        if "is_local" in data:
            pass
        if "name" in data:
            updates.append("name = ?")
            params.append((data["name"] or "").strip())
        if "soundcloud_url" in data:
            updates.append("soundcloud_url = ?")
            params.append(data["soundcloud_url"].strip() or None)
        if "instagram_url" in data:
            updates.append("instagram_url = ?")
            params.append(data["instagram_url"].strip() or None)
        if "spotify_url" in data:
            updates.append("spotify_url = ?")
            params.append(data["spotify_url"].strip() or None)
        if "is_canadian" in data:
            updates.append("is_canadian = ?")
            val = data["is_canadian"]
            params.append(1 if bool(val) else 0)
        if not updates:
            if "is_local" not in data:
                return jsonify({"success": False, "error": "No fields to update"}), 400
        params.append(artist_id)
        actor = _cu_actor_label()
        with get_db() as conn:
            existing = conn.execute(
                "SELECT id, name FROM cu_artists WHERE id = ?",
                (artist_id,),
            ).fetchone()
            if not existing:
                return jsonify({"success": False, "error": "Artist not found"}), 404
            if updates:
                conn.execute(
                    f"UPDATE cu_artists SET {', '.join(updates)} WHERE id = ?",
                    params,
                )
                record_entity_change(
                    conn,
                    entity_type="artist",
                    entity_id=int(artist_id),
                    operation="cor_unum.artist.update",
                    summary=f"Updated artist '{existing['name']}'",
                    actor=actor,
                    details={"fields": list(data.keys())},
                )
            if "is_local" in data:
                set_local_yvr(conn, artist_id, bool(data["is_local"]))
                record_entity_change(
                    conn,
                    entity_type="artist",
                    entity_id=int(artist_id),
                    operation="cor_unum.artist.locality.update",
                    summary=f"Updated local tag for artist '{existing['name']}'",
                    actor=actor,
                    details={"is_local": bool(data["is_local"])},
                )
        return jsonify({"success": True})

    @app.route("/api/cor-unum/artists/<int:artist_id>/check-locality", methods=["POST"])
    def api_cu_check_artist_locality(artist_id):
        from ..ingestion.service import check_artist_fingerprint
        force = request.args.get("force", "0") == "1"
        result = check_artist_fingerprint("soundcloud", artist_id, force=force)
        if result.get("error"):
            return jsonify({"success": False, "error": result["error"]}), 400
        return jsonify({"success": True, **result})

    @app.route("/api/cor-unum/artists/check-all-locality", methods=["POST"])
    def api_cu_check_all_locality():
        from ..ingestion.service import check_all_artist_fingerprints
        raw_limit = request.args.get("limit", 30, type=int)
        limit = max(0, min(raw_limit if raw_limit is not None else 30, 200))
        mode = (request.args.get("mode") or "unchecked").strip().lower()
        result = check_all_artist_fingerprints("soundcloud", limit=limit, mode=mode)
        return jsonify({"success": True, "result": result})

    @app.route("/api/cor-unum/fingerprints")
    def api_cu_fingerprint_sources():
        from ..ingestion.service import get_fingerprint_sources
        return jsonify({"success": True, "sources": get_fingerprint_sources()})

    @app.route("/api/cor-unum/artists/<int:artist_id>/check-fingerprint/<source_key>", methods=["POST"])
    def api_cu_check_artist_fingerprint(artist_id, source_key):
        from ..ingestion.service import check_artist_fingerprint
        force = request.args.get("force", "0") == "1"
        result = check_artist_fingerprint(source_key, artist_id, force=force)
        if result.get("error"):
            return jsonify({"success": False, "error": result["error"]}), 400
        return jsonify({"success": True, **result})

    @app.route("/api/cor-unum/artists/check-all-fingerprint/<source_key>", methods=["POST"])
    def api_cu_check_all_artist_fingerprints(source_key):
        from ..ingestion.service import check_all_artist_fingerprints
        raw_limit = request.args.get("limit", 30, type=int)
        limit = max(0, min(raw_limit if raw_limit is not None else 30, 200))
        mode = (request.args.get("mode") or "unchecked").strip().lower()
        result = check_all_artist_fingerprints(source_key, limit=limit, mode=mode)
        if result.get("error"):
            return jsonify({"success": False, "error": result["error"]}), 400
        return jsonify({"success": True, "result": result})


    return app


def run_web():
    """Run the web dashboard."""
    app = create_app()
    host = Config.web_host()
    port = Config.web_port()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run_web()
