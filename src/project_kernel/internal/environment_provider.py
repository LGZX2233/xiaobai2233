"""Inspect the configured Python runtime and installed distribution metadata."""
from datetime import datetime, timezone
import importlib.metadata
import platform
import sys
from packaging.specifiers import SpecifierSet, InvalidSpecifier
from packaging.version import Version, InvalidVersion

class PythonEnvironmentProbe:
    """Inspect this configured Python runtime and distribution metadata."""
    def probe(self, recipes):
        facts=[]
        for recipe in recipes:
            for requirement in recipe.get("dependencies",[]):
                name=requirement["name"]
                spec=requirement.get("version_spec","")
                fact={"name":name,"required_version":spec,"checked_at":datetime.now(timezone.utc).isoformat()}
                try:
                    if name=="python":
                        version=platform.python_version()
                        path=sys.executable
                    else:
                        dist=importlib.metadata.distribution(name)
                        version=dist.version
                        path=str(dist.locate_file(""))
                    state="satisfied" if Version(version) in SpecifierSet(spec) else "too_old"
                    fact.update(version=version,path=path,state=state)
                except importlib.metadata.PackageNotFoundError:
                    fact.update(version=None,path=None,state="missing")
                except (InvalidVersion,InvalidSpecifier) as exc:
                    fact.update(version=None,path=None,state="unknown",reason=str(exc))
                facts.append(fact)
        return {"facts":facts,"runtime_path":sys.executable,"checked_at":datetime.now(timezone.utc).isoformat(),
                "status":"ready" if facts and all(f["state"]=="satisfied" for f in facts) else "blocked"}
