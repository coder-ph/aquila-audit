import pkgutil
import importlib

# This code automatically imports all submodules in the current directory
for loader, module_name, is_pkg in pkgutil.walk_packages(__path__):
    importlib.import_module(f'shared.models.{module_name}')