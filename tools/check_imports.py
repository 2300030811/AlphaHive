import importlib
import traceback

modules = [
    'agents.specialists.fundamental',
    'agents.specialists.technical',
    'agents.specialists.news',
    'engine.cache',
    'engine.orchestrator'
]

for m in modules:
    try:
        importlib.import_module(m)
        print(f"{m}: OK")
    except Exception as e:
        print(f"{m}: ERR {e}")
        traceback.print_exc()
        break
