"""
Skill: troubleshoot
Diagnoses issues with Noctem skills and systems.

Parameters:
  - target (str, optional): Specific component to troubleshoot 
                           (web, network, cache, skills, all)
  - verbose (bool, optional): Include detailed diagnostics (default: false)

Returns:
  - success: {"status": "ok/warning/error", "diagnostics": [...], "recommendations": [...]}
  - error: {"error": "..."}
"""
import sys
import socket
import importlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class DiagnosticResult:
    """Result of a single diagnostic check."""
    name: str
    status: str  # "ok", "warning", "error"
    message: str
    details: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "details": self.details
        }


class TroubleshootBase:
    """Base class for troubleshoot modules."""
    
    name: str = "base"
    description: str = "Base troubleshooter"
    
    def run_diagnostics(self, verbose: bool = False) -> List[DiagnosticResult]:
        """Run all diagnostics for this module. Override in subclass."""
        return []
    
    def get_recommendations(self, results: List[DiagnosticResult]) -> List[str]:
        """Generate recommendations based on diagnostic results."""
        return []


class NetworkTroubleshoot(TroubleshootBase):
    """Diagnose network connectivity issues."""
    
    name = "network"
    description = "Network connectivity diagnostics"
    
    def run_diagnostics(self, verbose: bool = False) -> List[DiagnosticResult]:
        results = []
        
        # Check DNS resolution
        results.append(self._check_dns())
        
        # Check basic connectivity
        results.append(self._check_connectivity())
        
        # Check if we can reach common services
        if verbose:
            results.append(self._check_https())
        
        return results
    
    def _check_dns(self) -> DiagnosticResult:
        """Check if DNS resolution works."""
        try:
            socket.gethostbyname("example.com")
            return DiagnosticResult(
                name="dns_resolution",
                status="ok",
                message="DNS resolution working"
            )
        except socket.gaierror as e:
            return DiagnosticResult(
                name="dns_resolution",
                status="error",
                message="DNS resolution failed",
                details=str(e)
            )
    
    def _check_connectivity(self) -> DiagnosticResult:
        """Check basic network connectivity."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(("8.8.8.8", 53))  # Google DNS
            sock.close()
            
            if result == 0:
                return DiagnosticResult(
                    name="network_connectivity",
                    status="ok",
                    message="Network connectivity working"
                )
            else:
                return DiagnosticResult(
                    name="network_connectivity",
                    status="error",
                    message="Cannot reach external network",
                    details=f"Connection error code: {result}"
                )
        except Exception as e:
            return DiagnosticResult(
                name="network_connectivity",
                status="error",
                message="Network check failed",
                details=str(e)
            )
    
    def _check_https(self) -> DiagnosticResult:
        """Check HTTPS connectivity."""
        try:
            import ssl
            import urllib.request
            
            ctx = ssl.create_default_context()
            req = urllib.request.Request(
                "https://example.com",
                headers={"User-Agent": "Noctem/1.0"}
            )
            urllib.request.urlopen(req, timeout=10, context=ctx)
            
            return DiagnosticResult(
                name="https_connectivity",
                status="ok",
                message="HTTPS connectivity working"
            )
        except Exception as e:
            return DiagnosticResult(
                name="https_connectivity",
                status="error",
                message="HTTPS connection failed",
                details=str(e)
            )
    
    def get_recommendations(self, results: List[DiagnosticResult]) -> List[str]:
        recs = []
        for r in results:
            if r.status == "error":
                if "dns" in r.name:
                    recs.append("Check DNS settings in /etc/resolv.conf")
                    recs.append("Try: ping 8.8.8.8 (if this works, DNS is the issue)")
                elif "connectivity" in r.name:
                    recs.append("Check if connected to network (WiFi/Ethernet)")
                    recs.append("Check firewall settings")
                elif "https" in r.name:
                    recs.append("Check system time (SSL requires correct time)")
                    recs.append("Check if HTTPS is blocked by firewall/proxy")
        return recs


class CacheTroubleshoot(TroubleshootBase):
    """Diagnose cache issues."""
    
    name = "cache"
    description = "Cache system diagnostics"
    
    def run_diagnostics(self, verbose: bool = False) -> List[DiagnosticResult]:
        results = []
        
        results.append(self._check_cache_dir())
        results.append(self._check_cache_permissions())
        
        if verbose:
            results.append(self._check_cache_contents())
        
        return results
    
    def _check_cache_dir(self) -> DiagnosticResult:
        """Check if cache directory exists and is accessible."""
        from utils.cache import CACHE_DIR
        
        if CACHE_DIR.exists():
            return DiagnosticResult(
                name="cache_directory",
                status="ok",
                message=f"Cache directory exists: {CACHE_DIR}"
            )
        else:
            # Try to create it
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                return DiagnosticResult(
                    name="cache_directory",
                    status="ok",
                    message=f"Cache directory created: {CACHE_DIR}"
                )
            except Exception as e:
                return DiagnosticResult(
                    name="cache_directory",
                    status="error",
                    message="Cannot create cache directory",
                    details=str(e)
                )
    
    def _check_cache_permissions(self) -> DiagnosticResult:
        """Check cache directory permissions."""
        from utils.cache import CACHE_DIR
        import os
        
        if not CACHE_DIR.exists():
            return DiagnosticResult(
                name="cache_permissions",
                status="warning",
                message="Cache directory does not exist yet"
            )
        
        # Check write permission
        test_file = CACHE_DIR / ".write_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
            return DiagnosticResult(
                name="cache_permissions",
                status="ok",
                message="Cache directory is writable"
            )
        except Exception as e:
            return DiagnosticResult(
                name="cache_permissions",
                status="error",
                message="Cache directory is not writable",
                details=str(e)
            )
    
    def _check_cache_contents(self) -> DiagnosticResult:
        """Check cache contents and size."""
        from utils.cache import CACHE_DIR
        
        if not CACHE_DIR.exists():
            return DiagnosticResult(
                name="cache_contents",
                status="ok",
                message="Cache is empty (directory doesn't exist)"
            )
        
        files = list(CACHE_DIR.glob("*.json"))
        total_size = sum(f.stat().st_size for f in files)
        
        return DiagnosticResult(
            name="cache_contents",
            status="ok",
            message=f"Cache has {len(files)} entries, {total_size / 1024:.1f} KB total",
            details=", ".join(f.stem[:20] for f in files[:5]) + ("..." if len(files) > 5 else "")
        )
    
    def get_recommendations(self, results: List[DiagnosticResult]) -> List[str]:
        recs = []
        for r in results:
            if r.status == "error":
                if "directory" in r.name:
                    recs.append("Check disk space and parent directory permissions")
                elif "permissions" in r.name:
                    recs.append("Run: chmod 755 cache/")
                    recs.append("Check if running as correct user")
        return recs


class WebSkillsTroubleshoot(TroubleshootBase):
    """Diagnose web_fetch and web_search skill issues."""
    
    name = "web"
    description = "Web skills (fetch/search) diagnostics"
    
    def run_diagnostics(self, verbose: bool = False) -> List[DiagnosticResult]:
        results = []
        
        # Check dependencies
        results.append(self._check_dependencies())
        
        # Check skill registration
        results.append(self._check_skill_registration())
        
        # Check rate limiter state
        results.append(self._check_rate_limiter())
        
        # Test actual fetch (only in verbose mode, requires network)
        if verbose:
            results.append(self._test_fetch())
            results.append(self._test_search())
        
        return results
    
    def _check_dependencies(self) -> DiagnosticResult:
        """Check required Python packages."""
        missing = []
        
        try:
            import requests
        except ImportError:
            missing.append("requests")
        
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            missing.append("beautifulsoup4")
        
        if missing:
            return DiagnosticResult(
                name="dependencies",
                status="error",
                message=f"Missing packages: {', '.join(missing)}",
                details=f"Install with: pip install {' '.join(missing)}"
            )
        
        return DiagnosticResult(
            name="dependencies",
            status="ok",
            message="All required packages installed"
        )
    
    def _check_skill_registration(self) -> DiagnosticResult:
        """Check if web skills are properly registered."""
        try:
            from skills import get_skill
            
            web_fetch = get_skill("web_fetch")
            web_search = get_skill("web_search")
            
            if web_fetch is None:
                return DiagnosticResult(
                    name="skill_registration",
                    status="error",
                    message="web_fetch skill not registered"
                )
            
            if web_search is None:
                return DiagnosticResult(
                    name="skill_registration",
                    status="error",
                    message="web_search skill not registered"
                )
            
            return DiagnosticResult(
                name="skill_registration",
                status="ok",
                message="Both web_fetch and web_search skills registered"
            )
        except Exception as e:
            return DiagnosticResult(
                name="skill_registration",
                status="error",
                message="Failed to check skill registration",
                details=str(e)
            )
    
    def _check_rate_limiter(self) -> DiagnosticResult:
        """Check rate limiter state."""
        try:
            from utils.rate_limit import _last_request
            
            active_limits = len(_last_request)
            domains = list(_last_request.keys())[:5]
            
            return DiagnosticResult(
                name="rate_limiter",
                status="ok",
                message=f"Rate limiter tracking {active_limits} domain(s)",
                details=", ".join(domains) if domains else "No domains tracked"
            )
        except Exception as e:
            return DiagnosticResult(
                name="rate_limiter",
                status="warning",
                message="Could not inspect rate limiter",
                details=str(e)
            )
    
    def _test_fetch(self) -> DiagnosticResult:
        """Test actual web_fetch functionality."""
        try:
            from skills.web_fetch import run
            result = run("https://example.com", use_cache=False)
            
            if "error" in result:
                return DiagnosticResult(
                    name="fetch_test",
                    status="error",
                    message=f"web_fetch failed: {result['error']}"
                )
            
            if "Example Domain" in result.get("title", ""):
                return DiagnosticResult(
                    name="fetch_test",
                    status="ok",
                    message="web_fetch working (fetched example.com)"
                )
            else:
                return DiagnosticResult(
                    name="fetch_test",
                    status="warning",
                    message="web_fetch returned unexpected content"
                )
        except Exception as e:
            return DiagnosticResult(
                name="fetch_test",
                status="error",
                message="web_fetch test failed",
                details=str(e)
            )
    
    def _test_search(self) -> DiagnosticResult:
        """Test actual web_search functionality."""
        try:
            from skills.web_search import run
            result = run("test query", num_results=2, use_cache=False)
            
            if "error" in result:
                # Rate limiting is expected sometimes
                if "rate" in result["error"].lower():
                    return DiagnosticResult(
                        name="search_test",
                        status="warning",
                        message="web_search rate limited (try again later)"
                    )
                return DiagnosticResult(
                    name="search_test",
                    status="error",
                    message=f"web_search failed: {result['error']}"
                )
            
            if result.get("results"):
                return DiagnosticResult(
                    name="search_test",
                    status="ok",
                    message=f"web_search working ({len(result['results'])} results)"
                )
            else:
                return DiagnosticResult(
                    name="search_test",
                    status="warning",
                    message="web_search returned no results (may be rate limited)"
                )
        except Exception as e:
            return DiagnosticResult(
                name="search_test",
                status="error",
                message="web_search test failed",
                details=str(e)
            )
    
    def get_recommendations(self, results: List[DiagnosticResult]) -> List[str]:
        recs = []
        for r in results:
            if r.status == "error":
                if "dependencies" in r.name:
                    recs.append("Install missing packages with pip")
                elif "registration" in r.name:
                    recs.append("Check skills/__init__.py imports web_fetch and web_search")
                    recs.append("Restart the daemon after fixing")
                elif "fetch" in r.name:
                    recs.append("Run 'troubleshoot network' to check connectivity")
                    recs.append("Check if the URL is blocked by robots.txt")
                elif "search" in r.name:
                    recs.append("DuckDuckGo may be rate limiting - wait a few minutes")
                    recs.append("Check network connectivity")
            elif r.status == "warning":
                if "rate" in r.message.lower():
                    recs.append("Wait 2-5 minutes before retrying searches")
        return recs


class SkillsTroubleshoot(TroubleshootBase):
    """Diagnose general skills system issues."""
    
    name = "skills"
    description = "Skills system diagnostics"
    
    def run_diagnostics(self, verbose: bool = False) -> List[DiagnosticResult]:
        results = []
        
        results.append(self._check_skills_loaded())
        results.append(self._check_skill_runner())
        
        if verbose:
            results.append(self._test_shell_skill())
        
        return results
    
    def _check_skills_loaded(self) -> DiagnosticResult:
        """Check what skills are loaded."""
        try:
            from skills import get_all_skills
            skills = get_all_skills()
            
            expected = ["shell", "signal_send", "file_read", "file_write", 
                       "task_status", "web_fetch", "web_search"]
            loaded = list(skills.keys())
            missing = [s for s in expected if s not in loaded]
            
            if missing:
                return DiagnosticResult(
                    name="skills_loaded",
                    status="warning",
                    message=f"Missing expected skills: {', '.join(missing)}",
                    details=f"Loaded: {', '.join(loaded)}"
                )
            
            return DiagnosticResult(
                name="skills_loaded",
                status="ok",
                message=f"{len(loaded)} skills loaded",
                details=", ".join(loaded)
            )
        except Exception as e:
            return DiagnosticResult(
                name="skills_loaded",
                status="error",
                message="Failed to load skills",
                details=str(e)
            )
    
    def _check_skill_runner(self) -> DiagnosticResult:
        """Check skill runner functionality."""
        try:
            from skill_runner import run_skill, list_skills
            
            skills = list_skills()
            if not skills:
                return DiagnosticResult(
                    name="skill_runner",
                    status="error",
                    message="Skill runner reports no skills"
                )
            
            return DiagnosticResult(
                name="skill_runner",
                status="ok",
                message="Skill runner operational"
            )
        except Exception as e:
            return DiagnosticResult(
                name="skill_runner",
                status="error",
                message="Skill runner failed",
                details=str(e)
            )
    
    def _test_shell_skill(self) -> DiagnosticResult:
        """Test basic shell skill."""
        try:
            from skill_runner import run_skill
            result = run_skill("shell", {"command": "echo 'test'"})
            
            if result.success and "test" in result.output:
                return DiagnosticResult(
                    name="shell_skill_test",
                    status="ok",
                    message="Shell skill working"
                )
            else:
                return DiagnosticResult(
                    name="shell_skill_test",
                    status="error",
                    message="Shell skill returned unexpected result",
                    details=result.error or result.output
                )
        except Exception as e:
            return DiagnosticResult(
                name="shell_skill_test",
                status="error",
                message="Shell skill test failed",
                details=str(e)
            )
    
    def get_recommendations(self, results: List[DiagnosticResult]) -> List[str]:
        recs = []
        for r in results:
            if r.status == "error":
                if "loaded" in r.name:
                    recs.append("Check skills/__init__.py for import errors")
                    recs.append("Run: python -c 'from skills import *' to see errors")
                elif "runner" in r.name:
                    recs.append("Check skill_runner.py for syntax errors")
        return recs


# Registry of all troubleshoot modules
TROUBLESHOOT_MODULES = {
    "network": NetworkTroubleshoot(),
    "cache": CacheTroubleshoot(),
    "web": WebSkillsTroubleshoot(),
    "skills": SkillsTroubleshoot(),
}


def run(target: str = "all", verbose: bool = False) -> dict:
    """
    Run troubleshooting diagnostics.
    
    Args:
        target: Component to troubleshoot (network, cache, web, skills, all)
        verbose: Include detailed/slow diagnostics
    
    Returns:
        Diagnostic report with status, results, and recommendations
    """
    all_results = []
    all_recommendations = []
    
    # Determine which modules to run
    if target == "all":
        modules = list(TROUBLESHOOT_MODULES.values())
    elif target in TROUBLESHOOT_MODULES:
        modules = [TROUBLESHOOT_MODULES[target]]
    else:
        return {"error": f"Unknown target: {target}. Use: {', '.join(TROUBLESHOOT_MODULES.keys())}, all"}
    
    # Run diagnostics
    for module in modules:
        results = module.run_diagnostics(verbose=verbose)
        all_results.extend(results)
        
        # Get recommendations for any issues
        recs = module.get_recommendations(results)
        all_recommendations.extend(recs)
    
    # Determine overall status
    statuses = [r.status for r in all_results]
    if "error" in statuses:
        overall_status = "error"
    elif "warning" in statuses:
        overall_status = "warning"
    else:
        overall_status = "ok"
    
    # Remove duplicate recommendations
    unique_recs = list(dict.fromkeys(all_recommendations))
    
    return {
        "status": overall_status,
        "target": target,
        "verbose": verbose,
        "timestamp": datetime.now().isoformat(),
        "diagnostics": [r.to_dict() for r in all_results],
        "summary": {
            "total": len(all_results),
            "ok": statuses.count("ok"),
            "warning": statuses.count("warning"),
            "error": statuses.count("error")
        },
        "recommendations": unique_recs
    }


# Skill class wrapper for Noctem framework
from typing import Dict
try:
    from .base import Skill, SkillResult, SkillContext, register_skill
except ImportError:
    # Running as standalone script
    from base import Skill, SkillResult, SkillContext, register_skill


@register_skill
class TroubleshootSkill(Skill):
    """Diagnose issues with Noctem components."""
    
    name = "troubleshoot"
    description = "Diagnose issues with Noctem skills and systems. Use when something isn't working."
    parameters = {
        "target": "string (optional) - component to troubleshoot: network, cache, web, skills, or all (default: all)",
        "verbose": "bool (optional, default false) - run detailed diagnostics (slower, may require network)"
    }
    
    def run(self, params: Dict, context: SkillContext) -> SkillResult:
        target = params.get("target", "all")
        verbose = params.get("verbose", False)
        
        result = run(target=target, verbose=verbose)
        
        if "error" in result:
            return SkillResult(
                success=False,
                output="",
                error=result["error"]
            )
        
        # Format output
        lines = [f"Troubleshoot Report: {target.upper()}"]
        lines.append(f"Status: {result['status'].upper()}")
        lines.append(f"Checks: {result['summary']['ok']} ok, {result['summary']['warning']} warnings, {result['summary']['error']} errors")
        lines.append("")
        
        # Show diagnostics
        for diag in result["diagnostics"]:
            icon = "✓" if diag["status"] == "ok" else "⚠" if diag["status"] == "warning" else "✗"
            lines.append(f"{icon} {diag['name']}: {diag['message']}")
            if diag.get("details") and verbose:
                lines.append(f"    {diag['details']}")
        
        # Show recommendations
        if result["recommendations"]:
            lines.append("")
            lines.append("Recommendations:")
            for rec in result["recommendations"]:
                lines.append(f"  • {rec}")
        
        return SkillResult(
            success=True,
            output="\n".join(lines),
            data=result
        )


# CLI for direct testing
if __name__ == "__main__":
    import json
    
    target = sys.argv[1] if len(sys.argv) > 1 else "all"
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    
    result = run(target=target, verbose=verbose)
    
    print(f"\n{'='*50}")
    print(f"Troubleshoot: {target.upper()}")
    print(f"{'='*50}\n")
    
    for diag in result.get("diagnostics", []):
        icon = "✓" if diag["status"] == "ok" else "⚠" if diag["status"] == "warning" else "✗"
        print(f"{icon} [{diag['status'].upper():7}] {diag['name']}: {diag['message']}")
        if diag.get("details"):
            print(f"           {diag['details']}")
    
    if result.get("recommendations"):
        print(f"\n{'='*50}")
        print("Recommendations:")
        print(f"{'='*50}")
        for rec in result["recommendations"]:
            print(f"  • {rec}")
    
    print(f"\nOverall Status: {result.get('status', 'unknown').upper()}")
